"""Trajectory replay: record successful runs, replay on similar tasks with step verification.

Architecture:
1. RECORD: during task, capture tool calls + between-action screenshots
2. MATCH: on high-similarity memory hits, evaluate replay viability
3. REPLAY: execute step-by-step, LLM-verify each step against history
4. ABORT: on mismatch, handoff to Agent with partial progress
"""

import hashlib
import json
import time
from pathlib import Path

import numpy as np

from cua.tools.screenshot import _np_to_png_b64, downsample_for_vlm

TRAJ_DIR = Path(__file__).parent / "data" / "trajectories"
TRAJ_DIR.mkdir(parents=True, exist_ok=True)


def _safe_json(content: str) -> dict:
    """Parse JSON safely, delegating to learning._repair_json."""
    from cua.learning import _repair_json
    result = _repair_json(content)
    # Normalize keys for replay use
    if "reason" in result and "reasoning" not in result:
        result["reasoning"] = result["reason"]
    return result


# --- Recording ---

class TrajectoryRecorder:
    """Records tool calls + screenshots during a task execution."""

    def __init__(self, task: str):
        self.task = task
        self.steps: list[dict] = []  # [{name, args, screenshot_before_b64}]
        self._last_screenshot: np.ndarray | None = None

    def record_step(self, name: str, args: dict, screenshot_before: np.ndarray,
                    screen_w: int, screen_h: int, mouse_pos: tuple, save_screenshot: bool = True):
        """Record a tool call. Only saves screenshot for action tools (save_screenshot=True)."""
        step = {"name": name, "args": args, "screenshot_b64": ""}
        if save_screenshot:
            downscaled, _, _ = downsample_for_vlm(screenshot_before, mouse_pos, screen_w, screen_h)
            rgb = downscaled[..., [2, 1, 0]]  # BGRA→RGB
            step["screenshot_b64"] = _np_to_png_b64(rgb)
        self.steps.append(step)
        self._last_screenshot = screenshot_before

    def update_last_step_screenshot(self, after_screenshot: np.ndarray,
                                     screen_w: int, screen_h: int, mouse_pos: tuple):
        """Replace the last recorded step's screenshot with AFTER-action state."""
        if self.steps:
            downscaled, _, _ = downsample_for_vlm(after_screenshot, mouse_pos, screen_w, screen_h)
            rgb = downscaled[..., [2, 1, 0]]
            self.steps[-1]["screenshot_b64"] = _np_to_png_b64(rgb)

    def save(self, task_summary: str = "", client=None, model: str = "") -> str | None:
        """Save trajectory. LLM cleans redundant steps, then decides replace/modify/abandon."""
        action_steps = [s for s in self.steps if s.get("screenshot_b64") and len(s["screenshot_b64"]) > 100]
        if len(action_steps) < 1:
            return None

        # LLM cleans the trajectory — removes redundant/unnecessary steps
        cleaned = _clean_trajectory(self.task, self.steps, client, model)

        traj_id = hashlib.sha256(
            json.dumps([s["name"] for s in self.steps]).encode()
        ).hexdigest()[:12]

        # Check for similar existing trajectory
        existing_id = None
        existing_data = None
        if task_summary:
            try:
                existing_id = _find_similar_traj(task_summary)
                if existing_id:
                    existing_data = load_trajectory(existing_id)
            except Exception:
                pass

        # If similar exists, ask LLM what to do
        action = "save_new"  # default
        if existing_data and client and model:
            action = _decide_trajectory_action(
                self.task, task_summary, cleaned, existing_data, client, model
            )
            print(f"  [replay] trajectory decision: {action}")

        # Handle old trajectory
        if existing_id and action in ("replace", "modify"):
            old_path = TRAJ_DIR / f"{existing_id}.json"
            if old_path.exists():
                if action == "replace":
                    old_path.unlink()
                else:  # modify — keep old as backup
                    old_path.rename(TRAJ_DIR / f"{existing_id}.old.json")

        if action == "abandon":
            return None  # Keep existing, don't save new

        meta = {
            "task": self.task,
            "summary": task_summary,
            "steps": cleaned,
        }

        path = TRAJ_DIR / f"{traj_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        return traj_id


def _clean_trajectory(task: str, steps: list, client, model: str) -> list:
    """LLM reviews trajectory screenshots, removes redundant steps.

    Returns cleaned steps list (name, args, screenshot_b64).
    """
    if not client or not model:
        return [{"name": s["name"], "args": s["args"], "screenshot_b64": s.get("screenshot_b64", "")}
                for s in steps]

    # Build content blocks with step descriptions + screenshots
    content_blocks = [
        {"type": "text", "text": (
            f"Task: {task}\n\nBelow are trajectory steps with screenshots. "
            f"Remove steps that are redundant (same state shown twice), "
            f"or don't contribute to the task outcome. Keep the essential sequence. "
            f"Output JSON: {{\"keep\": [1, 3, 5, 7]}} with 1-based step indices.\n"
        )},
    ]

    for i, s in enumerate(steps):
        desc = f"Step {i+1}: {s['name']} {json.dumps(s['args'], ensure_ascii=False)[:80]}"
        if s.get("screenshot_b64") and len(s["screenshot_b64"]) > 100:
            content_blocks.append({"type": "text", "text": desc})
            content_blocks.append({"type": "image_url", "image_url": {"url": s["screenshot_b64"]}})
        else:
            content_blocks.append({"type": "text", "text": desc + " (no screenshot)"})

    content_blocks.append({"type": "text", "text": "Which steps to keep?"})

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": (
                    "You clean automation trajectories by reviewing screenshots. "
                    "Remove redundant steps: if two screenshots show the same state, "
                    "keep only the latest. Remove unnecessary perception (repeated "
                    "screenshot without action in between). Keep the minimal sequence "
                    "that successfully completes the task. "
                    "Output JSON: {\"keep\": [1-based indices]}"
                )},
                {"role": "user", "content": content_blocks},
            ],
            response_format={"type": "json_object"},
        )
        result = _safe_json(resp.choices[0].message.content)
        keep = result.get("keep", [])
        if not keep:
            return [{"name": s["name"], "args": s["args"], "screenshot_b64": s.get("screenshot_b64", "")}
                    for s in steps]

        cleaned = []
        for i, s in enumerate(steps):
            if (i + 1) in keep:
                cleaned.append({
                    "name": s["name"], "args": s["args"],
                    "screenshot_b64": s.get("screenshot_b64", ""),
                })
        if cleaned and len(cleaned) < len(steps):
            print(f"  [replay] trajectory cleaned: {len(steps)} -> {len(cleaned)} steps")
        return cleaned if cleaned else [{"name": s["name"], "args": s["args"], "screenshot_b64": s.get("screenshot_b64", "")} for s in steps]
    except Exception:
        pass

    return [{"name": s["name"], "args": s["args"], "screenshot_b64": s.get("screenshot_b64", "")}
            for s in steps]


def _decide_trajectory_action(task: str, summary: str, new_steps: list,
                               existing: dict, client, model: str) -> str:
    """LLM decides: replace, modify, or abandon."""
    try:
        old_steps = json.dumps([
            f"{s['name']}({json.dumps(s['args'], ensure_ascii=False)[:60]})"
            for s in existing.get("steps", [])
        ], ensure_ascii=False)
        new_steps_str = json.dumps([
            f"{s['name']}({json.dumps(s['args'], ensure_ascii=False)[:60]})"
            for s in new_steps
        ], ensure_ascii=False)

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": (
                    "You manage replay trajectory versions. Given an existing trajectory "
                    "and a new one from the same task, decide: replace (new is better), "
                    "modify (merge best of both), or abandon (keep old). "
                    "Output JSON: {\"action\": \"replace\"|\"modify\"|\"abandon\", \"reason\": \"...\"}"
                )},
                {"role": "user", "content": (
                    f"Task: {task}\nSummary: {summary}\n\n"
                    f"Old trajectory ({existing.get('task','')}):\n{old_steps}\n\n"
                    f"New trajectory:\n{new_steps_str}\n\n"
                    f"Decide."
                )},
            ],
            response_format={"type": "json_object"},
        )
        result = _safe_json(resp.choices[0].message.content)
        action = result.get("action", "save_new")
        if action not in ("replace", "modify", "abandon"):
            action = "save_new"
        return action
    except Exception:
        return "save_new"


def _find_similar_traj(task_summary: str) -> str | None:
    """Find the most similar existing trajectory ID. Returns None if no good match."""
    files = [f for f in TRAJ_DIR.glob("*.json") if not f.name.endswith(".old.json")]
    if not files:
        return None

    docs = {}
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                traj = json.load(fh)
            s = traj.get("summary", traj.get("task", ""))
            if s:
                docs[f.stem] = s
        except Exception:
            continue

    if not docs:
        return None

    try:
        import chromadb
        from chromadb.utils import embedding_functions
        client = chromadb.Client(settings=chromadb.Settings(
            chroma_db_impl="duckdb+parquet", persist_directory=":memory:"
        ))
        ef = embedding_functions.DefaultEmbeddingFunction()
        col = client.create_collection("_traj_replace", embedding_function=ef)
        ids = list(docs.keys())
        col.add(ids=ids, documents=[docs[k] for k in ids])

        results = col.query(query_texts=[task_summary], n_results=1)
        if results["ids"] and results["ids"][0] and results["distances"][0]:
            sim = 1.0 - results["distances"][0][0]
            if sim >= 0.5:
                return results["ids"][0][0]
    except Exception:
        pass
    return None


def load_trajectory(traj_id: str) -> dict | None:
    """Load a saved trajectory by ID."""
    path = TRAJ_DIR / f"{traj_id}.json"
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_trajectory(task_summary: str) -> dict | None:
    """Find the most relevant trajectory by searching all saved ones via ChromaDB.

    Returns the trajectory dict or None if no good match found.
    """
    if not TRAJ_DIR.exists():
        return None

    # Get all trajectory files
    files = [f for f in TRAJ_DIR.glob("*.json") if not f.name.endswith(".old.json")]
    if not files:
        return None

    # Build a simple in-memory index for this search
    traj_docs = []
    traj_map = {}
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                traj = json.load(fh)
            task = traj.get("task", "")
            if task:
                traj_docs.append(task)
                traj_map[task] = traj
        except Exception:
            continue

    if not traj_docs:
        return None

    try:
        # Use a temp collection for trajectory search
        import chromadb
        client = chromadb.Client(settings=chromadb.Settings(
            chroma_db_impl="duckdb+parquet", persist_directory=":memory:"
        ))
        from chromadb.utils import embedding_functions
        ef = embedding_functions.DefaultEmbeddingFunction()
        col = client.create_collection("_traj_search", embedding_function=ef)
        col.add(ids=[str(i) for i in range(len(traj_docs))], documents=traj_docs)

        results = col.query(query_texts=[task_summary], n_results=1)
        if results["ids"] and results["ids"][0] and results["distances"][0]:
            sim = 1.0 - results["distances"][0][0]
            if sim >= 0.6:  # high threshold — only genuinely similar tasks
                idx = int(results["ids"][0][0])
                return traj_map[traj_docs[idx]]
    except Exception:
        pass

    # Fallback: no good match — return None
    return None


def delete_trajectory(traj_id: str):
    """Delete a trajectory."""
    path = TRAJ_DIR / f"{traj_id}.json"
    if path.exists():
        path.unlink()


# --- Replay Judge ---

def evaluate_replay(task: str, similar_text: str, traj_tool_names: list[str],
                    current_screenshot_b64: str, client, model: str) -> dict:
    """Ask a bare LLM whether trajectory replay is appropriate."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": (
                    "You evaluate whether to replay a recorded automation trajectory. "
                    "CRITICAL: reject if the trajectory tools/apps DON'T MATCH the task. "
                    "E.g., if task is about WeChat but trajectory launches Notepad → reject. "
                    "can_replay=true ONLY if: same app/domain, screen compatible, no blockers. "
                    "Return JSON: {\"can_replay\": true/false, \"reasoning\": \"...\"}"
                )},
                {"role": "user", "content": [
                    {"type": "text", "text": (
                        f"Task: {task}\n\n"
                        f"Trajectory tools: {', '.join(traj_tool_names[:10])}\n\n"
                        f"Similar past matches:\n{similar_text}\n\n"
                        f"Current screenshot:"
                    )},
                    {"type": "image_url", "image_url": {"url": current_screenshot_b64}},
                    {"type": "text", "text": "Can this trajectory be replayed for this task?"},
                ]},
            ],
            response_format={"type": "json_object"},
        )
        return _safe_json(resp.choices[0].message.content)
    except Exception as e:
        return {"can_replay": False, "reasoning": f"Judge error: {e}", "warnings": ""}


# --- Step Verifier ---

def verify_step(step: dict, current_screenshot: np.ndarray,
                sct, mouse_pos, screen_w, screen_h,
                client, model: str) -> dict:
    """After executing one replay step, verify the result matches history.

    Returns {"ok": bool, "reason": str}
    """
    try:
        down, _, _ = downsample_for_vlm(current_screenshot, mouse_pos, screen_w, screen_h)
        current_b64 = _np_to_png_b64(down[..., [2, 1, 0]])

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": (
                    "You verify whether a replayed automation step matches the expected outcome. "
                    "Compare the BEFORE (historical) and AFTER (current) screenshots. "
                    "Return JSON: {\"ok\": true/false, \"reason\": \"brief explanation\"}. "
                    "ok=true means the screenshots show equivalent results — the step succeeded."
                )},
                {"role": "user", "content": [
                    {"type": "text", "text": f"Step: {step['name']} with args {json.dumps(step['args'])}"},
                    {"type": "text", "text": "HISTORICAL (expected after this step):"},
                    {"type": "image_url", "image_url": {"url": step["screenshot_b64"]}},
                    {"type": "text", "text": "CURRENT (actual after executing):"},
                    {"type": "image_url", "image_url": {"url": current_b64}},
                    {"type": "text", "text": "Do these screenshots show the same outcome?"},
                ]},
            ],
            response_format={"type": "json_object"},
            max_tokens=150,
        )
        return _safe_json(resp.choices[0].message.content)
    except Exception as e:
        return {"ok": False, "reason": f"Verify error: {e}"}


# --- Main Replay Engine ---

def attempt_replay(traj: dict, task: str, similar_text: str,
                   sct, mouse_pos, screen_w, screen_h,
                   client, model: str) -> dict:
    """Attempt to replay a trajectory. Returns result dict.

    Returns:
        {"replayed": bool, "steps_done": int, "steps_total": int,
         "abort_reason": str or None, "tool_log": list[str]}
    """
    steps = traj["steps"]
    if not steps:
        return {"replayed": False, "abort_reason": "Empty trajectory"}

    # Step 1: Judge
    current = np.array(sct.grab(sct.monitors[1]))
    current_b64 = _np_to_png_b64(
        downsample_for_vlm(current, mouse_pos, screen_w, screen_h)[0][..., [2, 1, 0]]
    )
    traj_tool_names = list(set(s["name"] for s in steps))
    print(f"  [replay] evaluating ({len(steps)} steps, tools: {', '.join(traj_tool_names[:6])})...")
    judge = evaluate_replay(task, similar_text, traj_tool_names, current_b64, client, model)
    if not judge.get("can_replay"):
        return {"replayed": False, "abort_reason": f"Judge: {judge.get('reasoning', 'no')}"}

    print(f"  [replay] judge approved: {judge.get('reasoning', '')[:80]}")
    tool_log = []

    # Step 2: Execute step by step
    for i, step in enumerate(steps):
        name = step["name"]
        args = step["args"]

        print(f"  [replay] step {i+1}/{len(steps)}: {name} {json.dumps(args, ensure_ascii=False)[:80]}")

        # Execute the step
        try:
            from cua.tools import execute_tool
            result = execute_tool(name, args, sct, mouse_pos, screen_w, screen_h, current)
            tool_log.append(f"[replay] {name} {json.dumps(args, ensure_ascii=False)[:60]}")
        except Exception as e:
            return {
                "replayed": False, "steps_done": i, "steps_total": len(steps),
                "abort_reason": f"Step {i+1} execution error: {e}",
                "tool_log": tool_log,
            }

        # Update state from result
        if result.get("mouse_pos"):
            mouse_pos = result["mouse_pos"]
        if result.get("last_screenshot") is not None:
            current = result["last_screenshot"]

        # Verify this step (only if it has a reference screenshot)
        if step.get("screenshot_b64"):
            time.sleep(0.5)  # Let UI settle
            current = np.array(sct.grab(sct.monitors[1]))
            verification = verify_step(step, current, sct, mouse_pos, screen_w, screen_h, client, model)
            if not verification.get("ok"):
                print(f"  [replay] step {i+1} mismatch: {verification.get('reason', '')[:80]}")
                return {
                    "replayed": False, "steps_done": i, "steps_total": len(steps),
                    "abort_reason": f"Step {i+1} mismatch: {verification.get('reason', '')}",
                    "tool_log": tool_log,
                }

    # All steps done
    return {"replayed": True, "steps_done": len(steps), "steps_total": len(steps),
            "abort_reason": None, "tool_log": tool_log}

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
from cua.overlay import draw_cursor

TRAJ_DIR = Path(__file__).parent / "data" / "trajectories"
TRAJ_DIR.mkdir(parents=True, exist_ok=True)

SIMILARITY_REPLAY_THRESHOLD = 0.70  # Only consider replay above this similarity


def _safe_json(content: str) -> dict:
    """Parse JSON safely, with truncation repair fallback."""
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        content = content.rstrip()
        last_quote = content.rfind('"')
        if last_quote > 0 and not content.endswith("}"):
            content = content[:last_quote + 1] + '}'
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {}


# --- Recording ---

class TrajectoryRecorder:
    """Records tool calls + screenshots during a task execution."""

    def __init__(self, task: str):
        self.task = task
        self.steps: list[dict] = []  # [{name, args, screenshot_before_b64}]
        self._last_screenshot: np.ndarray | None = None

    def record_step(self, name: str, args: dict, screenshot_before: np.ndarray,
                    screen_w: int, screen_h: int, mouse_pos: tuple):
        """Record a tool call with the screenshot BEFORE execution."""
        downscaled, _, _ = downsample_for_vlm(screenshot_before, mouse_pos, screen_w, screen_h)
        rgb = downscaled[..., [2, 1, 0]]  # BGRA→RGB
        b64 = _np_to_png_b64(rgb)

        self.steps.append({
            "name": name,
            "args": args,
            "screenshot_b64": b64,
        })
        self._last_screenshot = screenshot_before

    def save(self) -> str | None:
        """Save trajectory to disk. Returns trajectory ID or None."""
        if len(self.steps) < 2:
            return None

        traj_id = hashlib.sha256(
            json.dumps([s["name"] for s in self.steps]).encode()
        ).hexdigest()[:12]

        # Save metadata (no screenshots in JSON — they're stored inline as b64)
        meta = {
            "task": self.task,
            "steps": [
                {"name": s["name"], "args": s["args"], "screenshot_b64": s["screenshot_b64"]}
                for s in self.steps
            ],
        }

        path = TRAJ_DIR / f"{traj_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        return traj_id


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
    files = list(TRAJ_DIR.glob("*.json"))
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
        from cua.learning import _get_skills_collection
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
            if sim >= 0.4:  # moderate threshold
                idx = int(results["ids"][0][0])
                return traj_map[traj_docs[idx]]
    except Exception:
        pass

    # Fallback: return the most recent trajectory
    newest = max(files, key=lambda f: f.stat().st_mtime)
    with open(newest, "r", encoding="utf-8") as f:
        return json.load(f)


def delete_trajectory(traj_id: str):
    """Delete a trajectory."""
    path = TRAJ_DIR / f"{traj_id}.json"
    if path.exists():
        path.unlink()


# --- Replay Judge ---

def evaluate_replay(task: str, similar_text: str, current_screenshot_b64: str,
                    client, model: str) -> dict:
    """Ask a bare LLM whether trajectory replay is appropriate.

    Returns {"can_replay": bool, "reasoning": str, "warnings": str}
    """
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": (
                    "You evaluate whether to replay a recorded automation trajectory. "
                    "Return JSON: {\"can_replay\": true/false, \"reasoning\": \"...\", \"warnings\": \"...\"}. "
                    "can_replay=true only if: the task is highly similar to past success, "
                    "the current screen state looks compatible with the first step, "
                    "and there are no obvious blockers (dialogs, login screens, different app open)."
                )},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": current_screenshot_b64}},
                    {"type": "text", "text": (
                        f"Task: {task}\n\n"
                        f"Similar past success:\n{similar_text}\n\n"
                        f"Look at the current screenshot. Is replay appropriate?"
                    )},
                ]},
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
            extra_body={"thinking": {"type": "disabled"}},
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
            extra_body={"thinking": {"type": "disabled"}},
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
    import mss as _mss_module
    current = np.array(sct.grab(sct.monitors[1]))
    current_b64 = _np_to_png_b64(
        downsample_for_vlm(current, mouse_pos, screen_w, screen_h)[0][..., [2, 1, 0]]
    )
    print(f"  [replay] evaluating ({len(steps)} steps)...")
    judge = evaluate_replay(task, similar_text, current_b64, client, model)
    if not judge.get("can_replay"):
        return {"replayed": False, "abort_reason": f"Judge: {judge.get('reasoning', 'no')}"}

    print(f"  [replay] judge approved: {judge.get('reasoning', '')[:80]}")
    tool_log = []

    # Step 2: Execute step by step
    for i, step in enumerate(steps):
        name = step["name"]
        args = step["args"]

        # Skip perception-only steps during replay
        from cua.agent import PERCEPTION_TOOLS
        if name in PERCEPTION_TOOLS:
            tool_log.append(f"[replay-skip] {name}")
            continue

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

        # Verify this step (only for state-changing tools)
        from cua.agent import VERIFY_TOOLS
        if name in VERIFY_TOOLS:
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

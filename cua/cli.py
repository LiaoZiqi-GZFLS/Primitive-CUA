"""CLI entry point for the CUA agent."""
import atexit
import os
import sys

from openai import OpenAI

# Suppress noisy threading shutdown errors from Playwright/ChromaDB
def _cleanup():
    import threading
    for t in threading.enumerate():
        if t.is_alive() and t != threading.current_thread():
            t.join(timeout=0.5)
atexit.register(_cleanup)

from cua.config import load_config
from cua.agent import run_task
from cua.learning import reflect_and_learn, save_pending, settle_pending


def main():
    """Run the CUA agent in an interactive CLI loop."""
    config = load_config()

    model = config.get("model", "kimi-k3")
    base_url = config.get("base_url", "https://api.moonshot.cn/v1")
    api_key = config.get("moonshot_api_key", "") or os.environ.get("MOONSHOT_API_KEY", "")

    client = OpenAI(api_key=api_key, base_url=base_url)

    # Settle any interrupted tasks from previous sessions
    settle_pending(client, model)

    print("=" * 60)
    print("CUA - Computer Use Agent")
    print(f"  LLM: {model}")
    print("  Modes: --record (capture)  --replay (fast)  --script (run .cua)")
    print("  Press Ctrl+C during a task to cancel it.")
    print("  Type a task to begin, or 'quit' to exit.")
    print("=" * 60)

    # Parse flags
    args = sys.argv[1:]
    record_mode = False
    replay_mode = False
    if "--record" in args:
        record_mode = True
        args.remove("--record")
    if "--replay" in args:
        replay_mode = True
        args.remove("--replay")
    script_mode = False
    if "--script" in args:
        script_mode = True
        args.remove("--script")

    # If task provided as command-line argument, run it once
    if args:
        task = " ".join(args)
        print(f"\nTask: {task}\n")
        if script_mode:
            print("  📜 SCRIPT mode active\n")
            _run_script(task, config, client, model)
        elif replay_mode:
            print("  ⏩  REPLAY mode active — using recorded templates...\n")
            _run_replay(task, config)
        else:
            if record_mode:
                print("  ⏺  RECORD mode active — capturing button templates...\n")
            _run_with_cancel(task, config, client, model, record_mode=record_mode)
        return

    # Interactive mode (flags persist across tasks)
    if record_mode:
        print("  ⏺  RECORD mode active for all interactive tasks.\n")
    if replay_mode:
        print("  ⏩  REPLAY mode active for all interactive tasks.\n")
    while True:
        try:
            task = input("\nTask > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not task:
            continue
        if task.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break

        print()
        if script_mode:
            _run_script(task, config, client, model)
        elif replay_mode:
            _run_replay(task, config)
        else:
            _run_with_cancel(task, config, client, model, record_mode=record_mode)


def _run_script(task: str, config: dict, client, model: str):
    """Run a .cua script with delegation to K3 on code 2."""
    from cua.script_runner import ScriptEngine
    try:
        engine = ScriptEngine(config)
        result = engine.run(task)  # task = script path
        print()
        if result.code == 0:
            print(f"✓ Script succeeded: {result.summary}")
        elif result.code == 1:
            print(f"✗ Script failed: {result.summary}")
        elif result.code == 2:
            print(f"↪ Script delegated to K3 Agent: {result.summary}")
            report = run_task(result.summary, config)
            _print_report(report)
    except KeyboardInterrupt:
        print("\n  ⏹ Script cancelled.\n")


def _calc_sim(query_vec, cached_hex: str) -> float:
    """Cosine similarity between query and cached embedding."""
    import numpy as np
    b = bytes.fromhex(cached_hex)
    v = np.frombuffer(b, dtype=np.float16)
    if len(v) < 384:
        v = np.pad(v, (0, 384 - len(v)))
    return float(np.dot(query_vec, v) /
                 (np.linalg.norm(query_vec) * np.linalg.norm(v) + 1e-8))


def _k3_decide(task: str, top3: list[tuple[str, float]],
                idx: dict, config: dict) -> dict | None:
    """K3 decides: pick existing, create new, or fallback to normal mode.

    Returns:
        {"action": "exec", "script_path": str}  — execute existing
        {"action": "create", "script": str, "name": str}  — execute new script
        {"action": "fallback"}  — use K3 Agent
        None on error
    """
    import json
    from openai import OpenAI
    from pathlib import Path
    from cua.recorder import CUA_SCRIPT_SYNTAX

    api_key = config.get("moonshot_api_key", "") or os.environ.get("MOONSHOT_API_KEY", "")
    if not api_key:
        return None

    model = config.get("model", "kimi-k3")
    base_url = config.get("base_url", "https://api.moonshot.cn/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)

    # Build candidate info with full script content
    script_dir = Path("cua/data/scripts")
    candidates_text = ""
    for i, (name, sim) in enumerate(top3, 1):
        desc = idx[name].get("desc", "")
        # Load full script, truncate if long
        sc_path = script_dir / name
        try:
            full = sc_path.read_text(encoding="utf-8")
            if len(full) > 1500:
                full = full[:1500] + "\n... [truncated, see full script]"
        except Exception:
            full = "(cannot read)"
        candidates_text += (
            f"### Script {i}: {name} (sim={sim:.3f})\n"
            f"```cua\n{full}\n```\n\n"
        )

    # Check element availability
    from cua.recorder import list_templates
    known_elements = {t.get("ocr_text", "") for t in list_templates()}
    missing_warning = ""
    for name, _ in top3:
        sc_path = script_dir / name
        try:
            content = sc_path.read_text(encoding="utf-8")
            refs = set()
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("click ") or line.startswith("dblclick "):
                    refs.add(line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else "")
            missing = [r for r in refs if r and not any(r in e or e in r for e in known_elements)]
            if missing:
                missing_warning += f"  WARNING: {name} references elements not in library: {', '.join(missing)}\n"
        except Exception:
            pass
    if missing_warning:
        missing_warning = (
            "These scripts reference elements NOT in the library. They will FAIL at runtime. "
            "Unless the task is extremely simple (like launch + wait), you MUST use fallback mode.\n\n"
            + missing_warning
        )

    system_prompt = (
        f"You are a CUA automation decision engine. Your job is to choose "
        f"how to execute a desktop automation task.\n\n"
        f"## Options\n"
        f"1. **exec N** — Execute an existing script (N = 1-{len(top3)})\n"
        f"2. **create** — Write a NEW script if existing ones don't fit but task is automatable\n"
        f"3. **fallback** — Use full K3 Agent (normal mode) when scripts won't work\n\n"
        f"## Decision rules\n"
        f"- If scripts reference missing elements → fallback (scripts WILL fail)\n"
        f"- If a script EXACTLY matches the task → exec it\n"
        f"- If scripts are close but need changes → create a new script\n"
        f"- If task is complex/novel/requires tool use beyond clicks → fallback\n"
        f"- Simple repetitive tasks (launch + click + type) are good for scripts\n\n"
        f"## Script Syntax\n{CUA_SCRIPT_SYNTAX}\n\n"
        f"Output JSON ONLY:\n"
        f'{{"action": "exec", "pick": <1-{len(top3)}>, "reason": "..."}}\n'
        f'{{"action": "create", "script": "<full .cua code>", "reason": "..."}}\n'
        f'{{"action": "fallback", "reason": "..."}}\n'
    )

    user_prompt = (
        f"Task: {task}\n\n"
        f"{candidates_text}"
        f"{missing_warning}"
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            reasoning_effort="max",
        )
        verdict = json.loads(resp.choices[0].message.content or "{}")
        action = verdict.get("action", "fallback")
        reason = verdict.get("reason", "")[:100]

        if action == "exec":
            pick = verdict.get("pick", 1)
            if 1 <= pick <= len(top3):
                print(f"  K3 exec {pick}: {top3[pick-1][0]} — {reason}")
                return {"action": "exec", "script_path": str(script_dir / top3[pick-1][0])}

        elif action == "create":
            script = verdict.get("script", "")
            if len(script) < 30:
                print(f"  K3 wanted to create but script too short — {reason}")
                return None
            print(f"  K3 creating new script — {reason}")
            # Validate the new script
            return _validate_and_save_new(script, task, config)

        else:
            print(f"  K3 fallback — {reason}")
            return {"action": "fallback"}

    except Exception as e:
        print(f"  K3 decide failed: {e}")
    return None


def _validate_and_save_new(script: str, task: str, config: dict) -> dict | None:
    """Validate K3-generated script, fix via K3 if needed, save and return path."""
    import tempfile, os as _os, json as _json, time
    from pathlib import Path
    from cua.script_runner import ScriptEngine
    from openai import OpenAI

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in task[:30])[:30]
    # Strip markdown
    if script.startswith("```"):
        script = script.split("\n", 1)[1] if "\n" in script else script
        if script.endswith("```"): script = script[:-3]
    script = script.strip()

    # Validation loop
    for round_n in range(3):
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".cua", delete=False, encoding="utf-8")
        tf.write(script); tf.close()
        engine = ScriptEngine()
        errors = engine.validate(tf.name)
        _os.unlink(tf.name)
        if not errors:
            break
        print(f"  New script validation round {round_n+1}: {len(errors)} errors, fixing...")
        api_key = config.get("moonshot_api_key", "") or os.environ.get("MOONSHOT_API_KEY", "")
        if not api_key:
            break
        model = config.get("model", "kimi-k3")
        base_url = config.get("base_url", "https://api.moonshot.cn/v1")
        client = OpenAI(api_key=api_key, base_url=base_url)
        try:
            fix_resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Fix these .cua syntax errors. Output ONLY the corrected script."},
                    {"role": "user", "content": f"Script:\n{script}\n\nErrors:\n" + "\n".join(errors)},
                ],
                reasoning_effort="max",
            )
            fixed = (fix_resp.choices[0].message.content or "").strip()
            if fixed.startswith("```"):
                fixed = fixed.split("\n", 1)[1] if "\n" in fixed else fixed
                if fixed.endswith("```"): fixed = fixed[:-3]
            fixed = fixed.strip()
            if len(fixed) > 30: script = fixed
        except Exception:
            break

    if len(script) < 30:
        return None

    # Save
    script_dir = Path(f"cua/data/scripts")
    script_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    path = script_dir / f"k3gen_{safe_name}_{ts}.cua"
    path.write_text(script, encoding="utf-8")
    print(f"  New script saved: {path}")
    return {"action": "exec", "script_path": str(path)}


def _k3_pick_script(task: str, top3: list[tuple[str, float]],
                    idx: dict, config: dict) -> str | None:
    """Legacy wrapper — calls _k3_decide."""
    result = _k3_decide(task, top3, idx, config)
    if result and result["action"] == "exec":
        return result["script_path"]
    return None


def _get_script_index() -> dict:
    """Load or build cache of .cua script descriptions + precomputed embeddings.

    Returns {script_name: {"desc": str, "vec": hex}}. Uses file mtime to
    detect changes — only rebuilds entries whose source file changed.
    """
    import json
    from pathlib import Path
    from cua.recorder import _embed_text
    import numpy as np

    script_dir = Path("cua/data/scripts")
    index_path = script_dir / "_index.json"
    cache = {}

    # Load existing cache
    if index_path.exists():
        try:
            cache = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    scripts = {s.name: s for s in script_dir.glob("*.cua")
               if not s.name.startswith("example_") and s.name != "_index.json"}

    changed = False
    for name, sc in scripts.items():
        mtime = int(sc.stat().st_mtime * 1000)
        if name in cache and cache[name].get("mtime", 0) == mtime:
            continue  # Unchanged — reuse cached vec

        # Read and embed
        try:
            first = sc.read_text(encoding="utf-8").split("\n")[0]
            desc = first.lstrip("# ").strip()[:100] or sc.stem
        except Exception:
            desc = sc.stem
        vec = _embed_text(desc[:200])
        cache[name] = {"desc": desc, "vec": vec.tobytes().hex(), "mtime": mtime}
        changed = True

    # Remove deleted scripts
    to_del = [n for n in cache if n not in scripts]
    for n in to_del:
        del cache[n]
        changed = True

    if changed:
        try:
            index_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    return cache


def _run_replay(task: str, config: dict):
    """Run a task in fast replay mode — K3 decides: script or normal agent."""
    from cua.recorder import _embed_text
    from cua.script_runner import ScriptEngine

    try:
        idx = _get_script_index()
        if idx:
            task_vec = _embed_text(task[:200])
            scored = sorted(
                ((_calc_sim(task_vec, entry["vec"]), name)
                 for name, entry in idx.items()),
                key=lambda x: -x[0]
            )
            top3 = [(name, sim) for sim, name in scored[:3] if sim > 0.10]

            if top3:
                print(f"  Candidates: {', '.join(f'{n}({s:.2f})' for n,s in top3)}")
                decision = _k3_decide(task, top3, idx, config)

                if decision and decision["action"] == "exec":
                    script_path = decision["script_path"]
                    engine = ScriptEngine(config)
                    result = engine.run(str(script_path))
                    if result.code == 2:
                        print("↪ Script returned 2 — delegating to K3 Agent")
                        report = run_task(result.summary, config)
                    else:
                        report = {
                            "success": result.code == 0,
                            "summary": result.summary,
                            "steps": [f"Script: {result.success_count}/{result.step_count} steps"],
                            "tokens": {"total": 0},
                        }
                    _print_report(report)
                    return
                elif decision and decision["action"] == "fallback":
                    pass  # Fall through to K3 Agent below

        # Fall back to K3 Agent
        report = run_task(task, config)
        _print_report(report)
    except KeyboardInterrupt:
        print("\n  ⏹ Replay cancelled.\n")


def _run_with_cancel(task: str, config: dict, client: OpenAI, model: str, record_mode: bool = False):
    """Run a task, handling Ctrl+C gracefully, then reflect."""
    if record_mode:
        from cua.recorder import start_macro
        start_macro()

    try:
        report = run_task(task, config, record_mode=record_mode)
        _print_report(report)

        # Post-task: save macro if recording
        if record_mode and report.get("success"):
            try:
                from cua.recorder import save_macro, list_templates
                import re
                # Find templates recorded during this session (most recent by timestamp)
                all_tmpl = sorted(list_templates(), key=lambda t: t.get("timestamp", 0), reverse=True)
                session_steps = all_tmpl[:len(report.get("steps", [])) + 10]  # rough estimate
                # Generate macro name from task
                name = re.sub(r'[^a-zA-Z0-9一-鿿_-]', '-', task[:40]).strip('-')[:40] or "unnamed"
                save_macro(name, task, session_steps[::-1])  # reverse to chronological
            except Exception:
                pass

        # Post-task reflection
        tool_log = report.pop("_tool_calls_log", [])
        reflect_and_learn(task, report, tool_log, client, model)
    except KeyboardInterrupt:
        print("\n  ⏹ Task cancelled.")
        print()
        try:
            from cua.agent import get_last_tool_log
            tool_log = get_last_tool_log()
            save_pending(task, "User cancelled (Ctrl+C)", tool_log)
        except Exception:
            pass


def _print_report(report: dict):
    """Print a formatted finish report."""
    print()
    if report["success"]:
        print("✓ Task completed successfully")
    else:
        print("✗ Task failed")

    print(f"Summary: {report['summary']}")

    steps = report.get("steps", [])
    if steps:
        print("Steps:")
        for i, step in enumerate(steps, 1):
            print(f"  {i}. {step}")

    tokens = report.get("tokens")
    if tokens:
        print(f"\nTokens: {tokens['total']:,} total ({tokens['prompt']:,} prompt + {tokens['completion']:,} completion)")

    print()


if __name__ == "__main__":
    main()

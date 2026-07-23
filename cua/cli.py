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


def _run_replay(task: str, config: dict):
    """Run a task in fast replay mode — searches .cua scripts by embedding."""
    from cua.recorder import _embed_text
    from cua.script_runner import ScriptEngine

    try:
        # Search .cua scripts by embedding similarity
        import numpy as np
        from pathlib import Path
        script_dir = Path("cua/data/scripts")
        scripts = list(script_dir.glob("*.cua")) if script_dir.exists() else []

        if scripts:
            task_vec = _embed_text(task[:200])
            best_s, best_script = 0, None
            for sc in scripts:
                try:
                    first = sc.read_text(encoding="utf-8").split("\n")[0]
                    desc = first.lstrip("# ").strip()[:100] or sc.stem
                except Exception:
                    desc = sc.stem
                sv = _embed_text(desc[:200])
                s = float(np.dot(task_vec, sv) /
                         (np.linalg.norm(task_vec) * np.linalg.norm(sv) + 1e-8))
                if s > best_s:
                    best_s, best_script = s, sc

            if best_script and best_s > 0.15:
                print(f"  📜 Script match: {best_script.name} (sim={best_s:.3f})\n")
                engine = ScriptEngine(config)
                result = engine.run(str(best_script))
                if result.code == 2:
                    print(f"↪ Script returned 2 — delegating to K3 Agent")
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

        # No matching script — fall back to K3 Agent
        print(f"  No matching script found — falling back to K3 Agent\n")
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

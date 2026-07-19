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
    print("  Press Ctrl+C during a task to cancel it.")
    print("  Type a task to begin, or 'quit' to exit.")
    print("=" * 60)

    # If task provided as command-line argument, run it once
    args = sys.argv[1:]
    if args:
        task = " ".join(args)
        print(f"\nTask: {task}\n")
        _run_with_cancel(task, config, client, model)
        return

    # Interactive mode
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
        _run_with_cancel(task, config, client, model)


def _run_with_cancel(task: str, config: dict, client: OpenAI, model: str):
    """Run a task, handling Ctrl+C gracefully, then reflect."""
    try:
        report = run_task(task, config)
        _print_report(report)

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

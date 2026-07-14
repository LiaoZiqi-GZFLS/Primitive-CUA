"""CLI entry point for the CUA agent."""
import sys

from cua.config import load_config
from cua.agent import run_task


def main():
    """Run the CUA agent in an interactive CLI loop."""
    config = load_config()

    model = config.get("model", "kimi-k2.6")
    print("=" * 60)
    print("CUA - Computer Use Agent")
    print(f"  LLM: {model}")
    print("  Type a task to begin, or 'quit' to exit.")
    print("=" * 60)

    # If task provided as command-line argument, run it once
    args = sys.argv[1:]
    if args:
        task = " ".join(args)
        print(f"\nTask: {task}\n")
        report = run_task(task, config)
        _print_report(report)
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
        report = run_task(task, config)
        _print_report(report)


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

    print()


if __name__ == "__main__":
    main()

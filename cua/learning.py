"""Post-task learning: reflect on what worked and what failed, persist across tasks."""
import json
import os
from pathlib import Path

LEARNINGS_FILE = Path(__file__).parent / "learnings.json"


def load_learnings() -> list[dict]:
    """Load all past learnings."""
    if LEARNINGS_FILE.exists():
        try:
            with open(LEARNINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_learnings(learnings: list[dict]):
    """Persist learnings to disk (keep last 50)."""
    LEARNINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Keep only last 50 entries
    if len(learnings) > 50:
        learnings = learnings[-50:]
    with open(LEARNINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(learnings, f, ensure_ascii=False, indent=2)


def reflect_and_learn(
    task: str,
    report: dict,
    tool_calls_log: list[str],
    client,
    model: str,
):
    """After task completion, reflect and extract learnings.

    Args:
        task: Original task description
        report: Finish report (success, summary, steps)
        tool_calls_log: List of formatted tool call strings from the run
        client: OpenAI client
        model: Model name
    """
    if client is None:
        return

    success = report.get("success", False)
    summary = report.get("summary", "")
    steps = report.get("steps", [])
    tokens = report.get("tokens", {})

    # Build a concise execution trace
    trace = "\n".join(tool_calls_log[-30:])  # last 30 calls
    if len(tool_calls_log) > 30:
        trace = f"... ({len(tool_calls_log) - 30} more calls)\n" + trace

    outlook = "success" if success else "failure"

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You analyze completed desktop automation tasks and extract "
                        "actionable learnings for future runs. Output valid JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Task: {task}\n"
                        f"Outcome: {outlook}\n"
                        f"Summary: {summary}\n"
                        f"Steps taken: {json.dumps(steps, ensure_ascii=False)}\n"
                        f"Tokens used: {json.dumps(tokens)}\n\n"
                        f"Tool execution trace:\n{trace}\n\n"
                        f"Extract up to 3 concise, actionable learnings. "
                        f"For each learning, include:\n"
                        f"- type: 'success_pattern' or 'failure_fix'\n"
                        f"- context: short description of the scenario\n"
                        f"- learning: the specific actionable insight\n"
                        f"- tools: relevant tool names\n\n"
                        f"Only include learnings that would help a future run of a similar task. "
                        f"Be specific — not 'be more careful' but 'when clicking taskbar icons, "
                        f"use magnifier first since they are small targets'."
                    ),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "learnings",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "learnings": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["success_pattern", "failure_fix"]},
                                        "context": {"type": "string"},
                                        "learning": {"type": "string"},
                                        "tools": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                    "required": ["type", "context", "learning", "tools"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["learnings"],
                        "additionalProperties": False,
                    },
                },
            },
            max_tokens=512,
            extra_body={"thinking": {"type": "disabled"}},
        )

        result = json.loads(resp.choices[0].message.content)
        new_learnings = result.get("learnings", [])

        if new_learnings:
            all_learnings = load_learnings()
            for l in new_learnings:
                l["task"] = task[:80]
                l["outcome"] = outlook
            all_learnings.extend(new_learnings)
            save_learnings(all_learnings)
            print(f"  [learn] saved {len(new_learnings)} new learning(s)")

    except Exception as e:
        print(f"  [learn] reflection failed: {e}")


def get_learnings_prompt() -> str:
    """Get a prompt snippet with relevant past learnings (last 10, condensed)."""
    all_learnings = load_learnings()
    if not all_learnings:
        return ""

    # Take last 15 and format
    recent = all_learnings[-15:]
    lines = ["\n## Past Learnings (from previous tasks)\n"]
    for l in recent:
        icon = "✓" if l["type"] == "success_pattern" else "✗"
        lines.append(f"- {icon} [{l['context']}] {l['learning']}")

    return "\n".join(lines)

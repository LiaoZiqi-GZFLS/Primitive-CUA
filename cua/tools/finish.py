"""Finish tool: end the current task round with a report."""

FINISH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "finish",
        "description": "End the current task. Call this when the task is complete or cannot be completed. Provide a success/failure status, a summary of what was accomplished, and a list of steps taken.",
        "parameters": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether the task was completed successfully",
                },
                "summary": {
                    "type": "string",
                    "description": "Concise summary of what was accomplished or why it failed",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of key actions taken, in order",
                },
            },
            "required": ["success", "summary", "steps"],
        },
    },
}


FINISH_SENTINEL = "__CUA_FINISH__"


def execute_finish(success: bool, summary: str, steps: list[str]) -> dict:
    """Return finish report. The agent loop detects FINISH_SENTINEL to exit."""
    return {
        "content": [
            {"type": "text", "text": FINISH_SENTINEL}
        ],
        "_finish_report": {
            "success": success,
            "summary": summary,
            "steps": steps,
        },
    }

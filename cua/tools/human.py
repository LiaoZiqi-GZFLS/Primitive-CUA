"""Human help tool: pause agent and request user assistance."""


HUMAN_HELP_SCHEMA = {
    "type": "function",
    "function": {
        "name": "request_human_help",
        "description": "Pause and request help from the human user. Use when you encounter a login page, CAPTCHA, UAC permission dialog, or any situation you cannot handle autonomously. Describe what you need and wait for the user's response.",
        "parameters": {
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "What you need the human to do, e.g. 'Please log in to the website with your credentials', 'Please click Allow on the UAC dialog', 'Please solve the CAPTCHA and press Enter when done'",
                }
            },
            "required": ["request"],
        },
    },
}


def execute_human_help(request: str) -> dict:
    """Pause and ask the human for help. Returns their response."""
    print()
    print("=" * 50)
    print("  Agent needs your help:")
    print(f"  {request}")
    print("=" * 50)
    print()

    try:
        response = input("  Your response (Enter to continue): ").strip()
    except (EOFError, KeyboardInterrupt):
        response = "User skipped."

    print()
    return {
        "content": [
            {"type": "text", "text": f"Human response: {response if response else '(no input, user pressed Enter)'}"}
        ],
        "mouse_pos": None,
        "last_screenshot": None,
    }

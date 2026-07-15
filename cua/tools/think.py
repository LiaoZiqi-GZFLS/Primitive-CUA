"""Think tool: prompts the agent to pause, reflect, and plan."""

THINK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "think",
        "description": "Pause to reflect on progress, analyze the current situation, and plan the next steps. Call this when you're unsure what to do next, when you've completed a sub-task and need to decide the next move, or when you need to carefully analyze the screen before acting. This tool does NOT perform any action — it just gives you space to think.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

THINK_PROMPT = """Take a step back and think carefully:

1. **Current state**: What do you see on the screen right now? What is the current situation?
2. **Progress so far**: What have you already accomplished toward the task? What sub-tasks are complete?
3. **What's next**: What is the immediate next action you should take? Be specific.
4. **Plan**: Outline the remaining steps needed to complete the task.
5. **Obstacles**: Are there any challenges or things that aren't working? How can you work around them?

After reflecting, call the appropriate tool to take your next action. Do NOT call think() again immediately — take an action based on your reflection."""


def execute_think() -> dict:
    """Return a reflection prompt to guide the model's next action."""
    from cua.tools.utility import get_notes
    notes = get_notes()
    prompt = THINK_PROMPT
    if notes != "(no notes yet)":
        prompt = f"Your notes so far:\n{notes}\n\n{THINK_PROMPT}"
    return {
        "content": [
            {"type": "text", "text": prompt}
        ],
        "mouse_pos": None,
        "last_screenshot": None,
    }

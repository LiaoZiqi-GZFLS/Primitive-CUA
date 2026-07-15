"""Think tool: prompts the agent to pause, reflect, and plan."""

# Set by agent.py at task start with similar past learnings from ChromaDB
_first_think_extra = ""


def set_think_context(similar_text: str):
    """Set extra context for the next think() call (called once at task start)."""
    global _first_think_extra
    _first_think_extra = similar_text


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

    global _first_think_extra
    extra = _first_think_extra
    _first_think_extra = ""  # only inject once

    notes = get_notes()
    prompt = ""
    if extra:
        prompt += f"Relevant past experience for this task:\n{extra}\n\n"
    if notes != "(no notes yet)":
        prompt += f"Your notes so far:\n{notes}\n\n"
    prompt += THINK_PROMPT

    return {
        "content": [
            {"type": "text", "text": prompt}
        ],
        "mouse_pos": None,
        "last_screenshot": None,
    }

"""Utility tools: wait, file_read, file_write, note."""
import os
import time


# --- wait ---

WAIT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "wait",
        "description": "Wait for a specified number of seconds. Use this to let the system settle after launching apps, loading pages, or before taking a screenshot. Saves tokens compared to repeatedly calling screenshot to check if something loaded.",
        "parameters": {
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "number",
                    "description": "Seconds to wait (0.5-10.0)",
                }
            },
            "required": ["seconds"],
        },
    },
}


def execute_wait(seconds: float) -> dict:
    """Wait for a duration."""
    seconds = max(0.5, min(10.0, seconds))
    time.sleep(seconds)
    return {
        "content": [{"type": "text", "text": f"Waited {seconds:.1f}s."}],
        "mouse_pos": None,
        "last_screenshot": None,
    }


# --- file_read ---

FILE_READ_SCHEMA = {
    "type": "function",
    "function": {
        "name": "file_read",
        "description": "Read the contents of a file. Use this to check file content without opening the file in a GUI app. Returns the full text content.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read (absolute or relative to current directory)",
                }
            },
            "required": ["path"],
        },
    },
}


def execute_file_read(path: str) -> dict:
    """Read file content."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > 2000:
            content = content[:2000] + f"\n... (truncated, {len(content)} chars total)"
        return {
            "content": [{"type": "text", "text": f"File '{path}':\n{content}"}],
            "mouse_pos": None,
            "last_screenshot": None,
        }
    except FileNotFoundError:
        return {
            "content": [{"type": "text", "text": f"File not found: {path}"}],
            "mouse_pos": None,
            "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error reading file: {e}"}],
            "mouse_pos": None,
            "last_screenshot": None,
        }


# --- file_write ---

FILE_WRITE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "file_write",
        "description": "Write content to a file. Creates the file if it doesn't exist, overwrites if it does. For appending, use note() instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write (absolute or relative to current directory)",
                },
                "content": {
                    "type": "string",
                    "description": "Text content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
    },
}


def execute_file_write(path: str, content: str) -> dict:
    """Write content to a file."""
    try:
        # Ensure parent directory exists
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {
            "content": [{"type": "text", "text": f"Written {len(content)} chars to '{path}'."}],
            "mouse_pos": None,
            "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error writing file: {e}"}],
            "mouse_pos": None,
            "last_screenshot": None,
        }


# --- note (persistent notepad) ---

_notepad: list[str] = []


NOTE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "note",
        "description": "Write a note to your persistent notepad. Use this to remember important information across actions — window positions, icon locations, file paths, task progress. Notes persist for the entire task and are shown when you call think(). Call with no arguments to read all notes.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Note text to save. If empty or omitted, returns all current notes.",
                }
            },
            "required": [],
        },
    },
}


def clear_notes():
    """Clear all notes (called at task start)."""
    _notepad.clear()


def get_notes() -> str:
    """Get all notes as a formatted string."""
    if not _notepad:
        return "(no notes yet)"
    return "\n".join(f"{i+1}. {n}" for i, n in enumerate(_notepad))


def execute_note(text: str = "") -> dict:
    """Add or read notes."""
    if text:
        _notepad.append(text)
        return {
            "content": [{"type": "text", "text": f"Note #{len(_notepad)} saved: {text[:100]}"}],
            "mouse_pos": None,
            "last_screenshot": None,
        }
    else:
        return {
            "content": [{"type": "text", "text": get_notes()}],
            "mouse_pos": None,
            "last_screenshot": None,
        }


# --- Trajectory management ---

DELETE_TRAJECTORY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "delete_trajectory",
        "description": "Delete a saved replay trajectory. Use when replay fails due to an outdated or broken trajectory — the next successful task run will save a fresh one.",
        "parameters": {
            "type": "object",
            "properties": {
                "traj_id": {"type": "string", "description": "Trajectory ID to delete"},
            },
            "required": ["traj_id"],
        },
    },
}


def execute_delete_trajectory(traj_id: str) -> dict:
    from cua.replay import delete_trajectory
    delete_trajectory(traj_id)
    return {
        "content": [{"type": "text", "text": f"Trajectory deleted: {traj_id}"}],
        "mouse_pos": None, "last_screenshot": None,
    }

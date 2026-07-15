"""UI Automation tools: inspect, click, set_value, get_text via Windows UIA."""
import time

import uiautomation as uia


def _foreground_control():
    """Get the foreground window's UIA control."""
    return uia.GetForegroundControl()


def _find_control(name: str, max_depth: int = 4):
    """Find a control by name (partial match, case-insensitive) in the foreground window."""
    fg = _foreground_control()
    if fg is None:
        return None

    name_lower = name.lower()

    def search(ctrl, depth):
        if depth > max_depth:
            return None
        ctrl_name = (ctrl.Name or "").lower()
        if name_lower in ctrl_name:
            return ctrl
        for child in ctrl.GetChildren():
            result = search(child, depth + 1)
            if result:
                return result
        return None

    return search(fg, 0)


def _format_control(ctrl, depth=0):
    """Format a control into a readable tree line."""
    indent = "  " * depth
    info = f"{ctrl.ControlTypeName}"
    if ctrl.Name:
        info += f" '{ctrl.Name}'"
    if ctrl.AutomationId:
        info += f" #{ctrl.AutomationId}"
    rect = ctrl.BoundingRectangle
    if rect:
        info += f" ({rect.left}, {rect.top}, {rect.width()}x{rect.height()})"
    return f"{indent}{info}"


# --- Schemas ---

UIA_INSPECT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "uia_inspect",
        "description": "Inspect the UI controls of the current foreground window. Returns a tree of controls with their names, types, and positions. Use this to understand the structure of native Windows apps, Office programs, and dialogs before interacting with them. Much faster and more precise than screenshot-based coordinate clicking.",
        "parameters": {
            "type": "object",
            "properties": {
                "depth": {
                    "type": "integer",
                    "description": "How deep to traverse the control tree (1-5, default 3). Higher = more detail.",
                }
            },
            "required": [],
        },
    },
}


UIA_CLICK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "uia_click",
        "description": "Click a UI control by its name (partial match, case-insensitive) in the current foreground window. Use uia_inspect first to see available controls. Works on buttons, menu items, tabs, checkboxes — any clickable control. Much more reliable than coordinate-based clicking for native apps.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Control name to click (e.g. 'OK', 'Cancel', 'File', 'Bold')"},
            },
            "required": ["name"],
        },
    },
}


UIA_SET_VALUE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "uia_set_value",
        "description": "Set the value of an input/editable control by its name. Use for typing into native app text fields, setting cell values in Excel, filling form fields in dialogs. Supports Chinese text. Use uia_inspect first to find the control name.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Control name to target (e.g. 'Document', 'File name:', 'Cell')"},
                "value": {"type": "string", "description": "The text value to set"},
            },
            "required": ["name", "value"],
        },
    },
}


UIA_GET_TEXT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "uia_get_text",
        "description": "Read the text/value of a UI control by its name. Use to read document content, cell values, label text, status messages. Use uia_inspect first to find the control name.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Control name to read from (e.g. 'Document', 'Status', 'Cell')"},
            },
            "required": ["name"],
        },
    },
}


# --- Executors ---

def execute_uia_inspect(depth: int = 3) -> dict:
    """Dump control tree of foreground window."""
    try:
        depth = max(1, min(5, depth))
        fg = _foreground_control()
        if fg is None:
            return {
                "content": [{"type": "text", "text": "No foreground window found."}],
                "mouse_pos": None, "last_screenshot": None,
            }

        lines = [f"Active window: {fg.Name}"]

        def walk(ctrl, d):
            if d > depth:
                return
            lines.append(_format_control(ctrl, d))
            for child in ctrl.GetChildren():
                walk(child, d + 1)

        walk(fg, 0)

        return {
            "content": [{"type": "text", "text": "\n".join(lines[:120])}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"UIA inspect failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


def execute_uia_click(name: str) -> dict:
    """Click a control by name."""
    try:
        ctrl = _find_control(name)
        if ctrl is None:
            return {
                "content": [{"type": "text", "text": f"Control '{name}' not found. Try uia_inspect to see available controls."}],
                "mouse_pos": None, "last_screenshot": None,
            }

        # Click() often throws COM errors even when the click actually succeeds.
        # Try Click() first, fall back to InvokePattern. Ignore exceptions.
        try:
            ctrl.Click()
        except Exception:
            try:
                inv = ctrl.GetInvokePattern()
                inv.Invoke()
            except Exception:
                pass

        time.sleep(0.2)

        return {
            "content": [{"type": "text", "text": f"Clicked: {ctrl.Name} ({ctrl.ControlTypeName})"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"UIA click failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


def execute_uia_set_value(name: str, value: str) -> dict:
    """Set value of an editable control."""
    try:
        ctrl = _find_control(name)
        if ctrl is None:
            return {
                "content": [{"type": "text", "text": f"Control '{name}' not found. Try uia_inspect to see available controls."}],
                "mouse_pos": None, "last_screenshot": None,
            }

        # Try ValuePattern first (most reliable)
        try:
            vp = ctrl.GetValuePattern()
            vp.SetValue(value)
            time.sleep(0.1)
            return {
                "content": [{"type": "text", "text": f"Set value of '{ctrl.Name}': '{value}'"}],
                "mouse_pos": None, "last_screenshot": None,
            }
        except Exception:
            pass

        # Fallback: click to focus, then paste
        ctrl.Click()
        time.sleep(0.1)
        ctrl.SendKeys("{Ctrl}a")
        import pyperclip
        pyperclip.copy(value)
        ctrl.SendKeys("{Ctrl}v")
        time.sleep(0.1)

        return {
            "content": [{"type": "text", "text": f"Set value of '{ctrl.Name}' via paste: '{value}'"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"UIA set_value failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


def execute_uia_get_text(name: str) -> dict:
    """Read text/value from a control."""
    try:
        ctrl = _find_control(name)
        if ctrl is None:
            return {
                "content": [{"type": "text", "text": f"Control '{name}' not found. Try uia_inspect to see available controls."}],
                "mouse_pos": None, "last_screenshot": None,
            }

        text = ctrl.Name or ""
        try:
            vp = ctrl.GetValuePattern()
            text = vp.Value or text
        except Exception:
            pass

        return {
            "content": [{"type": "text", "text": f"Text of '{ctrl.Name}': {text}"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"UIA get_text failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


# --- Run dialog ---

RUN_COMMAND_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_command",
        "description": "Open the Windows Run dialog (Win+R), type a command, and press Enter. Use for: opening paths ('C:\\Users'), launching executables ('cmd', 'notepad', 'control'), opening URLs, running shell commands. Faster than Start menu search for system commands.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to run — path, executable name, URL, or shell command",
                },
            },
            "required": ["command"],
        },
    },
}


def execute_run_command(command: str) -> dict:
    """Win+R, type command, Enter."""
    import pyautogui
    import pyperclip

    try:
        pyautogui.hotkey("win", "r")
        time.sleep(0.2)

        # Use paste for non-ASCII, typewrite for ASCII
        if command.isascii():
            pyautogui.typewrite(command, interval=0.02)
        else:
            pyperclip.copy(command)
            time.sleep(0.05)
            pyautogui.hotkey("ctrl", "v")

        time.sleep(0.2)
        # Press Enter twice — Chinese IME may consume the first one
        pyautogui.press("enter")
        time.sleep(0.1)
        pyautogui.press("enter")
        time.sleep(0.5)

        return {
            "content": [{"type": "text", "text": f"Ran: {command}"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Run command failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }

UIA_CLICK_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

UIA_SET_VALUE_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

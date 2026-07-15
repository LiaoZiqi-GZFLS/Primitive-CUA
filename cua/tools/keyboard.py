"""Keyboard input tool: type_keys."""
import time
import pyautogui
from cua.tools.mouse import _grab_screen, _denorm
from cua.tools.screenshot import _np_to_jpeg_b64
from cua.overlay import draw_cursor

# All pyautogui-recognized special key names (lowercase for matching)
SPECIAL_KEYS = {
    "ctrl", "alt", "shift", "win", "cmd", "command",
    "enter", "return", "tab", "escape", "esc",
    "backspace", "delete", "del", "insert", "ins",
    "up", "down", "left", "right",
    "home", "end", "pageup", "pagedown",
    "space", "spacebar",
    "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
    "capslock", "numlock", "scrolllock",
    "printscreen", "prtsc",
    "volumeup", "volumedown", "volumemute",
    "playpause", "stop", "prevtrack", "nexttrack",
}

# Keys that can act as modifiers in combos (must be held while pressing another key)
MODIFIER_KEYS = {"ctrl", "alt", "shift", "win", "cmd", "command"}

TYPE_KEYS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "type_keys",
        "description": (
            "Type text or press keys. Pass a plain string to type text character by character. "
            "Pass a special key name (enter, tab, escape, backspace, delete, space, up, down, left, right, "
            "f1-f12, ctrl, alt, shift, win, home, end, pageup, pagedown) to press that single key. "
            "Pass a combo like 'ctrl+c' or 'alt+tab' to press keys together. "
            "Key names are case-insensitive. Returns a new screenshot after typing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keys": {
                    "type": "string",
                    "description": (
                        "What to type. Three forms: "
                        "1) Plain text like 'hello world' — typed character by character. "
                        "2) Single special key like 'enter', 'tab', 'escape', 'backspace', 'f5' — pressed once. "
                        "3) Key combo like 'ctrl+c', 'alt+tab', 'win+r' — keys pressed together. "
                        "Available special keys: ctrl, alt, shift, win, enter, tab, escape, backspace, "
                        "delete, space, up, down, left, right, home, end, pageup, pagedown, "
                        "f1-f12, capslock, numlock, printscreen, volumeup, volumedown."
                    ),
                },
                "repeat": {
                    "type": "integer",
                    "description": "Number of times to repeat the key press (1-50, default 1). Only applies to special keys and combos, not plain text. Use for multi-delete, multi-backspace, etc.",
                },
            },
            "required": ["keys"],
        },
    },
}


def _parse_keys(keys: str):
    """Parse a keys string into (action, args).

    Returns:
        ("text", str)       — typewrite this text
        ("key", str)        — press this single key
        ("hotkey", list)    — press these keys together
    """
    key = keys.strip()

    # Check if it's a key combo like "ctrl+c" or "alt+tab"
    if "+" in key:
        parts = [k.strip().lower() for k in key.split("+")]
        if len(parts) >= 2:
            # Modifiers (all but last) must be known modifier keys
            modifiers_ok = all(
                p in MODIFIER_KEYS for p in parts[:-1]
            )
            if modifiers_ok:
                return ("hotkey", parts)
        # If modifiers aren't valid, fall through — might still be text with literal +

    # Check if it's a single special key
    if key.lower() in SPECIAL_KEYS:
        return ("key", key.lower())

    # Otherwise, type as text
    return ("text", keys)


def execute_type_keys(
    keys, sct, mouse_pos: tuple, screen_w: int, screen_h: int, repeat: int = 1
) -> dict:
    """Type text or press key(s)."""
    repeat = max(1, min(50, repeat))

    if isinstance(keys, list):
        for _ in range(repeat):
            pyautogui.hotkey(*keys)
        desc = "+".join(keys)
    elif isinstance(keys, str):
        action, arg = _parse_keys(keys)
        if action == "key":
            for _ in range(repeat):
                pyautogui.press(arg)
            desc = f"[{arg}]" + (f" x{repeat}" if repeat > 1 else "")
        elif action == "hotkey":
            for _ in range(repeat):
                pyautogui.hotkey(*arg)
            desc = "+".join(arg) + (f" x{repeat}" if repeat > 1 else "")
        else:
            pyautogui.typewrite(arg, interval=0.02)
            desc = repr(arg)
    else:
        desc = str(keys)

    time.sleep(0.15)

    px = _denorm(mouse_pos[0], screen_w)
    py = _denorm(mouse_pos[1], screen_h)
    img = _grab_screen(sct)
    annotated = draw_cursor(img, px, py, scale=1.0)

    img_rgb = img[..., [2, 1, 0]]
    annotated_rgb = annotated[..., [2, 1, 0]]

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img_rgb)}},
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated_rgb)}},
            {"type": "text", "text": f"Typed: {desc}"},
        ],
        "mouse_pos": mouse_pos,
        "last_screenshot": img,
    }

"""Clipboard tools: read_clipboard and paste_text."""
import time
import pyperclip
import pyautogui

from cua.tools.mouse import _grab_screen, _denorm
from cua.tools.screenshot import _np_to_jpeg_b64
from cua.overlay import draw_cursor


READ_CLIPBOARD_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_clipboard",
        "description": "Read the current text content from the system clipboard. Returns the text. Use this to check what was just copied.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


PASTE_TEXT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "paste_text",
        "description": "Paste text directly at the current cursor position by writing to clipboard and pressing Ctrl+V. Much faster than type_keys for long text. Use type_keys for short text or special keys, paste_text for long text.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to paste at the current cursor position",
                }
            },
            "required": ["text"],
        },
    },
}

PASTE_TEXT_SCHEMA["function"]["parameters"]["properties"]["verify"] = {
    "type": "boolean",
    "description": "Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.",
}


def execute_read_clipboard() -> dict:
    """Read text from system clipboard."""
    try:
        text = pyperclip.paste()
    except Exception as e:
        text = f"Error reading clipboard: {e}"

    return {
        "content": [
            {"type": "text", "text": f"Clipboard content: {text}" if text else "Clipboard is empty."}
        ],
        "mouse_pos": None,
        "last_screenshot": None,
    }


def execute_paste_text(
    text: str, sct, mouse_pos: tuple, screen_w: int, screen_h: int
) -> dict:
    """Copy text to clipboard and paste via Ctrl+V."""
    pyperclip.copy(text)
    time.sleep(0.05)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.15)

    px = _denorm(mouse_pos[0], screen_w)
    py = _denorm(mouse_pos[1], screen_h)
    img = _grab_screen(sct)
    annotated = draw_cursor(img, px, py, scale=1.0)

    img_rgb = img[..., [2, 1, 0]]
    annotated_rgb = annotated[..., [2, 1, 0]]

    preview = text[:80] + "..." if len(text) > 80 else text
    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img_rgb)}},
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated_rgb)}},
            {"type": "text", "text": f"Pasted ({len(text)} chars): {preview}"},
        ],
        "mouse_pos": mouse_pos,
        "last_screenshot": img,
    }

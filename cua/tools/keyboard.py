"""Keyboard input tool: type_keys."""
import time
import pyautogui
from cua.tools.mouse import _grab_screen, _denorm
from cua.tools.screenshot import _np_to_jpeg_b64
from cua.overlay import draw_cursor


TYPE_KEYS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "type_keys",
        "description": "Type text or press key combinations. Pass a string to type text character by character. Pass an array of key names to press them together as a combo (e.g. ['ctrl', 'c']). Returns a new screenshot after typing.",
        "parameters": {
            "type": "object",
            "properties": {
                "keys": {
                    "description": "Text string to type, or array of key names for a key combination. Key names: ctrl, alt, shift, enter, tab, escape, backspace, delete, up, down, left, right, f1-f12, win, pageup, pagedown, home, end, space.",
                }
            },
            "required": ["keys"],
        },
    },
}


def execute_type_keys(
    keys, sct, mouse_pos: tuple, screen_w: int, screen_h: int
) -> dict:
    """Type text or press key combination."""
    if isinstance(keys, str):
        pyautogui.typewrite(keys, interval=0.02)
    elif isinstance(keys, list):
        pyautogui.hotkey(*keys)

    time.sleep(0.15)

    px = _denorm(mouse_pos[0], screen_w)
    py = _denorm(mouse_pos[1], screen_h)
    img = _grab_screen(sct)
    annotated = draw_cursor(img, px, py, scale=1.0)

    img_rgb = img[..., [2, 1, 0]]
    annotated_rgb = annotated[..., [2, 1, 0]]

    desc = repr(keys) if isinstance(keys, str) else "+".join(keys)
    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img_rgb)}},
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated_rgb)}},
            {"type": "text", "text": f"Typed: {desc}"},
        ],
        "mouse_pos": mouse_pos,
        "last_screenshot": img,
    }

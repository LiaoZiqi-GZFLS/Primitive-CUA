"""Windows management tools: list_windows, focus_window, launch_app."""
import json
import subprocess
import time

import pyautogui
import pygetwindow as gw

from cua.tools.mouse import _grab_screen, _denorm
from cua.tools.screenshot import _np_to_jpeg_b64
from cua.overlay import draw_cursor


LIST_WINDOWS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_windows",
        "description": "List all open windows with their titles, visibility status, and screen position. Use this to find out what applications are running and where they are on screen.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


FOCUS_WINDOW_SCHEMA = {
    "type": "function",
    "function": {
        "name": "focus_window",
        "description": "Bring a window to the foreground by matching its title (partial match, case-insensitive). Use list_windows first to see available window titles.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Part of the window title to match (e.g. 'Notepad', 'Chrome', '微信')",
                }
            },
            "required": ["title"],
        },
    },
}


LAUNCH_APP_SCHEMA = {
    "type": "function",
    "function": {
        "name": "launch_app",
        "description": "Launch an application by name. Uses Windows Start menu search (Win key, type name, Enter). Common names: 'notepad', 'chrome', 'edge', 'calculator', 'cmd', 'explorer'.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Application name as you would type in the Start menu search (e.g. 'Notepad', 'Google Chrome', '微信')",
                }
            },
            "required": ["name"],
        },
    },
}


def execute_list_windows() -> dict:
    """List all open windows with metadata (normalized coordinates)."""
    try:
        windows = gw.getAllWindows()
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error listing windows: {e}"}],
            "mouse_pos": None,
            "last_screenshot": None,
        }

    sw, sh = pyautogui.size()
    result = []
    for w in windows:
        title = w.title.strip()
        if not title:
            continue
        result.append({
            "title": title,
            "visible": w.visible,
            "minimized": w.isMinimized,
            "maximized": w.isMaximized,
            "x": round(max(0, min(1, w.left / sw)), 4),
            "y": round(max(0, min(1, w.top / sh)), 4),
            "width": round(max(0, min(1, w.width / sw)), 4),
            "height": round(max(0, min(1, w.height / sh)), 4),
        })

    return {
        "content": [
            {"type": "text", "text": json.dumps(result, ensure_ascii=False)}
        ],
        "mouse_pos": None,
        "last_screenshot": None,
    }


def execute_focus_window(
    title: str, sct, mouse_pos: tuple, screen_w: int, screen_h: int
) -> dict:
    """Focus a window by title match."""
    matches = gw.getWindowsWithTitle(title)
    if not matches:
        return {
            "content": [
                {"type": "text", "text": f"No window found matching '{title}'. Use list_windows to see available windows."}
            ],
            "mouse_pos": mouse_pos,
            "last_screenshot": None,
        }

    win = matches[0]
    try:
        if win.isMinimized:
            win.restore()
        win.activate()
        time.sleep(0.3)
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Error focusing window: {e}"}],
            "mouse_pos": mouse_pos,
            "last_screenshot": None,
        }

    # Take screenshot to confirm
    img = _grab_screen(sct)
    px = _denorm(mouse_pos[0], screen_w)
    py = _denorm(mouse_pos[1], screen_h)
    annotated = draw_cursor(img, px, py, scale=1.0)

    img_rgb = img[..., [2, 1, 0]]
    annotated_rgb = annotated[..., [2, 1, 0]]

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img_rgb)}},
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated_rgb)}},
            {"type": "text", "text": f"Focused window: {win.title}"},
        ],
        "mouse_pos": mouse_pos,
        "last_screenshot": img,
    }


def execute_launch_app(
    name: str, sct, mouse_pos: tuple, screen_w: int, screen_h: int
) -> dict:
    """Launch an app via Start menu search. Uses clipboard paste for Chinese names."""
    import pyperclip

    # Win key to open Start
    pyautogui.hotkey("win")
    time.sleep(0.3)

    # Type or paste the app name
    if name.isascii():
        pyautogui.typewrite(name, interval=0.03)
    else:
        # Chinese/non-ASCII: use clipboard paste
        pyperclip.copy(name)
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
    time.sleep(0.5)

    # Press Enter twice — Chinese IME may consume the first one
    pyautogui.press("enter")
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(1.0)

    img = _grab_screen(sct)
    px = _denorm(mouse_pos[0], screen_w)
    py = _denorm(mouse_pos[1], screen_h)
    annotated = draw_cursor(img, px, py, scale=1.0)

    img_rgb = img[..., [2, 1, 0]]
    annotated_rgb = annotated[..., [2, 1, 0]]

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img_rgb)}},
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated_rgb)}},
            {"type": "text", "text": f"Launched: {name}"},
        ],
        "mouse_pos": mouse_pos,
        "last_screenshot": img,
    }

FOCUS_WINDOW_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

LAUNCH_APP_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

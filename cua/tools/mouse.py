"""Virtual mouse control tools: set_mouse, click, drag."""
import json
import time
from typing import Any

import numpy as np
import pyautogui

from cua.tools.screenshot import _np_to_jpeg_b64

# Fail-safe: move to corner to abort
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


def _denorm(x: float, dim: int) -> int:
    """Convert normalized coordinate to pixel, clamped."""
    return max(0, min(dim - 1, round(x * dim)))


def _norm(px: int, dim: int) -> float:
    """Convert pixel to normalized coordinate."""
    return round(px / dim, 4)


def _grab_screen(sct):
    """Capture screen via mss, return BGRA numpy array."""
    return np.array(sct.grab(sct.monitors[1]))


SET_MOUSE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "set_mouse",
        "description": "Move the virtual mouse to normalized screen coordinates (0.0 to 1.0). After moving, returns a new screenshot with the updated cursor position.",
        "parameters": {
            "type": "object",
            "properties": {
                "x": {
                    "type": "number",
                    "description": "Horizontal position (0.0=left, 1.0=right)",
                },
                "y": {
                    "type": "number",
                    "description": "Vertical position (0.0=top, 1.0=bottom)",
                },
            },
            "required": ["x", "y"],
        },
    },
}


def execute_set_mouse(
    x: float, y: float, sct, screen_w: int, screen_h: int
) -> dict:
    """Move virtual mouse to (x, y) in normalized coords."""
    px = _denorm(x, screen_w)
    py = _denorm(y, screen_h)
    pyautogui.moveTo(px, py)
    time.sleep(0.05)

    # Take new screenshot
    img = _grab_screen(sct)
    from cua.overlay import draw_cursor
    annotated = draw_cursor(img, px, py, scale=1.0)
    new_mouse = (_norm(px, screen_w), _norm(py, screen_h))

    # Convert BGRA to RGB for JPEG
    img_rgb = img[..., [2, 1, 0]]
    annotated_rgb = annotated[..., [2, 1, 0]]

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img_rgb)}},
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated_rgb)}},
            {
                "type": "text",
                "text": f"Moved to ({new_mouse[0]:.4f}, {new_mouse[1]:.4f}) [pixel ({px}, {py})]",
            },
        ],
        "mouse_pos": new_mouse,
        "last_screenshot": img,
    }


CLICK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "click",
        "description": "Perform a mouse click operation at the current virtual mouse position. Supports left/right/middle buttons, single/double clicks, multi-click, and scrolling. Returns a new screenshot after clicking.",
        "parameters": {
            "type": "object",
            "properties": {
                "button": {
                    "type": "string",
                    "enum": ["left", "right", "middle"],
                    "description": "Mouse button to click",
                },
                "type": {
                    "type": "string",
                    "enum": ["single", "double"],
                    "description": "Click type: single click or double click",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of clicks (default 1). Only meaningful for type=single.",
                },
                "scroll": {
                    "type": "integer",
                    "description": "Scroll amount: positive=up, negative=down, 0=no scroll. Only with type=single.",
                },
            },
            "required": ["button", "type"],
        },
    },
}


def execute_click(
    button: str,
    click_type: str,
    sct,
    mouse_pos: tuple,
    screen_w: int,
    screen_h: int,
    count: int = 1,
    scroll: int = 0,
) -> dict:
    """Execute mouse click at current position."""
    px = _denorm(mouse_pos[0], screen_w)
    py = _denorm(mouse_pos[1], screen_h)

    if click_type == "double":
        pyautogui.doubleClick(px, py, button=button)
    elif click_type == "single":
        if scroll != 0:
            pyautogui.scroll(scroll, x=px, y=py)
        else:
            pyautogui.click(px, py, clicks=max(1, count), button=button)

    time.sleep(0.1)

    img = _grab_screen(sct)
    from cua.overlay import draw_cursor
    annotated = draw_cursor(img, px, py, scale=1.0)

    img_rgb = img[..., [2, 1, 0]]
    annotated_rgb = annotated[..., [2, 1, 0]]

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img_rgb)}},
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated_rgb)}},
            {
                "type": "text",
                "text": f"Clicked {button} {click_type} at ({mouse_pos[0]:.4f}, {mouse_pos[1]:.4f})"
                + (f" scroll={scroll}" if scroll else ""),
            },
        ],
        "mouse_pos": mouse_pos,
        "last_screenshot": img,
    }


DRAG_SCHEMA = {
    "type": "function",
    "function": {
        "name": "drag",
        "description": "Drag from one screen position to another. Moves the mouse to the start, presses the left button, drags to the end, and releases. Virtual mouse ends at the destination.",
        "parameters": {
            "type": "object",
            "properties": {
                "from_x": {"type": "number", "description": "Start X (normalized 0-1)"},
                "from_y": {"type": "number", "description": "Start Y (normalized 0-1)"},
                "to_x": {"type": "number", "description": "End X (normalized 0-1)"},
                "to_y": {"type": "number", "description": "End Y (normalized 0-1)"},
            },
            "required": ["from_x", "from_y", "to_x", "to_y"],
        },
    },
}


def execute_drag(
    from_x: float,
    from_y: float,
    to_x: float,
    to_y: float,
    sct,
    screen_w: int,
    screen_h: int,
) -> dict:
    """Execute drag operation."""
    fpx = _denorm(from_x, screen_w)
    fpy = _denorm(from_y, screen_h)
    tpx = _denorm(to_x, screen_w)
    tpy = _denorm(to_y, screen_h)

    pyautogui.moveTo(fpx, fpy)
    pyautogui.mouseDown()
    pyautogui.moveTo(tpx, tpy, duration=0.5)
    pyautogui.mouseUp()
    time.sleep(0.1)

    img = _grab_screen(sct)
    from cua.overlay import draw_cursor
    new_mouse = (_norm(tpx, screen_w), _norm(tpy, screen_h))
    annotated = draw_cursor(img, tpx, tpy, scale=1.0)

    img_rgb = img[..., [2, 1, 0]]
    annotated_rgb = annotated[..., [2, 1, 0]]

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img_rgb)}},
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated_rgb)}},
            {
                "type": "text",
                "text": (
                    f"Dragged from ({from_x:.4f}, {from_y:.4f}) "
                    f"to ({to_x:.4f}, {to_y:.4f})"
                ),
            },
        ],
        "mouse_pos": new_mouse,
        "last_screenshot": img,
    }

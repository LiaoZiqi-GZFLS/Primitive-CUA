"""Tool registry: collects all tool schemas and routes execution."""
import json
from typing import Any

from cua.tools.screenshot import SCREENSHOT_SCHEMA, execute_screenshot
from cua.tools.mouse import (
    SET_MOUSE_SCHEMA, execute_set_mouse,
    CLICK_SCHEMA, execute_click,
    DRAG_SCHEMA, execute_drag,
)
from cua.tools.keyboard import TYPE_KEYS_SCHEMA, execute_type_keys
from cua.tools.magnifier import MAGNIFIER_SCHEMA, execute_magnifier
from cua.tools.ocr import OCR_SCHEMA, execute_ocr
from cua.tools.clipboard import (
    READ_CLIPBOARD_SCHEMA, execute_read_clipboard,
    PASTE_TEXT_SCHEMA, execute_paste_text,
)
from cua.tools.think import THINK_SCHEMA, execute_think
from cua.tools.finish import FINISH_SCHEMA, FINISH_SENTINEL, execute_finish


# All tool schemas sent to Kimi API (excluding web_search which is a builtin)
TOOLS = [
    SCREENSHOT_SCHEMA,
    SET_MOUSE_SCHEMA,
    CLICK_SCHEMA,
    DRAG_SCHEMA,
    TYPE_KEYS_SCHEMA,
    MAGNIFIER_SCHEMA,
    OCR_SCHEMA,
    READ_CLIPBOARD_SCHEMA,
    PASTE_TEXT_SCHEMA,
    THINK_SCHEMA,
    FINISH_SCHEMA,
]

# Kimi built-in web search tool
WEB_SEARCH_TOOL = {
    "type": "builtin_function",
    "function": {"name": "$web_search"},
}

ALL_TOOLS = TOOLS + [WEB_SEARCH_TOOL]


def execute_tool(
    name: str,
    args: dict,
    sct: Any,
    mouse_pos: tuple[float, float],
    screen_w: int,
    screen_h: int,
    last_screenshot: Any,
) -> dict:
    """Route tool call to the correct implementation.

    Returns a dict with keys:
        content: list of message content blocks for the API
        mouse_pos: updated mouse position (or None if unchanged)
        last_screenshot: updated screenshot array (or same if unchanged)
        _finish_report: only present for finish tool
    """
    if name == "screenshot":
        return execute_screenshot(sct, mouse_pos, screen_w, screen_h)

    elif name == "set_mouse":
        return execute_set_mouse(
            args["x"], args["y"], sct, screen_w, screen_h
        )

    elif name == "click":
        return execute_click(
            args["button"],
            args["type"],
            count=args.get("count", 1),
            scroll=args.get("scroll", 0),
            sct=sct,
            mouse_pos=mouse_pos,
            screen_w=screen_w,
            screen_h=screen_h,
        )

    elif name == "drag":
        return execute_drag(
            args["from_x"], args["from_y"],
            args["to_x"], args["to_y"],
            sct, screen_w, screen_h,
        )

    elif name == "type_keys":
        return execute_type_keys(
            args["keys"], sct, mouse_pos, screen_w, screen_h
        )

    elif name == "magnifier":
        return execute_magnifier(
            sct, mouse_pos, screen_w, screen_h, last_screenshot
        )

    elif name == "ocr":
        return execute_ocr(last_screenshot)

    elif name == "read_clipboard":
        return execute_read_clipboard()

    elif name == "paste_text":
        return execute_paste_text(
            args["text"], sct, mouse_pos, screen_w, screen_h
        )

    elif name == "$web_search":
        # Kimi built-in web search — the actual search is executed server-side.
        # We just acknowledge the call. The search results appear in the model's
        # next response as part of the tool call flow.
        return {
            "content": [{"type": "text", "text": "ok"}],
            "mouse_pos": None,
            "last_screenshot": last_screenshot,
        }

    elif name == "think":
        return execute_think()

    elif name == "finish":
        return execute_finish(
            args["success"],
            args["summary"],
            args["steps"],
        )

    else:
        raise ValueError(f"Unknown tool: {name}")

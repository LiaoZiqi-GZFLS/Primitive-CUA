"""Tool registry: collects all tool schemas and routes execution."""
from typing import Any

from cua.tools.screenshot import SCREENSHOT_SCHEMA, execute_screenshot
from cua.tools.mouse import (
    SET_MOUSE_SCHEMA, execute_set_mouse,
    CLICK_SCHEMA, execute_click,
    DRAG_SCHEMA, execute_drag,
    SCROLL_SCHEMA, execute_scroll,
)
from cua.tools.keyboard import TYPE_KEYS_SCHEMA, execute_type_keys
from cua.tools.magnifier import MAGNIFIER_SCHEMA, execute_magnifier
from cua.tools.ocr import OCR_SCHEMA, execute_ocr
from cua.tools.clipboard import (
    READ_CLIPBOARD_SCHEMA, execute_read_clipboard,
    PASTE_TEXT_SCHEMA, execute_paste_text,
)
from cua.tools.think import THINK_SCHEMA, execute_think
from cua.tools.windows import (
    LIST_WINDOWS_SCHEMA, execute_list_windows,
    FOCUS_WINDOW_SCHEMA, execute_focus_window,
    LAUNCH_APP_SCHEMA, execute_launch_app,
)
from cua.tools.web import (
    WEB_NAVIGATE_SCHEMA, execute_web_navigate,
    WEB_GET_CONTENT_SCHEMA, execute_web_get_content,
    WEB_CLICK_SCHEMA, execute_web_click,
    WEB_TYPE_SCHEMA, execute_web_type,
    WEB_NEW_TAB_SCHEMA, execute_web_new_tab,
    WEB_SWITCH_TAB_SCHEMA, execute_web_switch_tab,
    WEB_CLOSE_TAB_SCHEMA, execute_web_close_tab,
    WEB_REFRESH_SCHEMA, execute_web_refresh,
    WEB_BACK_SCHEMA, execute_web_back,
    WEB_FORWARD_SCHEMA, execute_web_forward,
    WEB_LIST_TABS_SCHEMA, execute_web_list_tabs,
    WEB_PRESS_SCHEMA, execute_web_press,
    WEB_SCROLL_SCHEMA, execute_web_scroll,
)
from cua.tools.uia import (
    UIA_INSPECT_SCHEMA, execute_uia_inspect,
    UIA_CLICK_SCHEMA, execute_uia_click,
    UIA_SET_VALUE_SCHEMA, execute_uia_set_value,
    UIA_GET_TEXT_SCHEMA, execute_uia_get_text,
    RUN_COMMAND_SCHEMA, execute_run_command,
)
from cua.tools.utility import (
    WAIT_SCHEMA, execute_wait,
    FILE_READ_SCHEMA, execute_file_read,
    FILE_WRITE_SCHEMA, execute_file_write,
    NOTE_SCHEMA, execute_note,
)
from cua.tools.human import HUMAN_HELP_SCHEMA, execute_human_help
from cua.subagents.draft_content import DRAFT_CONTENT_SCHEMA, execute_draft_content
from cua.subagents.image_gen import GENERATE_IMAGE_SCHEMA, execute_generate_image
from cua.tools.document import (
    READ_DOCUMENT_SCHEMA, execute_read_document,
    LIST_DOCUMENTS_SCHEMA, execute_list_documents,
    DELETE_DOCUMENT_SCHEMA, execute_delete_document,
    CLEANUP_DOCUMENTS_SCHEMA, execute_cleanup_documents,
)
from cua.tools.kimi_memory import (
    MEMORY_SCHEMA, execute_memory,
    RETHINK_SCHEMA, execute_rethink,
)
from cua.tools.finish import FINISH_SCHEMA, FINISH_SENTINEL, execute_finish


# All tool schemas sent to Kimi API (excluding web_search which is a builtin)
TOOLS = [
    SCREENSHOT_SCHEMA,
    SET_MOUSE_SCHEMA,
    CLICK_SCHEMA,
    DRAG_SCHEMA,
    SCROLL_SCHEMA,
    TYPE_KEYS_SCHEMA,
    MAGNIFIER_SCHEMA,
    OCR_SCHEMA,
    READ_CLIPBOARD_SCHEMA,
    PASTE_TEXT_SCHEMA,
    THINK_SCHEMA,
    LIST_WINDOWS_SCHEMA,
    FOCUS_WINDOW_SCHEMA,
    LAUNCH_APP_SCHEMA,
    WEB_NAVIGATE_SCHEMA,
    WEB_GET_CONTENT_SCHEMA,
    WEB_CLICK_SCHEMA,
    WEB_TYPE_SCHEMA,
    WEB_NEW_TAB_SCHEMA,
    WEB_SWITCH_TAB_SCHEMA,
    WEB_CLOSE_TAB_SCHEMA,
    WEB_REFRESH_SCHEMA,
    WEB_BACK_SCHEMA,
    WEB_FORWARD_SCHEMA,
    WEB_LIST_TABS_SCHEMA,
    WEB_PRESS_SCHEMA,
    WEB_SCROLL_SCHEMA,
    UIA_INSPECT_SCHEMA,
    UIA_CLICK_SCHEMA,
    UIA_SET_VALUE_SCHEMA,
    UIA_GET_TEXT_SCHEMA,
    RUN_COMMAND_SCHEMA,
    WAIT_SCHEMA,
    FILE_READ_SCHEMA,
    FILE_WRITE_SCHEMA,
    NOTE_SCHEMA,
    MEMORY_SCHEMA,
    RETHINK_SCHEMA,
    DRAFT_CONTENT_SCHEMA,
    GENERATE_IMAGE_SCHEMA,
    READ_DOCUMENT_SCHEMA,
    LIST_DOCUMENTS_SCHEMA,
    DELETE_DOCUMENT_SCHEMA,
    CLEANUP_DOCUMENTS_SCHEMA,
    HUMAN_HELP_SCHEMA,
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
        return execute_screenshot(sct, mouse_pos, screen_w, screen_h, delay=args.get("delay", 0.0))

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

    elif name == "scroll":
        return execute_scroll(
            args["x"], args["y"],
            args["direction"],
            args.get("amount", 3),
            sct, screen_w, screen_h,
        )

    elif name == "type_keys":
        return execute_type_keys(
            args["keys"], sct, mouse_pos, screen_w, screen_h,
            repeat=args.get("repeat", 1),
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

    elif name == "list_windows":
        return execute_list_windows()

    elif name == "focus_window":
        return execute_focus_window(
            args["title"], sct, mouse_pos, screen_w, screen_h
        )

    elif name == "launch_app":
        return execute_launch_app(
            args["name"], sct, mouse_pos, screen_w, screen_h
        )

    elif name == "web_navigate":
        return execute_web_navigate(args["url"])

    elif name == "web_get_content":
        return execute_web_get_content()

    elif name == "web_click":
        return execute_web_click(args["text"])

    elif name == "web_type":
        return execute_web_type(args["label"], args["text"])

    elif name == "web_new_tab":
        return execute_web_new_tab()

    elif name == "web_switch_tab":
        return execute_web_switch_tab(args["index"])

    elif name == "web_close_tab":
        return execute_web_close_tab()

    elif name == "web_refresh":
        return execute_web_refresh()

    elif name == "web_back":
        return execute_web_back()

    elif name == "web_forward":
        return execute_web_forward()

    elif name == "web_list_tabs":
        return execute_web_list_tabs()

    elif name == "web_press":
        return execute_web_press(args["key"])

    elif name == "web_scroll":
        return execute_web_scroll(args["amount"])

    elif name == "uia_inspect":
        return execute_uia_inspect(args.get("depth", 3))

    elif name == "uia_click":
        return execute_uia_click(args["name"])

    elif name == "uia_set_value":
        return execute_uia_set_value(args["name"], args["value"])

    elif name == "uia_get_text":
        return execute_uia_get_text(args["name"])

    elif name == "run_command":
        return execute_run_command(args["command"])

    elif name == "wait":
        return execute_wait(args["seconds"])

    elif name == "file_read":
        return execute_file_read(args["path"])

    elif name == "file_write":
        return execute_file_write(args["path"], args["content"])

    elif name == "note":
        return execute_note(args.get("text", ""))

    elif name == "request_human_help":
        return execute_human_help(args["request"])

    elif name == "DraftContent":
        return execute_draft_content(
            args["task"],
            args["persona"],
            args.get("prefill", ""),
            args.get("max_chars", 4000),
        )

    elif name == "GenerateImage":
        return execute_generate_image(args["requirement"])

    elif name == "ReadDocument":
        return execute_read_document(args["path"], args.get("purpose", "file-extract"))

    elif name == "ListDocuments":
        return execute_list_documents()

    elif name == "DeleteDocument":
        return execute_delete_document(args["ref"])

    elif name == "CleanupDocuments":
        return execute_cleanup_documents()

    elif name == "memory":
        return execute_memory(
            args.get("action", ""),
            args.get("key", ""),
            args.get("value", ""),
        )

    elif name == "rethink":
        return execute_rethink(args.get("content", ""))

    elif name == "finish":
        return execute_finish(
            args["success"],
            args["summary"],
            args["steps"],
        )

    else:
        raise ValueError(f"Unknown tool: {name}")

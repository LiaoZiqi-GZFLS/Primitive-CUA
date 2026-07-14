"""Agent core loop: drives the Kimi K2.6 tool-calling cycle."""
import json
import time
from typing import Any

import mss
import numpy as np
from openai import OpenAI

from cua.config import load_config
from cua.tools import ALL_TOOLS, execute_tool
from cua.tools.screenshot import _np_to_jpeg_b64
from cua.overlay import draw_cursor


SYSTEM_PROMPT = """You are a Computer Use Agent (CUA). You control a Windows desktop by calling tools. You operate in a tool-calling loop: you see screenshots, call tools to act, receive new screenshots, and continue until the task is done.

## Tools

- **screenshot**: Full-screen capture. Returns original image + annotated version with virtual mouse cursor (red crosshair + circle).
- **set_mouse(x, y)**: Move virtual mouse to normalized coordinates (0.0-1.0, 4 decimal places).
- **click(button, type, count, scroll)**: Click at current mouse position. button: left/right/middle. type: single/double. count: number of clicks. scroll: positive=up, negative=down.
- **drag(from_x, from_y, to_x, to_y)**: Drag from one position to another.
- **type_keys(keys)**: Type text ("hello world"), press a special key ("enter", "tab", "escape", "backspace", "f5"), or press a combo ("ctrl+c", "alt+tab", "win+r").
- **magnifier**: Square crop centered on cursor, side = half the shorter screen edge. Use for fine details.
- **ocr**: Run OCR on the current screenshot. Returns text blocks with positions and confidence.
- **web_search(query)**: Search the web via Kimi built-in search.
- **read_clipboard**: Read text content from the system clipboard. Use to check what was copied.
- **paste_text(text)**: Paste text at the current cursor position via clipboard (Ctrl+V). Much faster than type_keys for long text. Use type_keys for short text or special keys, paste_text for bulk text.
- **think**: Pause to reflect on progress and plan next steps. Use when you're stuck, unsure, or need to strategize. Does NOT perform any action — it gives you space to think before your next move.
- **finish(success, summary, steps)**: MANDATORY — call this to end the task. You MUST call finish() when the task is complete or cannot proceed. success: true/false. summary: what was accomplished or why it failed. steps: ordered list of key actions taken.

## Critical Rules

1. **ALWAYS end with finish()**: You are in a tool-calling loop. You CANNOT output text directly as a final response. The ONLY way to communicate your final result to the user is by calling the finish() tool. If the task is done, call finish(). If you're stuck or the task is impossible, call finish(success=false, ...). Never output a text summary without also calling finish().

2. **Act, don't describe**: Don't tell me what you plan to do — just call the tool. Take one action at a time, observe the result, then take the next action.

3. **Verify with screenshots**: After every action you receive new screenshots. Use them to confirm the action had the expected effect. If something went wrong, try an alternative approach.

4. **Coordinates**: (0,0)=top-left, (1,1)=bottom-right. Use exactly 4 decimal places. The annotated screenshot shows WHERE the cursor currently is with a red crosshair. To click something: FIRST set_mouse() to position the cursor, THEN click().

5. **Keep trying**: If one approach fails, try another. Use ocr and magnifier to understand what's on screen."""


def _build_initial_content(task: str, mouse_pos, screen_w, screen_h, img):
    """Build the content blocks for the first user message."""
    px = round(mouse_pos[0] * screen_w)
    py = round(mouse_pos[1] * screen_h)
    annotated = draw_cursor(img, px, py, scale=1.0)

    # BGRA → RGB for JPEG
    img_rgb = img[..., [2, 1, 0]]
    annotated_rgb = annotated[..., [2, 1, 0]]

    return [
        {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img_rgb)}},
        {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated_rgb)}},
        {
            "type": "text",
            "text": (
                f"Task: {task}\n"
                f"Screen resolution: {screen_w}x{screen_h}\n"
                f"Virtual mouse starts at: ({mouse_pos[0]:.4f}, {mouse_pos[1]:.4f})\n"
                f"Look at the screenshots and start working on the task."
            ),
        },
    ]


def run_task(task: str, config: dict | None = None) -> dict:
    """Run a single task. Returns the finish report.

    Args:
        task: The task description string.
        config: Optional config dict. If None, loads from config.yaml.

    Returns:
        Finish report dict with success, summary, steps keys.
    """
    if config is None:
        config = load_config()

    api_key = config.get("moonshot_api_key", "")
    if not api_key:
        raise RuntimeError(
            "API key not set. Either:\n"
            "  1. Set 'moonshot_api_key' in cua/config.yaml, or\n"
            "  2. Set the MOONSHOT_API_KEY environment variable"
        )

    model = config.get("model", "kimi-k2.6")
    base_url = config.get("base_url", "https://api.moonshot.cn/v1")
    max_tokens = config.get("max_tokens", 32768)
    max_iterations = config.get("max_iterations", 50)

    client = OpenAI(api_key=api_key, base_url=base_url)

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screen_w = monitor["width"]
        screen_h = monitor["height"]

        # Virtual mouse starts at center
        mouse_pos = (0.5, 0.5)

        # Initial screenshot
        img = np.array(sct.grab(monitor))  # BGRA, (H, W, 4)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_initial_content(task, mouse_pos, screen_w, screen_h, img),
            },
        ]

        for iteration in range(max_iterations):
            # Near the limit, inject a strong reminder
            if iteration == max_iterations - 3:
                messages.append({
                    "role": "user",
                    "content": (
                        "You have only a few iterations remaining. If the task is done "
                        "or you cannot proceed further, call finish() NOW. "
                        "You MUST use the finish tool — do not output text."
                    ),
                })

            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=ALL_TOOLS,
                    max_tokens=max_tokens,
                    extra_body={"thinking": {"type": "disabled"}},
                )
            except Exception as e:
                print(f"  API error (retrying in 2s): {e}")
                time.sleep(2)
                continue

            choice = response.choices[0]
            msg = choice.message

            if msg.content and not msg.tool_calls:
                # Model output text without calling a tool — likely a summary.
                # Remind it to use finish() to properly end the task.
                print(f"  [text response, nudging to call finish]")
                messages.append({"role": "assistant", "content": msg.content})
                messages.append({
                    "role": "user",
                    "content": (
                        "You output text without calling a tool. Remember: you MUST call "
                        "the finish() tool to end the task. If the task is complete, call "
                        "finish(success=true, summary='...', steps=[...]) now. "
                        "If you cannot complete the task, call finish(success=false, ...). "
                        "Do not output text — call the finish tool."
                    ),
                })
                continue

            if not msg.tool_calls:
                continue

            assistant_msg = {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
            messages.append(assistant_msg)

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                args_str = json.dumps(args, ensure_ascii=False)
                if len(args_str) > 120:
                    args_str = args_str[:117] + "..."
                print(f"  [{name}] {args_str}")

                try:
                    result = execute_tool(
                        name, args, sct, mouse_pos, screen_w, screen_h, img
                    )
                except Exception as e:
                    print(f"  Tool error: {e}")
                    result = {
                        "content": [{"type": "text", "text": f"Tool error: {e}"}],
                        "mouse_pos": None,
                        "last_screenshot": img,
                    }

                if result.get("mouse_pos") is not None:
                    mouse_pos = result["mouse_pos"]
                if result.get("last_screenshot") is not None:
                    img = result["last_screenshot"]

                if name == "finish" and "_finish_report" in result:
                    return result["_finish_report"]

                content_items = result["content"]
                text_items = []
                image_items = []
                for item in content_items:
                    if item.get("type") == "image_url":
                        image_items.append(item)
                    else:
                        text_items.append(item)

                tool_text = " ".join(
                    item.get("text", "") for item in text_items
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": tool_text,
                })

                if image_items:
                    user_content = image_items + [
                        {"type": "text", "text": f"After {name}: {tool_text}"}
                    ]
                    messages.append({
                        "role": "user",
                        "content": user_content,
                    })

        return {
            "success": False,
            "summary": f"Reached maximum iterations ({max_iterations}) without calling finish.",
            "steps": [],
        }

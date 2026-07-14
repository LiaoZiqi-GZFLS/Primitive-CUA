"""Agent core loop: drives the Kimi K2.6 tool-calling cycle."""
import os
import json
import time
from typing import Any

import mss
import numpy as np
from openai import OpenAI

from cua.tools import ALL_TOOLS, execute_tool
from cua.tools.screenshot import _np_to_jpeg_b64
from cua.overlay import draw_cursor


SYSTEM_PROMPT = """You are a Computer Use Agent (CUA). You control a Windows desktop by calling tools.

You have these tools:
- **screenshot**: Take a full-screen screenshot. You receive two images: the original and one with a red crosshair + circle marking the virtual mouse position.
- **set_mouse(x, y)**: Move the virtual mouse to normalized coordinates (0.0-1.0). The overlay updates in the next screenshot.
- **click(button, type, count, scroll)**: Click at the current mouse position. button: left/right/middle. type: single/double. count: number of clicks. scroll: positive=up, negative=down (only for type=single).
- **drag(from_x, from_y, to_x, to_y)**: Drag from one position to another (all normalized coordinates).
- **type_keys(keys)**: Type text (string) or key combo (array like ["ctrl", "c"]). Key names: ctrl, alt, shift, enter, tab, escape, backspace, delete, f1-f12, win, up, down, left, right.
- **magnifier**: Get a square crop of the screen centered on the virtual mouse. Side length = half the shorter screen edge. The cursor overlay is proportionally scaled.
- **ocr**: Run OCR on the most recent screenshot. Returns recognized text with bounding boxes.
- **web_search(query)**: Search the web via Kimi built-in search.
- **finish(success, summary, steps)**: End the task. Report what happened.

IMPORTANT:
- The screen has a virtual mouse cursor (red circle + crosshair). The annotated screenshot shows WHERE the cursor currently is.
- To click something, FIRST call set_mouse() to position the cursor over it, THEN call click().
- After every action you receive new screenshots — use them to verify the result.
- Use magnifier to see small UI elements and fine details.
- Use ocr to read text on the screen.
- Normalized coordinates: (0,0)=top-left, (1,1)=bottom-right. Use 4 decimal places.
- After completing a task, call finish() with a report."""


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


def run_task(task: str) -> dict:
    """Run a single task. Returns the finish report."""
    api_key = os.environ.get("MOONSHOT_API_KEY")
    if not api_key:
        raise RuntimeError("MOONSHOT_API_KEY environment variable not set")

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.moonshot.cn/v1",
    )

    with mss.mss() as sct:
        # Get primary monitor dimensions
        monitor = sct.monitors[1]
        screen_w = monitor["width"]
        screen_h = monitor["height"]

        # Virtual mouse starts at center
        mouse_pos = (0.5, 0.5)

        # Initial screenshot
        img = np.array(sct.grab(monitor))  # BGRA, (H, W, 4)

        # Build messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_initial_content(task, mouse_pos, screen_w, screen_h, img),
            },
        ]

        max_iterations = 50
        for iteration in range(max_iterations):
            try:
                response = client.chat.completions.create(
                    model="kimi-k2.6",
                    messages=messages,
                    tools=ALL_TOOLS,
                    max_tokens=32768,
                    extra_body={"thinking": {"type": "disabled"}},
                )
            except Exception as e:
                print(f"  API error (retrying in 2s): {e}")
                time.sleep(2)
                continue

            choice = response.choices[0]
            msg = choice.message

            # If model responds with text only (thinking/planning without tool calls)
            if msg.content and not msg.tool_calls:
                messages.append({"role": "assistant", "content": msg.content})
                continue

            if not msg.tool_calls:
                continue

            # Build assistant message with tool_calls for the API
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

            # Execute each tool call
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                # Truncate for display
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

                # Update state from tool result
                if result.get("mouse_pos") is not None:
                    mouse_pos = result["mouse_pos"]
                if result.get("last_screenshot") is not None:
                    img = result["last_screenshot"]

                # Check for finish sentinel
                if name == "finish" and "_finish_report" in result:
                    return result["_finish_report"]

                # Append tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result["content"], ensure_ascii=False),
                })

        # Hit max iterations without finish
        return {
            "success": False,
            "summary": "Reached maximum iterations (50) without calling finish.",
            "steps": [],
        }

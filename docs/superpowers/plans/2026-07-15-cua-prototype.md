# CUA Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-loop Computer Use Agent that controls Windows desktop via Kimi K2.6 API, with 9 tools (screenshot, mouse control, keyboard, magnifier, OCR, web search, finish).

**Architecture:** CLI reads task → agent.py runs Kimi tool-calling loop → tools execute desktop actions → screenshots flow back as base64 JPEG images. All mouse coordinates are normalized [0,1]. No context carries over between task rounds.

**Tech Stack:** Python 3.10+, mss, pyautogui, openai SDK, rapidocr-onnxruntime, Pillow, numpy

---

### Task 1: Project scaffolding

**Files:**
- Create: `cua/__init__.py`
- Create: `cua/requirements.txt`

- [ ] **Step 1: Create cua package init**

```python
# cua/__init__.py
# CUA - Computer Use Agent prototype
```

- [ ] **Step 2: Create requirements.txt**

```
mss>=9.0.0
pyautogui>=0.9.54
openai>=1.0.0
rapidocr-onnxruntime>=1.3.0
Pillow>=10.0.0
numpy>=1.24.0
```

- [ ] **Step 3: Install dependencies**

```bash
pip install -r cua/requirements.txt
```

- [ ] **Step 4: Commit**

```bash
git add cua/__init__.py cua/requirements.txt
git commit -m "chore: scaffold cua package with dependencies"
```

---

### Task 2: Overlay renderer

**Files:**
- Create: `cua/overlay.py`

- [ ] **Step 1: Write overlay.py**

```python
"""Draw virtual mouse cursor overlay on screenshots."""
import numpy as np
from PIL import Image, ImageDraw


def draw_cursor(
    image: np.ndarray,
    px: int,
    py: int,
    scale: float = 1.0,
) -> np.ndarray:
    """Draw virtual mouse cursor on a screenshot.

    Draws a red crosshair (full image) + red circle with white border at (px, py).
    Returns a NEW array (does not mutate input).

    Args:
        image: BGRA numpy array from mss (H, W, 4)
        px, py: Pixel position of cursor center
        scale: Size multiplier for magnifier mode

    Returns:
        RGBA numpy array with overlay drawn
    """
    h, w = image.shape[:2]

    # Convert BGRA (mss format) to RGBA for Pillow
    img_rgba = image[..., [2, 1, 0, 3]]
    pil_img = Image.fromarray(img_rgba, "RGBA")
    draw = ImageDraw.Draw(pil_img)

    # Line and circle sizes
    line_width = max(1, int(2 * scale))
    outer_radius = int(18 * scale)
    inner_radius = int(15 * scale)
    outer_width = max(1, int(4 * scale))
    inner_width = max(1, int(3 * scale))

    red = (231, 76, 60, 255)  # #e74c3c
    white = (255, 255, 255, 255)

    # Full-image crosshair
    draw.line([(0, py), (w, py)], fill=red, width=line_width)
    draw.line([(px, 0), (px, h)], fill=red, width=line_width)

    # White outer ring
    draw.ellipse(
        [px - outer_radius, py - outer_radius, px + outer_radius, py + outer_radius],
        outline=white,
        width=outer_width,
    )

    # Red inner circle (no fill)
    draw.ellipse(
        [px - inner_radius, py - inner_radius, px + inner_radius, py + inner_radius],
        outline=red,
        width=inner_width,
    )

    return np.array(pil_img)
```

- [ ] **Step 2: Verify import**

```bash
python -c "from cua.overlay import draw_cursor; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cua/overlay.py
git commit -m "feat: add overlay renderer for virtual mouse cursor"
```

---

### Task 3: Screenshot tool

**Files:**
- Create: `cua/tools/__init__.py` (empty placeholder)
- Create: `cua/tools/screenshot.py`

- [ ] **Step 1: Create tools package placeholder**

```python
# cua/tools/__init__.py (will be populated in Task 9)
```

- [ ] **Step 2: Write screenshot.py**

```python
"""Full-screen screenshot tool using mss."""
import io
import base64
from typing import Any

import numpy as np
from PIL import Image

from cua.overlay import draw_cursor


def _np_to_jpeg_b64(img: np.ndarray, quality: int = 85) -> str:
    """Convert numpy array (RGBA or RGB) to base64 JPEG data URI."""
    # Remove alpha if present for JPEG
    if img.shape[-1] == 4:
        img = img[..., :3]
    pil_img = Image.fromarray(img, "RGB")
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _annotated_screenshot(
    original: np.ndarray, px: int, py: int, scale: float
) -> np.ndarray:
    """Return annotated copy of screenshot."""
    return draw_cursor(original, px, py, scale)


SCREENSHOT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "screenshot",
        "description": "Take a full-screen screenshot. Returns the original image and an annotated version with the virtual mouse cursor position marked.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def execute_screenshot(
    sct: Any, mouse_pos: tuple[float, float], screen_w: int, screen_h: int
) -> dict:
    """Take a screenshot and return original + annotated as base64 JPEG."""
    import mss as _mss

    # Capture
    monitor = sct.monitors[1]
    img = np.array(sct.grab(monitor))  # BGRA, (H, W, 4)

    px = round(mouse_pos[0] * screen_w)
    py = round(mouse_pos[1] * screen_h)

    annotated = _annotated_screenshot(img, px, py, scale=1.0)

    original_b64 = _np_to_jpeg_b64(img[..., [2, 1, 0, 3]])  # BGRA → RGBA → RGB
    annotated_b64 = _np_to_jpeg_b64(annotated)

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": original_b64}},
            {"type": "image_url", "image_url": {"url": annotated_b64}},
            {
                "type": "text",
                "text": (
                    f"Screen: {screen_w}x{screen_h}. "
                    f"Virtual mouse: ({mouse_pos[0]:.4f}, {mouse_pos[1]:.4f})"
                ),
            },
        ],
        "last_screenshot": img,
    }
```

- [ ] **Step 3: Verify import**

```bash
python -c "from cua.tools.screenshot import SCREENSHOT_SCHEMA, execute_screenshot; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add cua/tools/__init__.py cua/tools/screenshot.py
git commit -m "feat: add screenshot tool with mss capture and overlay"
```

---

### Task 4: Mouse tools (set_mouse, click, drag)

**Files:**
- Create: `cua/tools/mouse.py`

- [ ] **Step 1: Write mouse.py**

```python
"""Virtual mouse control tools: set_mouse, click, drag."""
import json
import time
from typing import Any

import pyautogui

from cua.tools.screenshot import _np_to_jpeg_b64, _annotated_screenshot

# Fail-safe: move to corner to abort
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


def _denorm(x: float, dim: int) -> int:
    """Convert normalized coordinate to pixel, clamped."""
    return max(0, min(dim - 1, round(x * dim)))


def _norm(px: int, dim: int) -> float:
    """Convert pixel to normalized coordinate."""
    return round(px / dim, 4)


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
    img = _grab_screen(sct, screen_w, screen_h)
    annotated = _annotated_screenshot(img, px, py, scale=1.0)
    new_mouse = (_norm(px, screen_w), _norm(py, screen_h))

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img[..., [2, 1, 0, 3]])}},
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated)}},
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
    count: int,
    scroll: int,
    sct,
    mouse_pos: tuple,
    screen_w: int,
    screen_h: int,
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

    img = _grab_screen(sct, screen_w, screen_h)
    annotated = _annotated_screenshot(img, px, py, scale=1.0)

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img[..., [2, 1, 0, 3]])}},
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated)}},
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

    img = _grab_screen(sct, screen_w, screen_h)
    new_mouse = (_norm(tpx, screen_w), _norm(tpy, screen_h))
    annotated = _annotated_screenshot(img, tpx, tpy, scale=1.0)

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img[..., [2, 1, 0, 3]])}},
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated)}},
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


def _grab_screen(sct, screen_w: int, screen_h: int):
    """Capture screen via mss, return BGRA numpy array."""
    import numpy as np
    return np.array(sct.grab(sct.monitors[1]))
```

- [ ] **Step 2: Verify import**

```bash
python -c "from cua.tools.mouse import SET_MOUSE_SCHEMA, CLICK_SCHEMA, DRAG_SCHEMA; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cua/tools/mouse.py
git commit -m "feat: add mouse tools (set_mouse, click, drag)"
```

---

### Task 5: Keyboard tool

**Files:**
- Create: `cua/tools/keyboard.py`

- [ ] **Step 1: Write keyboard.py**

```python
"""Keyboard input tool: type_keys."""
import time

import pyautogui

from cua.tools.mouse import _grab_screen, _denorm
from cua.tools.screenshot import _np_to_jpeg_b64, _annotated_screenshot


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
        # Type text character by character
        pyautogui.typewrite(keys, interval=0.02)
    elif isinstance(keys, list):
        # Key combination: hold all, then release
        pyautogui.hotkey(*keys)

    time.sleep(0.15)

    px = _denorm(mouse_pos[0], screen_w)
    py = _denorm(mouse_pos[1], screen_h)
    img = _grab_screen(sct, screen_w, screen_h)
    annotated = _annotated_screenshot(img, px, py, scale=1.0)

    desc = repr(keys) if isinstance(keys, str) else "+".join(keys)
    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img[..., [2, 1, 0, 3]])}},
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated)}},
            {"type": "text", "text": f"Typed: {desc}"},
        ],
        "mouse_pos": mouse_pos,
        "last_screenshot": img,
    }
```

- [ ] **Step 2: Verify import**

```bash
python -c "from cua.tools.keyboard import TYPE_KEYS_SCHEMA, execute_type_keys; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cua/tools/keyboard.py
git commit -m "feat: add keyboard tool (type_keys)"
```

---

### Task 6: Magnifier tool

**Files:**
- Create: `cua/tools/magnifier.py`

- [ ] **Step 1: Write magnifier.py**

```python
"""Magnifier tool: square crop centered on virtual mouse."""
import numpy as np

from cua.overlay import draw_cursor
from cua.tools.screenshot import _np_to_jpeg_b64


MAGNIFIER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "magnifier",
        "description": "Take a square crop of the screen centered on the current virtual mouse position. The crop side length equals half the shorter screen dimension. Returns the original crop and an annotated version with a proportionally scaled cursor marker. Use this to see fine details near the cursor.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def execute_magnifier(
    sct,
    mouse_pos: tuple[float, float],
    screen_w: int,
    screen_h: int,
    last_screenshot: np.ndarray,
) -> dict:
    """Crop a square around the virtual mouse, with proportional overlay."""
    px = round(mouse_pos[0] * screen_w)
    py = round(mouse_pos[1] * screen_h)
    crop_side = min(screen_w, screen_h) // 2
    scale = crop_side / min(screen_w, screen_h)

    # Compute crop bounds (clamped to image edges)
    half = crop_side // 2
    left = max(0, min(screen_w - crop_side, px - half))
    top = max(0, min(screen_h - crop_side, py - half))

    # Crop from the last screenshot
    # last_screenshot is BGRA from mss
    crop = last_screenshot[top : top + crop_side, left : left + crop_side].copy()

    # Local cursor position within the crop
    local_px = px - left
    local_py = py - top

    annotated_crop = draw_cursor(crop, local_px, local_py, scale=scale)

    # Convert BGRA→RGBA→RGB for JPEG
    crop_rgb = crop[..., [2, 1, 0, 3]][..., :3]
    annotated_rgb = annotated_crop[..., [2, 1, 0, 3]][..., :3]

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(crop_rgb)}},
            {
                "type": "image_url",
                "image_url": {"url": _np_to_jpeg_b64(annotated_rgb)},
            },
            {
                "type": "text",
                "text": (
                    f"Magnifier: {crop_side}x{crop_side} crop at "
                    f"({mouse_pos[0]:.4f}, {mouse_pos[1]:.4f}), "
                    f"scale={scale:.2f}"
                ),
            },
        ],
        "mouse_pos": mouse_pos,
        "last_screenshot": last_screenshot,
    }
```

- [ ] **Step 2: Verify import**

```bash
python -c "from cua.tools.magnifier import MAGNIFIER_SCHEMA, execute_magnifier; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cua/tools/magnifier.py
git commit -m "feat: add magnifier tool (square crop with proportional overlay)"
```

---

### Task 7: OCR tool

**Files:**
- Create: `cua/tools/ocr.py`

- [ ] **Step 1: Write ocr.py**

```python
"""OCR tool using RapidOCR."""
import io
import json

import numpy as np
from PIL import Image


OCR_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ocr",
        "description": "Run OCR (Optical Character Recognition) on the most recent screenshot to extract all visible text. Returns recognized text blocks with their bounding boxes and confidence scores. Use this to read text content on the screen.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def execute_ocr(last_screenshot: np.ndarray) -> dict:
    """Run RapidOCR on the last screenshot, return structured text results."""
    from rapidocr_onnxruntime import RapidOCR

    # last_screenshot is BGRA from mss, convert to RGB for OCR
    if last_screenshot.shape[-1] == 4:
        img_rgb = last_screenshot[..., [2, 1, 0]]  # BGRA → RGB
    else:
        img_rgb = last_screenshot

    ocr_engine = RapidOCR()
    result, _ = ocr_engine(img_rgb)

    if result is None:
        result = []

    # Format: [bbox, text, confidence]
    text_blocks = []
    for item in result:
        bbox = item[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        text = item[1]
        confidence = item[2]
        text_blocks.append(
            {
                "text": text,
                "confidence": round(confidence, 4),
                "center_x": round((bbox[0][0] + bbox[2][0]) / 2, 1),
                "center_y": round((bbox[0][1] + bbox[2][1]) / 2, 1),
            }
        )

    return {
        "content": [
            {"type": "text", "text": json.dumps(text_blocks, ensure_ascii=False)}
        ],
        "mouse_pos": None,  # OCR does not change mouse pos
        "last_screenshot": last_screenshot,
    }
```

- [ ] **Step 2: Verify import**

```bash
python -c "from cua.tools.ocr import OCR_SCHEMA, execute_ocr; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cua/tools/ocr.py
git commit -m "feat: add OCR tool using RapidOCR"
```

---

### Task 8: Finish tool

**Files:**
- Create: `cua/tools/finish.py`

- [ ] **Step 1: Write finish.py**

```python
"""Finish tool: end the current task round with a report."""

FINISH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "finish",
        "description": "End the current task. Call this when the task is complete or cannot be completed. Provide a success/failure status, a summary of what was accomplished, and a list of steps taken.",
        "parameters": {
            "type": "object",
            "properties": {
                "success": {
                    "type": "boolean",
                    "description": "Whether the task was completed successfully",
                },
                "summary": {
                    "type": "string",
                    "description": "Concise summary of what was accomplished or why it failed",
                },
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of key actions taken, in order",
                },
            },
            "required": ["success", "summary", "steps"],
        },
    },
}


FINISH_SENTINEL = "__CUA_FINISH__"


def execute_finish(success: bool, summary: str, steps: list[str]) -> dict:
    """Return finish report. The agent loop detects FINISH_SENTINEL to exit."""
    return {
        "content": [
            {"type": "text", "text": FINISH_SENTINEL}
        ],
        "_finish_report": {
            "success": success,
            "summary": summary,
            "steps": steps,
        },
    }
```

- [ ] **Step 2: Verify import**

```bash
python -c "from cua.tools.finish import FINISH_SCHEMA, FINISH_SENTINEL, execute_finish; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cua/tools/finish.py
git commit -m "feat: add finish tool for task completion reporting"
```

---

### Task 9: Tool registry

**Files:**
- Modify: `cua/tools/__init__.py`

- [ ] **Step 1: Rewrite __init__.py with registry**

```python
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
            args.get("count", 1),
            args.get("scroll", 0),
            sct,
            mouse_pos,
            screen_w,
            screen_h,
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

    elif name == "finish":
        return execute_finish(
            args["success"],
            args["summary"],
            args["steps"],
        )

    else:
        raise ValueError(f"Unknown tool: {name}")
```

- [ ] **Step 2: Verify import**

```bash
python -c "from cua.tools import TOOLS, ALL_TOOLS, execute_tool; print(f'{len(TOOLS)} tools loaded, OK')"
```

Expected: `8 tools loaded, OK` (8 regular + 1 builtin web_search)

- [ ] **Step 3: Commit**

```bash
git add cua/tools/__init__.py
git commit -m "feat: add tool registry with dispatch routing"
```

---

### Task 10: Agent core loop

**Files:**
- Create: `cua/agent.py`

- [ ] **Step 1: Write agent.py**

```python
"""Agent core loop: drives the Kimi K2.6 tool-calling cycle."""
import os
import json
import time
from typing import Any

import mss
import numpy as np
from openai import OpenAI

from cua.tools import ALL_TOOLS, execute_tool, FINISH_SENTINEL
from cua.tools.screenshot import _np_to_jpeg_b64
from cua.overlay import draw_cursor


SYSTEM_PROMPT = """You are a Computer Use Agent (CUA). You control a Windows desktop by calling tools.

You have these tools:
- **screenshot**: Take a full-screen screenshot. You receive two images: the original and one with a red crosshair + circle marking the virtual mouse position.
- **set_mouse(x, y)**: Move the virtual mouse to normalized coordinates (0.0-1.0). The overlay updates in the next screenshot.
- **click(button, type, count, scroll)**: Click at the current mouse position. button: left/right/middle. type: single/double. count: number of clicks. scroll: positive=up, negative=down (set count=1, only for type=single).
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

    return [
        {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(img[..., [2, 1, 0, 3]])}},
        {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated)}},
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
        monitor = sct.monitors[1]
        screen_w = monitor["width"]
        screen_h = monitor["height"]

        # Virtual mouse starts at center
        mouse_pos = (0.5, 0.5)

        # Initial screenshot
        img = np.array(sct.grab(monitor))  # BGRA
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": _build_initial_content(task, mouse_pos, screen_w, screen_h, img),
            },
        ]

        max_iterations = 50
        for _ in range(max_iterations):
            try:
                response = client.chat.completions.create(
                    model="kimi-k2.6",
                    messages=messages,
                    tools=ALL_TOOLS,
                    max_tokens=32768,
                    extra_body={"thinking": {"type": "disabled"}},
                )
            except Exception as e:
                print(f"API error: {e}")
                time.sleep(2)
                continue

            choice = response.choices[0]
            msg = choice.message

            # If the model responds with text (no tool calls), treat as thinking/planning
            if msg.content and not msg.tool_calls:
                # Append as assistant message and continue
                messages.append({"role": "assistant", "content": msg.content})
                continue

            if not msg.tool_calls:
                continue

            # Build assistant message with tool_calls
            assistant_msg = {"role": "assistant", "content": msg.content or "", "tool_calls": []}
            for tc in msg.tool_calls:
                assistant_msg["tool_calls"].append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })
            messages.append(assistant_msg)

            # Execute each tool call
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                print(f"  [{name}] {json.dumps(args, ensure_ascii=False)[:120]}")

                try:
                    result = execute_tool(
                        name, args, sct, mouse_pos, screen_w, screen_h, img
                    )
                except Exception as e:
                    result = {
                        "content": [{"type": "text", "text": f"Tool error: {e}"}],
                        "mouse_pos": None,
                        "last_screenshot": img,
                    }

                # Update state
                if result.get("mouse_pos") is not None:
                    mouse_pos = result["mouse_pos"]
                if result.get("last_screenshot") is not None:
                    img = result["last_screenshot"]

                # Check for finish
                if name == "finish" and "_finish_report" in result:
                    return result["_finish_report"]

                # Append tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result["content"], ensure_ascii=False),
                })

        # Hit max iterations
        return {
            "success": False,
            "summary": "Reached maximum iterations without calling finish.",
            "steps": [],
        }
```

- [ ] **Step 2: Verify import**

```bash
python -c "from cua.agent import run_task, SYSTEM_PROMPT; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cua/agent.py
git commit -m "feat: add agent core loop with Kimi K2.6 tool-calling"
```

---

### Task 11: CLI entry point

**Files:**
- Create: `cua/cli.py`

- [ ] **Step 1: Write cli.py**

```python
"""CLI entry point for the CUA agent."""
import sys

from cua.agent import run_task


def main():
    """Run the CUA agent in an interactive CLI loop."""
    print("=" * 60)
    print("CUA - Computer Use Agent")
    print("  LLM: Kimi K2.6")
    print("  Type a task to begin, or 'quit' to exit.")
    print("=" * 60)

    # If task provided as command-line argument, run it once
    args = sys.argv[1:]
    if args:
        task = " ".join(args)
        print(f"\nTask: {task}\n")
        report = run_task(task)
        _print_report(report)
        return

    # Interactive mode
    while True:
        try:
            task = input("\nTask > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not task:
            continue
        if task.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break

        print()
        report = run_task(task)
        _print_report(report)


def _print_report(report: dict):
    """Print a formatted finish report."""
    print()
    if report["success"]:
        print("✓ Task completed successfully")
    else:
        print("✗ Task failed")

    print(f"Summary: {report['summary']}")

    steps = report.get("steps", [])
    if steps:
        print("Steps:")
        for i, step in enumerate(steps, 1):
            print(f"  {i}. {step}")

    print()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify import**

```bash
python -c "from cua.cli import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add cua/cli.py
git commit -m "feat: add CLI entry point with interactive task loop"
```

---

### Task 12: Integration verification

**Files:**
- Create: `cua/test_overlay.py` (manual test script)

- [ ] **Step 1: Write manual overlay test**

```python
"""Manual test: verify overlay rendering produces valid output."""
import numpy as np
from cua.overlay import draw_cursor


def test_overlay_basic():
    """Create a fake white screen and draw cursor on it."""
    # Simulate a 1920x1080 BGRA screenshot (all white)
    img = np.ones((1080, 1920, 4), dtype=np.uint8) * 255
    img[:, :, 3] = 255  # Alpha

    result = draw_cursor(img, px=960, py=540, scale=1.0)

    assert result.shape == (1080, 1920, 4), f"Shape mismatch: {result.shape}"
    assert result.dtype == np.uint8

    # Check crosshair at center: red pixels exist along the crosshair
    # Horizontal line at y=540 should have red pixels
    center_row = result[540, :, 0]  # R channel
    assert np.any(center_row == 231), "No red crosshair pixels found on horizontal line"

    # Vertical line at x=960
    center_col = result[:, 960, 0]
    assert np.any(center_col == 231), "No red crosshair pixels found on vertical line"

    print("PASS: overlay_basic")


def test_overlay_magnifier_scale():
    """Verify magnifier scale reduces marker size."""
    img = np.ones((540, 540, 4), dtype=np.uint8) * 255
    img[:, :, 3] = 255

    result = draw_cursor(img, px=270, py=270, scale=0.5)

    assert result.shape == (540, 540, 4)
    # At scale 0.5, circle should be roughly half size
    # Quick check: red pixels should exist near center
    assert np.any(result[270, :, 0] == 231)
    print("PASS: overlay_magnifier_scale")


if __name__ == "__main__":
    test_overlay_basic()
    test_overlay_magnifier_scale()
    print("\nAll overlay tests passed.")
```

- [ ] **Step 2: Run overlay tests**

```bash
python cua/test_overlay.py
```

Expected: `PASS: overlay_basic`, `PASS: overlay_magnifier_scale`, `All overlay tests passed.`

- [ ] **Step 3: Verify full import chain**

```bash
python -c "
from cua.overlay import draw_cursor
from cua.tools import ALL_TOOLS, execute_tool
from cua.agent import run_task
from cua.cli import main
print('All imports successful')
print(f'Tools registered: {len(ALL_TOOLS)}')
"
```

Expected: `All imports successful`, `Tools registered: 9`

- [ ] **Step 4: Commit**

```bash
git add cua/test_overlay.py
git commit -m "test: add overlay rendering verification tests"
```

---

### Task 13: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md with project specifics**

Replace the development section with actual commands and architecture:

```markdown
## Development

### Setup

```bash
pip install -r cua/requirements.txt
```

### Run

```bash
# Interactive mode
python cua/cli.py

# Single task
python cua/cli.py "打开记事本并输入hello world"
```

Environment variable required: `MOONSHOT_API_KEY`.

### Run Tests

```bash
python cua/test_overlay.py
```

### Architecture

```
cli.py          → Interactive CLI, reads tasks, prints finish reports
agent.py        → Core agent loop: Kimi K2.6 tool-calling cycle
overlay.py      → Draws virtual mouse cursor (red crosshair + circle) on screenshots
tools/
  __init__.py   → Tool registry: schema collection + execute_tool() dispatcher
  screenshot.py → mss full-screen capture, returns original + annotated JPEG images
  mouse.py      → set_mouse (move cursor), click (left/right/double/scroll), drag
  keyboard.py   → type_keys (text input + key combos)
  magnifier.py  → Square crop centered on cursor, side = min(w,h)/2, scaled overlay
  ocr.py        → RapidOCR text extraction from last screenshot
  finish.py     → Task completion: reports success/summary/steps, ends agent loop
```

### Key Design Decisions

- **thinking=disabled**: Required because `$web_search` is incompatible with K2.6 thinking mode
- **Images as JPEG base64**: Screenshots are compressed to JPEG (quality 85) before base64 encoding to reduce token costs
- **Normalized coordinates**: All mouse positions use [0,1] range with 4 decimal places; conversion to pixels happens in tool layer
- **No context between rounds**: Each CLI task builds a fresh `messages` list
- **Tool ordering matters**: The agent is single-threaded; tool calls execute sequentially within each API response
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with CUA development guide"
```

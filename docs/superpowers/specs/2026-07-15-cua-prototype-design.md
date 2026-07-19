# CUA Prototype Design

**Date**: 2026-07-15
**Status**: design approved

## Overview

A single-loop Computer Use Agent (CUA) prototype. The agent uses Kimi K2.6 (via OpenAI-compatible API) to control a Windows desktop through tool calls. The user provides a task via CLI; the agent iterates (screenshot → decide → act → screenshot) until completion, then prints a structured report. Each task round starts fresh with no context inheritance.

## Architecture

```
cli.py → agent.py → Kimi K2.6 API
                ↕
        tools/ (7 tools)
```

- **cli.py**: Reads task from command line, invokes agent, prints finish report, waits for next task.
- **agent.py**: Core loop. Builds messages with images, calls Kimi API, routes tool_calls to tool implementations, appends tool results. Ends when `finish` is called.
- **overlay.py**: Draws virtual mouse cursor on screenshots — red circle (r=15px, white border 3px) + red crosshair spanning full image width/height.
- **tools/**: 9 tools, one file per tool + `__init__.py` registry.

### File Structure

```
cua/
├── cli.py
├── agent.py
├── overlay.py
├── tools/
│   ├── __init__.py
│   ├── screenshot.py
│   ├── mouse.py
│   ├── keyboard.py
│   ├── magnifier.py
│   ├── ocr.py
│   └── finish.py
└── requirements.txt
```

## LLM Configuration

| Setting | Value | Reason |
|---------|-------|--------|
| model | kimi-k2.6 | Latest vision + tool-use model |
| base_url | https://api.moonshot.cn/v1 | OpenAI-compatible |
| thinking | disabled | Required for `$web_search` compatibility |
| max_tokens | 32768 | Default, sufficient for tool-call loops |
| temperature | 1.0 (fixed) | K2.6 does not allow modification |

Images sent as JPEG (quality 85), base64-encoded, in OpenAI vision format `data:image/jpeg;base64,...`.

## Tool Specifications

### 1. screenshot

Full-screen capture via `mss`. Returns two JPEG images (both as base64 data URIs):
- **original**: Raw screenshot
- **annotated**: Same screenshot with virtual mouse overlay drawn at current position

Also returns current virtual mouse normalized coordinates and screen resolution as text.

No input parameters.

### 2. set_mouse

Sets virtual mouse position in normalized coordinates. Moves the real system cursor via `pyautogui.moveTo()`.

```
Parameters:
  x: float  (0.0000–1.0000, normalized to screen width)
  y: float  (0.0000–1.0000, normalized to screen height)
```

Returns: new screenshot pair (original + annotated at new position) + updated coordinates.

### 3. click

Performs mouse click at current virtual mouse position.

```
Parameters:
  button: "left" | "right" | "middle"
  type: "single" | "double"
  count: int  (for multi-click, default 1)
  scroll: int  (scroll amount: positive=up, negative=down, 0=none; only with type="single")
```

Returns: new screenshot pair after the click action.

### 4. drag

Drag from one position to another.

```
Parameters:
  from_x, from_y: float  (start position, normalized)
  to_x, to_y: float  (end position, normalized)
```

Internally calls `pyautogui.moveTo(from) → pyautogui.mouseDown() → pyautogui.moveTo(to, duration=0.5) → pyautogui.mouseUp()`.

After drag completes, virtual mouse position updates to `(to_x, to_y)`.

Returns: new screenshot pair at the destination position.

### 5. type_keys

Sends keyboard input via `pyautogui`.

```
Parameters:
  keys: string | string[]
```

- Single string: types characters one by one (e.g. `"hello world"`)
- Array: presses keys in combination then releases (e.g. `["ctrl", "c"]`, `["alt", "tab"]`)

Supports special key names per pyautogui convention (`ctrl`, `alt`, `shift`, `enter`, `tab`, `escape`, `backspace`, `delete`, `up`, `down`, `left`, `right`, `f1`–`f12`, `win`, etc.).

Returns: new screenshot pair after key input.

### 6. magnifier

Takes a square crop centered on the current virtual mouse position. Side length = half the shorter screen dimension.

```
No parameters (uses current mouse position).
```

Returns: two cropped images (original + annotated). The overlay marker is proportionally scaled: circle radius and line thickness scale by `crop_side / min(screen_w, screen_h)`.

### 7. ocr

Runs RapidOCR (`rapidocr-onnxruntime`) on the most recent original screenshot.

```
No parameters.
```

Returns: structured text — all recognized text blocks with their bounding box positions and confidence scores in JSON format.

### 8. web_search

Kimi built-in web search via `$web_search` builtin_function.

```
Parameters:
  query: string
```

Returns: search result structured data from Kimi.

### 9. finish

Ends the current task round.

```
Parameters:
  success: bool        — whether the task was completed successfully
  summary: string      — concise conclusion (what was accomplished or why it failed)
  steps: string[]      — list of key actions taken, in order
```

Returns control to cli.py, which prints the report and waits for the next task.

## Agent Loop

```
1. Parse task from CLI
2. Take initial screenshot (mouse at screen center 0.5, 0.5)
3. Build first user message: task + resolution + mouse coords + two images
4. Send to Kimi API (with all tool schemas)
5. If response has tool_calls:
   a. Execute each tool in order
   b. Append tool results (images as base64 + text) to messages
   c. Update virtual mouse state if position changed
   d. Goto 4
6. If finish tool called: parse report, return to CLI
```

Each round's `messages` list is completely independent — no history carries over between CLI tasks.

## Coordinate System

- All mouse coordinates are **normalized to [0, 1]**, 4 decimal places
- `(0.0000, 0.0000)` = top-left corner of primary monitor
- `(1.0000, 1.0000)` = bottom-right corner of primary monitor
- Conversion: `pixel = round(normalized × screen_dimension)`
- Stored in memory as floats; serialized to 4 decimal places in tool parameters

## Overlay Rendering (overlay.py)

On a given screenshot (numpy array from mss), at pixel position (px, py):

1. Draw full-width **red horizontal line** at y=py (color `#e74c3c`, width 2px)
2. Draw full-height **red vertical line** at x=px (color `#e74c3c`, width 2px)
3. Draw **white outer ring**: radius 18px, width 4px
4. Draw **red inner circle**: radius 15px, width 3px (color `#e74c3c`, no fill)

For magnifier mode: multiply all sizes by `crop_side / min(screen_w, screen_h)`.

## Dependencies

```
mss>=9.0.0
pyautogui>=0.9.54
openai>=1.0.0
rapidocr-onnxruntime>=1.3.0
Pillow>=10.0.0
numpy>=1.24.0
```

## CLI Usage

```bash
python cua/cli.py "帮我打开浏览器搜索今天的科技新闻"
```

After completion, CLI prints the finish report and prompts for the next task:

```
✓ 任务完成
摘要: 已成功打开Edge浏览器并搜索今日科技新闻...
步骤:
  1. 双击任务栏Edge图标 (0.12, 0.95)
  2. 点击地址栏 (0.50, 0.06)
  3. 输入 "今日科技新闻"
  4. 按下Enter
  5. 确认搜索结果页面加载完成

输入下一个任务 (或 'quit' 退出):
```

## Out of Scope

- Multi-monitor support (primary monitor only)
- Context carryover between rounds
- Audio/speech input
- Application-specific automation beyond what the LLM can reason about visually
- Async or parallel tool execution

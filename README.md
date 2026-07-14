# Primitive-CUA

A single-loop Computer Use Agent (CUA) prototype that controls Windows desktop through tool-calling. Uses **Kimi K2.6** (Moonshot AI) as the vision-language model, `mss` for screen capture, and `pyautogui` for mouse/keyboard control.

## Architecture

```
User Task → Agent Loop → Kimi K2.6 API
                ↕
        9 Tools (screenshot, mouse, keyboard, magnifier, OCR, web search, ...)
```

The agent receives a task, takes a screenshot, and enters a tool-calling loop: the model sees the screen → decides what action to take → calls a tool → receives a new screenshot → repeats until the task is done or cannot be completed.

Every screenshot is sent as **two images**: the original and an annotated version with a red crosshair + circle marking the virtual mouse cursor position.

## Quick Start

### 1. Install dependencies

```bash
pip install -r cua/requirements.txt
```

### 2. Set API key

Copy the example config and fill in your Kimi API key:

```bash
cp cua/config.example.yaml cua/config.yaml
# Edit cua/config.yaml → set moonshot_api_key
```

Or set the environment variable:

```bash
# Windows PowerShell
$env:MOONSHOT_API_KEY = "your-key"

# Linux/macOS
export MOONSHOT_API_KEY="your-key"
```

Get an API key at [Kimi Open Platform](https://platform.kimi.com/console/api-keys).

### 3. Run

```bash
# Single task
python cua/cli.py "打开记事本并输入hello world"

# Interactive mode
python cua/cli.py
```

## Tools

| Tool | Description |
|------|-------------|
| `screenshot` | Full-screen capture via `mss`. Returns original + annotated image with virtual mouse overlay |
| `set_mouse(x, y)` | Move virtual mouse to normalized coordinates (0.0–1.0) |
| `click(button, type, count, scroll)` | Click at current mouse position. Supports left/right/middle, single/double, multi-click, scroll |
| `drag(from_x, from_y, to_x, to_y)` | Drag from one position to another |
| `type_keys(keys)` | Type text or press key combos (e.g. `["ctrl", "c"]`) |
| `magnifier` | Square crop centered on cursor, side = half the shorter screen edge, with scaled overlay |
| `ocr` | Run RapidOCR on the most recent screenshot, returns text blocks with bounding boxes |
| `web_search(query)` | Kimi built-in web search |
| `finish(success, summary, steps)` | End the task with a structured report |

## Virtual Mouse

All mouse coordinates are **normalized to [0, 1]** with 4 decimal places:
- `(0.0000, 0.0000)` = top-left corner
- `(1.0000, 1.0000)` = bottom-right corner

The virtual mouse cursor is rendered as a red circle (white border) + full-image red crosshair on annotated screenshots.

## Configuration

See `cua/config.example.yaml` for all options:

```yaml
moonshot_api_key: ""       # Kimi API key
model: "kimi-k2.6"         # LLM model
max_tokens: 32768          # Max tokens per API call
max_iterations: 50         # Max tool-calling iterations per task
jpeg_quality: 85           # Screenshot JPEG quality

overlay:                   # Cursor overlay style
  circle_radius: 15
  color: "#e74c3c"
```

## Project Structure

```
cua/
├── cli.py              # Interactive CLI entry point
├── agent.py            # Core agent loop: Kimi K2.6 tool-calling cycle
├── config.py           # YAML config loader (defaults → config.yaml → env vars)
├── overlay.py          # Virtual mouse cursor renderer
├── tools/
│   ├── __init__.py     # Tool registry + execute_tool() dispatcher
│   ├── screenshot.py   # mss capture + base64 JPEG encoding
│   ├── mouse.py        # set_mouse, click, drag
│   ├── keyboard.py     # type_keys
│   ├── magnifier.py    # Square crop with proportional overlay
│   ├── ocr.py          # RapidOCR text extraction
│   └── finish.py       # Task completion reporting
├── config.example.yaml # Configuration template
├── config.yaml         # Your local config (gitignored)
├── requirements.txt
└── test_overlay.py     # Overlay rendering tests
```

## Design Decisions

- **thinking=disabled**: Required for `$web_search` compatibility with K2.6
- **JPEG base64**: Screenshots compressed to JPEG (quality 85) before base64 encoding to reduce token cost
- **No context between rounds**: Each CLI task builds a fresh `messages` list
- **Tool results as user messages**: Images are fed back via user-role messages since Kimi API only renders `image_url` in user messages

## Requirements

- Python 3.10+
- Windows (primary target — uses `mss` and `pyautogui`)
- Kimi API key

## License

BSD 3-Clause

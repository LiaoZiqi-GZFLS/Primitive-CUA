# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Primitive-CUA** — a Computer Use Agent (CUA) project leveraging the Kimi K2.6 API (Moonshot AI) via its OpenAI-compatible HTTP interface. The project is in early-stage setup; no application code exists yet.

## API Reference

The project targets the **Kimi K2.6** model family via `https://api.moonshot.cn/v1`. Full API documentation is at `docs/kimi-api/kimi_k2.6_api_reference.md`. Key points:

- **OpenAI SDK compatible**: Use the standard `openai` Python/Node.js SDK with `base_url="https://api.moonshot.cn/v1"`
- **Authentication**: `Authorization: Bearer $MOONSHOT_API_KEY`
- **Thinking mode**: K2.6 defaults to thinking enabled (`reasoning_content` in responses); can be disabled via `extra_body={"thinking": {"type": "disabled"}}`
- **Vision**: Supports image (PNG/JPEG/WebP/GIF) and video (MP4/MOV/AVI/etc.) input via base64 or file upload (`ms://` protocol)
- **Tool calling**: Standard OpenAI-compatible `tools`/`tool_calls`, plus built-in functions like `$web_search`
- **Structured output**: Supports `response_format={"type": "json_object"}` and `response_format={"type": "json_schema", ...}`
- **Context window**: 262,144 tokens
- **Context caching**: Automatic; cache-hit pricing is significantly cheaper

## Project Structure

```
Primitive-CUA/
├── docs/
│   └── kimi-api/
│       └── kimi_k2.6_api_reference.md   # Only substantive file — comprehensive Kimi API docs
├── .gitignore                            # Python-focused gitignore
├── LICENSE                               # BSD 3-Clause
└── README.md                             # Placeholder
```

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

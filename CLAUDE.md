# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Primitive-CUA** — a Computer Use Agent (CUA) project leveraging the Kimi K3 API (Moonshot AI) via its OpenAI-compatible HTTP interface.

## API Reference

The project targets the **Kimi K3** model via `https://api.moonshot.cn/v1`. Full API documentation is at `docs/kimi-api/kimi_k3.md`. Key points:

- **OpenAI SDK compatible**: Use the standard `openai` Python/Node.js SDK with `base_url="https://api.moonshot.cn/v1"`
- **Authentication**: `Authorization: Bearer $MOONSHOT_API_KEY`
- **Thinking mode**: K3 always has thinking ON. Uses `reasoning_effort` parameter (currently only `max`, which is default). No `extra_body={"thinking": ...}` needed — do NOT pass it.
- **Vision**: Supports image (PNG/JPEG/WebP/GIF) and video (MP4/MOV/AVI/etc.) input via base64 or file upload (`ms://` protocol)
- **Tool calling**: Standard OpenAI-compatible `tools`/`tool_calls`
- **Structured output**: Supports `response_format={"type": "json_object"}` and `response_format={"type": "json_schema", "strict": True}`
- **Context window**: 1,000,000 tokens (1M)
- **Context caching**: Automatic; cache-hit pricing is significantly cheaper
- **`$web_search`**: Being updated — not recommended for production use currently
- **Fixed parameters**: `temperature=1.0`, `top_p=0.95` — do not explicitly pass these

## Project Structure

```
Primitive-CUA/
├── docs/
│   └── kimi-api/
│       ├── kimi_k3.md                    # Kimi K3 API reference (current model)
│       └── kimi_k2.6_api_reference.md    # Legacy K2.6 API docs
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
agent.py        → Core agent loop: Kimi K3 tool-calling cycle + prompt management
overlay.py      → Draws virtual mouse cursor (red crosshair + circle) on screenshots
config.py       → YAML config loader with env var fallback
learning.py     → Four-layer learning: AutoSkill (ChromaDB), Reflection, Pending, Knowledge base
replay.py       → Trajectory recording and replay with step verification
tools/
  __init__.py   → Tool registry: 47 tool schemas + execute_tool() dispatcher
  screenshot.py → mss full-screen capture → tiered downscale → PNG base64 + OCR
  mouse.py      → set_mouse, click, drag, scroll (normalized coords)
  keyboard.py   → type_keys (shortcuts only) — paste_text handles text input
  clipboard.py  → paste_text (primary text input), read_clipboard
  magnifier.py  → Square crop centered on cursor for fine-detail inspection
  ocr.py        → RapidOCR text extraction with shared engine
  think.py      → Reflection prompt injection for agent reasoning pauses
  finish.py     → Task completion — ends agent loop
  web.py        → Playwright browser automation (14 tools)
  uia.py        → Windows UI Automation (5 tools)
  windows.py    → Window management (list/focus/launch)
  utility.py    → wait, file_read, file_write, note
  human.py      → request_human_help
  document.py   → Kimi Files API (upload/extract/delete)
  kimi_memory.py→ Remote persistent KV storage + rethink consolidation
  loader.py     → Tool group definitions (reference) + ChromaDB similarity search
subagents/
  draft_content.py → Isolated content writing with persona
  image_gen.py     → Multi-round SVG generation with visual self-review
knowledge/
  *.md          → Manual knowledge base files (ChromaDB-indexed on startup)
```

### Key Design Decisions

- **K3 always thinking**: K3 always produces reasoning. `reasoning_effort="max"` is default. Assistant messages must preserve `reasoning_content` field.
- **Tiered PNG screenshots**: mss captures BGRA → numpy → downscale by resolution tier (≤2K keep, 4K→2K, 4K+→4K) → PIL LANCZOS → PNG base64. OCR runs on full-resolution image.
- **Normalized coordinates**: All mouse positions use [0,1] range with 4 decimal places; conversion to pixels happens in tool layer
- **Native tool selection**: All 47 tools sent to K3 on every request (no LLM classification). K3's 1M context + auto-caching makes this efficient.
- **Verify + Think after every action**: State-changing actions trigger BEFORE/AFTER screenshot comparison + analyst review + think() reflection prompt injection
- **Prompt architecture**: SYSTEM_PROMPT in agent.py defines tool usage guidance and critical rules. THINK_PROMPT in think.py structures reflection. OCR/verify prompts are inline in agent.py. Learning prompts in learning.py.
- **No context between rounds**: Each CLI task builds a fresh `messages` list (learning system persists via SQLite + ChromaDB)
- **Tool ordering matters**: The agent is single-threaded; tool calls execute sequentially within each API response

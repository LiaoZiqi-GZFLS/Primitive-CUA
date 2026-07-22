# Primitive-CUA

A Computer Use Agent (CUA) that controls Windows desktop through tool-calling. Uses **Kimi K3** (Moonshot AI, 1M context, 2.8T params) as the vision-language model, with 47 specialized tools for desktop, web, and native app automation.

## Architecture

```
User Task → Agent Loop → Kimi K3 API (47 tools, native tool selection)
                ↕
        Desktop, Web, UIA, Clipboard, Document, Memory, Subagents
                ↓
         Post-task Learning (AutoSkill / Reflection / Pending)
```

The agent receives a task, takes a screenshot, and enters a tool-calling loop: the model sees the screen → decides what action to take → calls tools → receives results → repeats until done. All 47 tools are sent to K3 on every request, leveraging K3's 1M context and auto-caching for native tool selection.

## Quick Start

### 1. Install dependencies

```bash
pip install -r cua/requirements.txt
```

### 2. Set API key

```bash
cp cua/config.example.yaml cua/config.yaml
# Edit cua/config.yaml → set moonshot_api_key
```

Or: `$env:MOONSHOT_API_KEY = "your-key"` (PowerShell) / `export MOONSHOT_API_KEY="your-key"` (bash).

Get a key at [Kimi Open Platform](https://platform.kimi.com/console/api-keys).

### 3. Run

```bash
python cua/cli.py                              # Interactive mode
python cua/cli.py "打开记事本写hello world"     # Single task
python cua/cli.py --record "打开微信搜索"       # Record element templates
python cua/cli.py --replay "微信搜索"           # Fast replay with templates
python cua/cli.py --script script.cua           # Execute .cua script
```

### Record & Replay

```
--record: Agent executes task normally, auto-captures UI elements
          (PNG button images + dHash + embedding + OCR + ROI).
          At task end, saves a macro (step sequence) and generates
          a .cua script improved by K3.

--replay: Fast execution using recorded templates. Three tiers:
          L0: OpenCV multi-scale template match (<10ms, no AI)
          L1: MiniLM embedding sliding-window search (~100ms)
          L2: Kimi K3 agent fallback (~5s)
          Self-healing: K3 reviews failures and rewrites .cua script.

--script: Execute .cua DSL scripts with actions, variables,
          branches, loops, and perception (kimi/ocr/see/window).
          return 0=success, 1=failure, 2=delegate to K3 agent.
          Scripts can be validated without execution via --check.
```

## Tool Categories

| Category | Tools | Description |
|----------|-------|-------------|
| **Desktop** | screenshot, set_mouse, click, drag, scroll, type_keys, paste_text, magnifier, ocr | Screen capture, mouse/keyboard/clipboard |
| **Windows** | list_windows, focus_window, launch_app | Window discovery, switching, app launch |
| **Web** | web_navigate, web_click, web_type, web_get_content, web_scroll (+7 more) | Playwright-driven browser automation |
| **UIA** | uia_inspect, uia_click, uia_set_value, uia_get_text, run_command | Windows UI Automation for Office/native apps |
| **Utility** | think, wait, note, file_read, file_write | Reasoning, timing, persistence |
| **Document** | ReadDocument, ListDocuments, DeleteDocument, CleanupDocuments | Kimi Files API for PDF/DOCX extraction |
| **Memory** | memory, rethink | Kimi Formula remote KV storage + consolidation |
| **Subagents** | DraftContent, GenerateImage | Isolated sessions for writing and image generation |

## Configuration

```yaml
moonshot_api_key: ""              # Kimi API key
model: "kimi-k3"                  # LLM model
max_completion_tokens: 131072     # Max tokens per API call (K3 max: 1048576)
max_iterations: 100               # Max tool-calling iterations per task

# Record & Replay
record:
  enabled: true                   # Auto-capture elements during agent execution
replay:
  l0_threshold: 0.70             # Template match minimum score
  l1_threshold: 0.60             # Embedding match minimum similarity
script:
  auto_improve: true              # K3 improves recorded scripts
  embed_model: "auto"            # multilingual/onnx/path
```

## Design Decisions

- **K3 always thinking**: K3 always produces reasoning; `reasoning_effort="max"` is default.
- **PNG screenshots**: mss → tiered downscale (≤2K keep, 4K→2K, 4K+→4K) → PNG base64
- **Normalized coordinates**: Mouse positions use [0,1] range with 4 decimal places
- **Native tool selection**: All 47 tools always sent to K3; auto-cached after first request
- **Learning system**: Success → AutoSkill, Failure → Reflection, Interrupted → Pending
- **Record & Replay**: Elements = visual widgets (PNG+dHash+embedding+OCR+ROI). 3-tier execution: L0 pixel (<10ms), L1 embedding (~100ms), L2 K3 (~5s). Self-healing loop.
- **Script engine**: .cua DSL with variables, branches, perception (kimi/ocr/see/window), return codes (0/1/2). Validation pass before execution.
- **Embedding**: Multilingual MiniLM-L12 (zh+en) preferred; ONNX MiniLM-L6 offline fallback.

## Requirements

- Python 3.10+
- Windows (uses `mss`, `pyautogui`, `pygetwindow`, `uiautomation`)
- Kimi API key

## License

BSD 3-Clause

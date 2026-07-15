"""Agent core loop: drives the Kimi K2.6 tool-calling cycle."""
import json
import time
from typing import Any

import mss
import numpy as np
from openai import OpenAI

from cua.config import load_config
from cua.tools import ALL_TOOLS, execute_tool
from cua.tools.loader import build_tools
from cua.tools.screenshot import _np_to_jpeg_b64
from cua.learning import get_learnings_prompt
from cua.overlay import draw_cursor

# Module-level tool log for Ctrl+C recovery
_current_tool_log: list[str] = []


def get_last_tool_log() -> list[str]:
    """Get tool calls from the most recent (possibly interrupted) task."""
    return list(_current_tool_log)

# Tools that modify system state — trigger auto-verification after execution
VERIFY_TOOLS = {
    # Desktop action tools
    "click", "drag", "type_keys", "paste_text",
    # Windows management
    "focus_window", "launch_app",
    # Web tools
    "web_navigate", "web_click", "web_type",
    "web_new_tab", "web_switch_tab", "web_close_tab",
    "web_refresh", "web_back", "web_forward",
    "web_press", "web_scroll",
    # UIA tools that modify state
    "uia_click", "uia_set_value",
}


SYSTEM_PROMPT = """You are a Computer Use Agent (CUA). You control a Windows desktop by calling tools. You operate in a tool-calling loop: you see screenshots, call tools to act, receive new screenshots, and continue until the task is done.

## Tools

- **screenshot**: Full-screen capture. Returns original image + annotated version with virtual mouse cursor (red crosshair + circle).
- **set_mouse(x, y)**: Move virtual mouse to normalized coordinates (0.0-1.0, 4 decimal places).
- **click(button, type, count, scroll)**: Click at current mouse position. button: left/right/middle. type: single/double. count: number of clicks. scroll: positive=up, negative=down.
- **drag(from_x, from_y, to_x, to_y)**: Drag from one position to another.
- **type_keys(keys, repeat?)**: Keyboard shortcuts and special keys ONLY ("ctrl+c", "enter", "tab", "escape", "backspace", "delete", "f5", "alt+tab", "win+r"). Use repeat=N for multiple presses (e.g. "backspace" repeat=10). DO NOT use for typing text — use paste_text for ALL text input.
- **magnifier**: Square crop centered on cursor, side = half the shorter screen edge. Use for fine details.
- **ocr**: Run OCR on the current screenshot. Returns text blocks with positions and confidence.
- **web_search(query)**: Search the web via Kimi built-in search.
- **read_clipboard**: Read text content from the system clipboard. Use to check what was copied.
- **paste_text(text)**: THE primary text input method. Copies text to clipboard → Ctrl+V. Works for ALL text: Chinese, English, emoji, code, long paragraphs. Use this for EVERY text input. Only use type_keys for keyboard shortcuts, never for content.
- **think**: Pause to reflect on progress and plan next steps. Use when you're stuck, unsure, or need to strategize. Does NOT perform any action — it gives you space to think before your next move.
- **list_windows**: List all open windows with titles, positions, visibility. Use this FIRST for any desktop task — find the target window before acting. Essential for Office, dialogs, and native apps.
- **focus_window(title)**: Bring a window to front by matching its title (partial match). Use list_windows first to find the exact title.
- **launch_app(name)**: Launch via Start menu search (Win key → type/paste name → Enter). Uses paste for Chinese. Only finds apps indexed by Windows Search — if it fails, try opening via taskbar shortcut or desktop icon instead.
- **wait(seconds)**: Wait for a duration (0.5-10s). Use after launching apps or loading pages instead of repeatedly calling screenshot to check. Saves tokens.
- **file_read(path)**: Read the contents of a text file. Use to check file content without opening GUI apps.
- **file_write(path, content)**: Write text content to a file. Creates parent directories automatically. Use for saving output directly instead of GUI save dialogs.
- **note(text)**: Save a note to your persistent notepad.
- **DraftContent(task, persona, prefill?, max_chars?)**: Write long-form content (articles, emails, reports) in an isolated writing session with its own persona. Returns file path + preview — use file_read to get full content.
- **GenerateImage(requirement)**: Generate an SVG image (icon, illustration, diagram). Uses multi-round generation + visual self-review. Returns PNG file path.
- **ReadDocument(path)**: Upload a file to Kimi and extract its text (PDF, DOCX, images with OCR). Returns a doc:<sha8> reference for DraftContent. Use instead of file_read for non-text files.
- **ListDocuments / DeleteDocument(ref) / CleanupDocuments**: Manage uploaded files in Kimi cloud (quota: 1000 files). Clean up periodically. Use to remember window positions, icon locations, file paths, or task progress. Notes appear automatically in think(). Call with no text to read all notes.
- **uia_inspect(depth)**: Inspect the UI control tree of the current foreground window. Shows control names, types, and positions. Essential for Office, native Windows apps, and dialogs with structured UI.
- **uia_click(name)**: Click a UI control by name (partial match) in the foreground window. Uses UIA Invoke pattern — reliable for buttons, menus, tabs in native apps.
- **uia_set_value(name, value)**: Set the value of an input/editable control by name. Uses UIA Value pattern for precise text entry in Office and native app fields. Supports Chinese.
- **uia_get_text(name)**: Read text/value from a control by name. Use to read document content, cell values, status text.
- **run_command(command)**: Open Windows Run dialog (Win+R), type a command, and press Enter. Use to open paths, launch executables, run shell commands.
- **web_navigate(url)**: Open a URL directly in the built-in browser. Use this IMMEDIATELY for any web task — no need to open Chrome/Edge on the desktop first. Just call web_navigate("https://...") as your first action.
- **web_get_content()**: Read the current page — headings, buttons, links, inputs, text. Use this instead of OCR/screenshot for web pages. Much more precise.
- **web_click(text)**: Click an element on the web page by its visible text. Reliable, no coordinate guessing.
- **web_type(label, text)**: Type into an input field (matched by placeholder/label). Use for form filling. Press Enter with web_press('Enter') after filling to submit.
- **web_press(key)**: Press a keyboard key on the page. Use 'Enter' to submit forms, 'Escape' to close modals, 'Tab' to switch focus.
- **web_scroll(amount)**: Scroll the page. Positive=down, negative=up. Use 500 for a typical scroll.
- **web_new_tab / web_switch_tab(index) / web_close_tab / web_list_tabs**: Manage browser tabs.
- **web_refresh / web_back / web_forward**: Page navigation (reload, back, forward).
- **request_human_help(request)**: Pause and ask the human for assistance. Use for login pages, CAPTCHAs, UAC permission dialogs, or any situation you cannot handle. Describe what you need, wait for the human's response, then continue.
- **finish(success, summary, steps)**: MANDATORY — call this to end the task. You MUST call finish() when the task is complete or cannot proceed. success: true/false. summary: what was accomplished or why it failed. steps: ordered list of key actions taken.

## Critical Rules

1. **ALWAYS end with finish()**: You are in a tool-calling loop. You CANNOT output text directly as a final response. The ONLY way to communicate your final result to the user is by calling the finish() tool. If the task is done, call finish(). If you're stuck or the task is impossible, call finish(success=false, ...). Never output a text summary without also calling finish().

2. **Act, don't describe**: Don't tell me what you plan to do — just call the tool. Take one action at a time, observe the result, then take the next action. However, when you call a tool, briefly explain your reasoning in the content field — what you're doing and why.

3. **verify parameter**: All action tools accept an optional verify boolean (default true). Set verify=false for rapid multi-step sequences to skip the before/after screenshot comparison — think() is still injected after every action regardless. Only use verify=false for fast consecutive operations; use verify=true (or omit) for normal use.

4. **Coordinates**: (0,0)=top-left, (1,1)=bottom-right. Use exactly 4 decimal places. The annotated screenshot shows WHERE the cursor currently is with a red crosshair. To click something: FIRST set_mouse() to position the cursor, THEN click().

5. **Web tasks = use web tools DIRECTLY**: If the task involves visiting a website, searching the web, reading online content, filling web forms, or ANY browser-based action, use web_navigate(url) IMMEDIATELY as your first action. Do NOT open a desktop browser, do NOT click the taskbar, do NOT use screenshot for web pages. The web tools run in their own browser — just call web_navigate("https://...") and then web_get_content() to see the page. The workflow is: web_navigate → web_get_content → web_click/web_type/web_press. You never need desktop tools for web tasks.

6. **ALL text input goes through paste**: paste_text is your default for any text — Chinese, English, code, URLs, file names, everything. type_keys is ONLY for keyboard shortcuts (ctrl+c, alt+tab, win+r) and special keys (enter, escape, tab, f5). If you catch yourself calling type_keys to type words, stop — use paste_text instead. The only exception is apps that block clipboard paste (rare); in that case, try uia_set_value first, then type_keys as last resort.

7. **Prefer structured tools over coordinate clicking**: For Office apps (Word, Excel, PowerPoint), Windows native dialogs, use structured tools FIRST. Best workflow: list_windows → focus_window → uia_inspect → uia_click/uia_set_value/uia_get_text. Only fall back to screenshot+set_mouse+click when structured tools can't access the target element.

8. **Keep trying**: If one approach fails, try another. Use ocr and magnifier to understand what's on screen."""


def _build_initial_content(task: str, mouse_pos, screen_w, screen_h):
    """Build the text-only content blocks for the first user message."""
    return [
        {
            "type": "text",
            "text": (
                f"Task: {task}\n"
                f"Screen resolution: {screen_w}x{screen_h}\n"
                f"Virtual mouse starts at: ({mouse_pos[0]:.4f}, {mouse_pos[1]:.4f})\n\n"
                f"Before you begin:\n"
                f"1. If the task involves a WEBSITE or URL, call web_navigate(url) DIRECTLY "
                f"as your first action. Do NOT open a desktop browser — web tools have their own.\n"
                f"2. If this is a purely informational task that requires no action "
                f"(e.g. answering a question, looking something up), call finish() directly.\n"
                f"3. Otherwise, first call screenshot() to see the current desktop state. "
                f"Then use think() to plan your approach.\n"
                f"4. Before each action, confirm the current state matches your expectation "
                f"by checking the screenshot. Explain your reasoning and act."
            ),
        },
    ]


def _cleanup_context(messages: list):
    """Remove stale image messages after a state-changing action.

    Cleans up:
    1. All set_mouse/magnifier result images
    2. All verify (BEFORE/AFTER) images except the most recent one
    3. All images from user messages before the 5th-to-last state-changing action
    """
    # Find the index of the last verify message
    last_verify_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg["role"] == "user":
            content = msg["content"]
            if isinstance(content, list):
                for item in content:
                    if item.get("type") == "text" and "BEFORE" in item.get("text", ""):
                        last_verify_idx = i
                        break
            if last_verify_idx >= 0:
                break

    # Find the position of the 5th-to-last state-changing action (click, web_click, focus_window, etc.)
    fifth_action_idx = -1
    action_count = 0
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg["role"] == "assistant" and "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                if tc.get("function", {}).get("name") in VERIFY_TOOLS:
                    action_count += 1
                    if action_count == 5:
                        fifth_action_idx = i
                        break
            if fifth_action_idx >= 0:
                break

    removed = 0
    for i in range(len(messages)):
        msg = messages[i]
        if msg["role"] != "user":
            continue
        content = msg["content"]
        if not isinstance(content, list):
            continue

        has_images = any(item.get("type") == "image_url" for item in content)
        if not has_images:
            continue

        full_text = " ".join(
            item.get("text", "") for item in content if item.get("type") == "text"
        )

        should_clean = False
        reason = ""

        # Rule 1: set_mouse/magnifier result images
        if "After set_mouse" in full_text or "After magnifier" in full_text:
            should_clean = True
            reason = "set_mouse/magnifier"

        # Rule 2: older verify images
        if "BEFORE" in full_text and i < last_verify_idx:
            should_clean = True
            reason = "old verify"

        # Rule 3: before the 5th-to-last state-changing action
        if fifth_action_idx >= 0 and i < fifth_action_idx:
            should_clean = True
            reason = "beyond 5-action window"

        if should_clean:
            new_content = []
            for item in content:
                if item.get("type") == "image_url":
                    removed += 1
                    continue
                new_content.append(item)
            new_content.append({
                "type": "text",
                "text": f" [images cleaned: {reason}]",
            })
            messages[i] = {"role": "user", "content": new_content}

    # Track last occurrence of each tool + first think for preservation
    last_indices: dict[str, int] = {}
    first_think_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg["role"] == "tool":
            name = msg.get("name", "")
            if name not in last_indices:
                last_indices[name] = i
            if name == "think":
                first_think_idx = i  # the earliest think (round 0) gets the smallest i

    # Rule 4: trim stale text from ALL perception tools.
    # Keep only the most recent result per perception tool; wipe all older ones.
    PERCEPTION_TOOLS = {
        "web_get_content", "list_windows", "web_list_tabs",
        "ocr", "read_clipboard", "uia_inspect", "uia_get_text",
    }

    trimmed = 0

    for i in range(len(messages)):
        msg = messages[i]
        if msg["role"] != "tool":
            continue
        name = msg.get("name", "")
        if name in PERCEPTION_TOOLS and i < last_indices.get(name, i):
            if i == first_think_idx:
                continue  # never delete round 0 think
            content = msg.get("content", "")
            first_line = content.split("\n")[0][:80] if content else ""
            messages[i]["content"] = f" [trimmed] {first_line}..."
            trimmed += 1

    # Rule 5: after 10+ state-changing actions, wipe ALL old tool output text
    wiped = 0
    if action_count >= 10:
        for i in range(len(messages)):
            msg = messages[i]
            if msg["role"] != "tool":
                continue
            name = msg.get("name", "")
            # Keep only the most recent output per tool
            if i >= last_indices.get(name, i):
                continue
            if i == first_think_idx:
                continue  # never wipe round 0 think
            content = msg.get("content", "")
            if len(content) > 80:
                messages[i]["content"] = f" [wiped] {content[:80]}..."
                wiped += 1

    if removed > 0 or trimmed > 0 or wiped > 0:
        print(f"  [cleanup] removed {removed} images, trimmed {trimmed} perception, wiped {wiped} old tool outputs from context")

    return action_count


def _compress_context(messages: list, client, model: str, max_tokens: int, skip_actions: int = 0):
    """LLM compression: summarize the next 10 oldest action-rounds into one concise record."""
    # Find the range of actions to compress: skip_actions to skip_actions+10
    action_count = 0
    compress_start_idx = -1
    compress_end_idx = -1
    for i in range(len(messages)):
        msg = messages[i]
        if msg["role"] == "assistant" and "tool_calls" in msg:
            for tc in msg["tool_calls"]:
                if tc.get("function", {}).get("name") in VERIFY_TOOLS:
                    action_count += 1
                    if action_count == skip_actions + 1 and compress_start_idx < 0:
                        compress_start_idx = i
                    if action_count == skip_actions + 10:
                        compress_end_idx = i
                        break
        if compress_end_idx >= 0:
            break

    if compress_start_idx < 0 or compress_end_idx < 0:
        return  # Not enough actions in range

    # Collect messages to compress: from compress_start_idx to compress_end_idx
    to_compress = []
    keep = []
    for i, msg in enumerate(messages):
        if i < compress_start_idx:
            keep.append(msg)
        elif i <= compress_end_idx:
            # Skip system prompt and the first think result
            if i == 0:  # system prompt
                keep.append(msg)
                continue
            if msg["role"] == "tool" and msg.get("name") == "think":
                keep.append(msg)  # preserve round-0 think
                continue
            to_compress.append(msg)
        else:
            keep.append(msg)

    if len(to_compress) < 5:
        return  # Too little to compress

    print(f"  [compress] summarizing {len(to_compress)} messages from early rounds...")

    try:
        # Build a text representation of what happened
        trace = []
        for msg in to_compress:
            role = msg["role"]
            if role == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    texts = [item.get("text", "") for item in content if item.get("type") == "text"]
                    trace.append(f"user: {' '.join(texts)[:200]}")
                elif isinstance(content, str):
                    trace.append(f"user: {content[:200]}")
            elif role == "assistant":
                tc = msg.get("tool_calls", [])
                if tc:
                    names = [t.get("function", {}).get("name", "?") for t in tc]
                    trace.append(f"assistant: called {', '.join(names)}")
                elif msg.get("content"):
                    trace.append(f"assistant: {msg['content'][:150]}")
            elif role == "tool":
                trace.append(f"tool({msg.get('name','?')}): {msg.get('content','')[:150]}")

        trace_text = "\n".join(trace[-50:])  # last 50 entries for compression

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Summarize this desktop automation trace into ONE concise paragraph. Include: what the user asked for, what actions were taken, what was accomplished in these rounds, any important findings (window positions, file paths, errors). Keep it under 300 characters. Write in Chinese if the original task was in Chinese."},
                {"role": "user", "content": trace_text},
            ],
            max_tokens=300,
            extra_body={"thinking": {"type": "disabled"}},
        )
        summary = resp.choices[0].message.content or ""

        # Replace: keep system prompt + first think, then compressed summary, then the rest
        compressed_msg = {
            "role": "user",
            "content": [{"type": "text", "text": f"[Compressed early rounds]\n{summary}"}],
        }

        # Find where to insert: after system + first think
        insert_pos = 1  # after system prompt
        for i in range(1, len(keep)):
            if keep[i]["role"] == "tool" and keep[i].get("name") == "think":
                insert_pos = i + 1
                break

        keep.insert(insert_pos, compressed_msg)
        messages[:] = keep

        print(f"  [compress] context reduced from {len(to_compress) + len(keep)} to {len(messages)} messages")

    except Exception as e:
        print(f"  [compress] failed: {e}")


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

    # Create client first (needed for LLM classification)
    client = OpenAI(api_key=api_key, base_url=base_url)

    # Dynamically load tools based on LLM task classification
    tool_names, tool_info, task_class = build_tools(task, client, model)
    active_tools = [t for t in ALL_TOOLS if t["function"]["name"] in tool_names]
    print(f"  Tools loaded: {tool_info} = {len(active_tools)} total")

    # Inject similar past learnings into first think()
    from cua.tools.think import set_think_context
    set_think_context(task_class.get("similar", ""))

    token_usage = {"prompt": 0, "completion": 0, "total": 0}
    _compressed_up_to = 0  # how many action-rounds have been compressed so far

    from cua.tools.utility import clear_notes
    clear_notes()

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screen_w = monitor["width"]
        screen_h = monitor["height"]

        # Virtual mouse starts at center
        mouse_pos = (0.5, 0.5)

        # Initial screenshot for state (not sent to model yet)
        img = np.array(sct.grab(monitor))  # BGRA, (H, W, 4)

        # Inject past learnings into system prompt
        learnings_text = get_learnings_prompt()
        system_content = SYSTEM_PROMPT + learnings_text

        # Tool call log (module-level for Ctrl+C recovery)
        _current_tool_log.clear()

        # Main agent messages
        messages = [
            {"role": "system", "content": system_content},
            {
                "role": "user",
                "content": _build_initial_content(task, mouse_pos, screen_w, screen_h),
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
                    tools=active_tools,
                    max_tokens=max_tokens,
                    extra_body={"thinking": {"type": "disabled"}},
                )
            except Exception as e:
                print(f"  API error (retrying in 2s): {e}")
                time.sleep(2)
                continue

            if hasattr(response, "usage") and response.usage:
                token_usage["prompt"] += response.usage.prompt_tokens or 0
                token_usage["completion"] += response.usage.completion_tokens or 0
                token_usage["total"] += response.usage.total_tokens or 0

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

            # Show model's reasoning before tool calls
            if msg.content:
                print(f"  💭 {msg.content}")

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
                _current_tool_log.append(f"[{name}] {args_str}")

                # Save before-screenshot for verify step
                img_before = img.copy() if name in VERIFY_TOOLS else None

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
                    result["_finish_report"]["tokens"] = token_usage
                    result["_finish_report"]["__current_tool_log"] = _current_tool_log
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

                # OCR cleaning: after screenshot, refine OCR with context-aware LLM
                if name == "screenshot":
                    print(f"  [ocr-clean] refining OCR with context...")
                    try:
                        # Extract raw OCR text from the tool result
                        raw_ocr = ""
                        for item in result["content"]:
                            if item.get("type") == "text":
                                raw_ocr = item.get("text", "")
                                break

                        # Scan for latest awareness tool results
                        latest_windows = "(no list_windows result yet)"
                        latest_web = "(no web_get_content result yet)"
                        latest_tabs = "(no web_list_tabs result yet)"
                        for m in reversed(messages):
                            if m["role"] == "tool":
                                n = m.get("name", "")
                                if n == "list_windows" and latest_windows.startswith("(no"):
                                    latest_windows = m.get("content", "")
                                elif n == "web_get_content" and latest_web.startswith("(no"):
                                    latest_web = m.get("content", "")
                                elif n == "web_list_tabs" and latest_tabs.startswith("(no"):
                                    latest_tabs = m.get("content", "")

                        # Build UIA tree with content
                        uia_tree = "(UIA inspection not available)"
                        try:
                            from cua.tools.uia import _foreground_control
                            fg = _foreground_control()
                            if fg is not None:
                                uia_lines = []

                                def _build_uia_tree(ctrl, depth=0, max_depth=3):
                                    if depth > max_depth:
                                        return
                                    indent = "  " * depth
                                    name = ctrl.Name or ""
                                    ctype = ctrl.ControlTypeName
                                    auto_id = ctrl.AutomationId or ""

                                    # Try to read value for editable/text controls
                                    value = ""
                                    if name and ctype in ("Edit", "Document", "Text", "DataItem"):
                                        try:
                                            vp = ctrl.GetValuePattern()
                                            if vp.Value:
                                                value = f' = "{vp.Value[:60]}"'
                                        except Exception:
                                            pass

                                    label = f"{indent}{ctype}"
                                    if name:
                                        label += f" '{name}'"
                                    if auto_id:
                                        label += f" #{auto_id}"
                                    if value:
                                        label += value

                                    rect = ctrl.BoundingRectangle
                                    if rect and rect.width() > 0:
                                        label += f" ({rect.left}, {rect.top})"

                                    uia_lines.append(label)

                                    for child in ctrl.GetChildren():
                                        _build_uia_tree(child, depth + 1, max_depth)

                                uia_lines.append(f"Active: {fg.Name}")
                                _build_uia_tree(fg)
                                uia_tree = "\n".join(uia_lines[:80])
                        except Exception as e:
                            uia_tree = f"(UIA inspection failed: {e})"

                        print(f"  [ocr-clean] UIA tree: {len(uia_tree)} chars")

                        # Fork agent context. messages already includes the tool
                        # and user image messages from the screenshot result.
                        clean_messages = list(messages)

                        clean_messages.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": (
                                    f"Raw OCR from screenshot (normalized coordinates in parentheses):\n"
                                    f"{raw_ocr}\n\n"
                                    f"Latest list_windows result:\n{latest_windows}\n\n"
                                    f"Latest web_get_content result:\n{latest_web}\n\n"
                                    f"Latest web_list_tabs result:\n{latest_tabs}\n\n"
                                    f"UIA control tree of foreground window (with content):\n"
                                    f"{uia_tree}\n\n"
                                    f"Based on all the above, summarize what's useful for the next step.\n"
                                    f"- Desktop UI: use list_windows + OCR + UIA to describe windows, "
                                    f"their controls, and WHERE key elements are (coordinates).\n"
                                    f"- UIA controls: note buttons, menus, input fields with their names. "
                                    f"Suggest uia_click/uia_set_value/uia_get_text for native apps "
                                    f"instead of coordinate-based clicking.\n"
                                    f"- Web content: if web_get_content has data, describe page elements. "
                                    f"Suggest web tools for precise page interaction.\n"
                                    f"- Note any input fields. Remind that paste_text is the default for ALL text input — never use type_keys for content.\n"
                                    f"Be concise and actionable, under 400 characters."
                                )},
                            ],
                        })
                        clean_resp = client.chat.completions.create(
                            model=model,
                            messages=clean_messages,
                            max_tokens=512,
                            extra_body={"thinking": {"type": "disabled"}},
                        )
                        cleaned_ocr = clean_resp.choices[0].message.content or ""
                        if hasattr(clean_resp, "usage") and clean_resp.usage:
                            token_usage["prompt"] += clean_resp.usage.prompt_tokens or 0
                            token_usage["completion"] += clean_resp.usage.completion_tokens or 0
                            token_usage["total"] += clean_resp.usage.total_tokens or 0
                        print(f"  [ocr-clean] cleaned: {cleaned_ocr[:120]}")

                        # Append cleaned OCR as a user message for the agent
                        messages.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"Cleaned OCR text: {cleaned_ocr}"},
                            ],
                        })
                    except Exception as e:
                        print(f"  [ocr-clean] failed: {e}")

                # Verify + Think: after a state-modifying action, show before/after and reflect.
                if name in VERIFY_TOOLS:
                    do_verify = args.get("verify", True)
                    if not do_verify:
                        # Skip verify but still inject think
                        print(f"  [verify] skipped (verify=false), injecting think...")
                        from cua.tools.think import THINK_PROMPT
                        messages.append({"role": "user", "content": [{"type": "text", "text": THINK_PROMPT}]})
                    else:
                        print(f"  [verify] waiting 1s, taking after-screenshot...")
                        time.sleep(1.0)
                    img_after = np.array(sct.grab(monitor))
                    img = img_after  # update current screenshot

                    before_rgb = img_before[..., [2, 1, 0]]
                    after_rgb = img_after[..., [2, 1, 0]]

                    # OCR both screenshots
                    from cua.tools.screenshot import _get_ocr_engine
                    ocr = _get_ocr_engine()
                    before_result, _ = ocr(before_rgb)
                    after_result, _ = ocr(after_rgb)

                    def _format_ocr(result) -> str:
                        if not result:
                            return "[no text]"
                        return " ".join(f"[{item[1]}]" for item in result)

                    before_ocr = _format_ocr(before_result)
                    after_ocr = _format_ocr(after_result)
                    print(f"  [verify] OCR: before={len(before_result or [])} blocks, after={len(after_result or [])} blocks")

                    # Fork agent context for the analyst — inherits all agent history,
                    # but the analyst's response does NOT go back into agent context.
                    delta_summary = ""
                    try:
                        analyst_messages = list(messages)  # shallow copy of agent history
                        analyst_messages.append({
                            "role": "user",
                            "content": [
                                {"type": "text", "text": f"BEFORE {name}:"},
                                {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(before_rgb)}},
                                {"type": "text", "text": f"BEFORE OCR: {before_ocr}"},
                                {"type": "text", "text": f"AFTER {name}:"},
                                {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(after_rgb)}},
                                {"type": "text", "text": f"AFTER OCR: {after_ocr}"},
                                {"type": "text", "text": (
                                    "You are analyzing whether this action succeeded. "
                                    "Compare BEFORE and AFTER screenshots and OCR. "
                                    "Output a concise summary in Chinese under 200 chars: "
                                    "what changed and whether the action had the expected effect."
                                )},
                            ],
                        })
                        analysis = client.chat.completions.create(
                            model=model,
                            messages=analyst_messages,
                            max_tokens=256,
                            extra_body={"thinking": {"type": "disabled"}},
                        )
                        delta_summary = analysis.choices[0].message.content or ""
                        if hasattr(analysis, "usage") and analysis.usage:
                            token_usage["prompt"] += analysis.usage.prompt_tokens or 0
                            token_usage["completion"] += analysis.usage.completion_tokens or 0
                            token_usage["total"] += analysis.usage.total_tokens or 0
                        print(f"  [verify] analyst: {delta_summary[:120]}")
                    except Exception as e:
                        print(f"  [verify] analyst failed: {e}")

                    from cua.tools.think import THINK_PROMPT

                    verify_content = [
                        {"type": "text", "text": f"BEFORE {name}:"},
                        {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(before_rgb)}},
                        {"type": "text", "text": f"AFTER {name}:"},
                        {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(after_rgb)}},
                    ]
                    if delta_summary:
                        verify_content.append({
                            "type": "text",
                            "text": (
                                f"Change analysis (from independent analyst): {delta_summary}\n\n"
                                f"You just called {name}. Compare the BEFORE/AFTER screenshots "
                                f"to verify the action's effect. Then reflect on what to do next.\n\n"
                                f"{THINK_PROMPT}"
                            ),
                        })
                    else:
                        verify_content.append({
                            "type": "text",
                            "text": (
                                f"You just called {name}. Compare the BEFORE/AFTER screenshots "
                                f"to verify the action's effect. "
                                f"Then reflect on what to do next.\n\n"
                                f"{THINK_PROMPT}"
                            ),
                        })
                    messages.append({"role": "user", "content": verify_content})

                # Context cleanup after state-changing actions
                if name in VERIFY_TOOLS:
                    ac = _cleanup_context(messages)
                    # Every 10 actions beyond 20, compress the oldest 10
                    while ac >= _compressed_up_to + 20:
                        _compress_context(messages, client, model, max_tokens, _compressed_up_to)
                        _compressed_up_to += 10

        return {
            "success": False,
            "summary": f"Reached maximum iterations ({max_iterations}) without calling finish.",
            "steps": [],
            "tokens": token_usage,
            "__current_tool_log": _current_tool_log,
        }

"""Agent core loop: drives the Kimi K3 tool-calling cycle."""
import json
import time

import mss
import numpy as np
import openai
from openai import OpenAI

from cua.config import load_config
from cua.tools import ALL_TOOLS, execute_tool
from cua.tools.loader import _search_similar
from cua.tools.screenshot import _np_to_png_b64, downsample_for_vlm
from cua.learning import get_learnings_prompt, index_knowledge

# Module-level tool log for Ctrl+C recovery
_current_tool_log: list[str] = []


def get_last_tool_log() -> list[str]:
    """Get tool calls from the most recent (possibly interrupted) task."""
    return list(_current_tool_log)

# Tools that modify system state — trigger auto-verification after execution
VERIFY_TOOLS = {
    # Desktop action tools
    "click", "drag", "scroll", "type_keys", "paste_text",
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

# Perception tools — sync physical cursor before executing
PERCEPTION_TOOLS = {
    "screenshot", "magnifier", "ocr",
    "list_windows", "web_get_content", "web_list_tabs",
    "read_clipboard", "uia_inspect", "uia_get_text",
}


SYSTEM_PROMPT = """You are a Computer Use Agent (CUA) controlling a Windows desktop through tool calls. Core loop: screenshot → assess → act → verify → repeat → finish().

## Critical Rules

1. **ALWAYS end with finish()**: You CANNOT output text directly. The ONLY way to deliver results is finish(success=..., summary=..., steps=[...]). Call finish() when done, stuck, or the task is impossible. Never output a text summary without finish().

2. **Act, don't describe**: Call tools directly — one action per turn. Briefly explain your reasoning in each tool call's content field, but don't narrate a plan without acting.

3. **paste_text for ALL text input**: Use paste_text(text) for Chinese, English, code, URLs, file names — everything. type_keys is ONLY for keyboard shortcuts (ctrl+c, alt+tab, enter, escape) and special keys (tab, f5, backspace). Never use type_keys to type words. If clipboard paste is blocked, try uia_set_value first, then type_keys as last resort.

4. **Web tasks → web tools DIRECTLY**: For ANY browser-based task, call web_navigate(url) as your first action. Do NOT open a desktop browser — web tools run their own. Workflow: web_navigate → web_get_content → web_click/web_type/web_press. You never need desktop tools for web pages.

5. **Native apps → structured tools FIRST**: For Microsoft Office (Word, Excel, PowerPoint) and native Windows apps: list_windows → focus_window → uia_inspect → uia_click/uia_set_value/uia_get_text. Only fall back to screenshot + coordinate clicking when UIA tools can't access the target. Note: "Office" in Chinese contexts usually means Microsoft Office. WPS is a separate product — only use it if the task explicitly mentions WPS.

6. **Verify state-changing actions**: Most action tools accept an optional `verify` boolean (default true). When enabled, BEFORE/AFTER screenshots are compared to confirm the action's effect. Set verify=false only for rapid multi-step sequences. think() is always injected after every action.

7. **Coordinates**: (0,0)=top-left, (1,1)=bottom-right. Use exactly 4 decimal places. The annotated screenshot shows the current cursor position (red crosshair). To click: set_mouse() first, then click().

8. **Use memory proactively**: Recall related memories at task start with memory(action='recall'). Save key findings during the task — don't wait until finish. Use rethink() after accumulating 5+ notes to consolidate. Use note() for quick persistent notes.

9. **Keep trying**: If one approach fails, try another. Use ocr() and magnifier() to inspect the screen. Call request_human_help() for logins, CAPTCHAs, or UAC dialogs.

## Tools

### Desktop Interaction
- **screenshot**: Full-screen capture with virtual cursor overlay (red crosshair + circle). Always call first to assess state.
- **set_mouse(x, y)**: Move cursor to normalized coordinates (0.0-1.0).
- **click(button, type, count, scroll)**: Click at cursor position. button: left/right/middle. type: single/double. scroll: positive=up, negative=down.
- **drag(from_x, from_y, to_x, to_y)**: Drag from one position to another.
- **scroll(x, y, direction, amount)**: Scroll at position. direction: up/down/pageup/pagedown.
- **type_keys(keys, repeat)**: Keyboard shortcuts ONLY. For text input, use paste_text instead.
- **paste_text(text)**: Copy text to clipboard → Ctrl+V. Primary text input for ALL content types.
- **magnifier**: Square crop centered on cursor for fine-detail inspection.
- **ocr**: Extract text from current screenshot with positions and confidence scores.
- **read_clipboard**: Read system clipboard content.
- **wait(seconds)**: Wait 0.5-10s. Use after launching apps instead of repeated screenshots.

### Windows Management
- **list_windows**: List all open windows (titles, positions, visibility). Use FIRST for any desktop task.
- **focus_window(title)**: Bring window to front by title (partial match). Use list_windows first.
- **launch_app(name)**: Launch via Start menu search (Win → type name → Enter). Only finds apps indexed by Windows Search. For "Office" tasks, launch "Microsoft Word/Excel/PowerPoint" unless the task explicitly says WPS. ⚠️ If the app is not installed, Windows will fall back to a Bing search in Edge — check list_windows() after launching to confirm the app actually opened.

### Web Browser (Playwright)
- **web_navigate(url)**: Open URL in built-in browser. Use IMMEDIATELY for any web task.
- **web_get_content()**: Read page structure — headings, buttons, links, inputs, text. More precise than OCR.
- **web_click(text)**: Click element by visible text. No coordinate guessing needed.
- **web_type(label, text)**: Type into input field matched by placeholder/label.
- **web_press(key)**: Press key on page (Enter to submit, Escape to close modals, Tab to switch focus).
- **web_scroll(amount)**: Scroll page. Positive=down, negative=up. Use ~500 for a typical scroll.
- **web_new_tab / web_switch_tab(index) / web_close_tab / web_list_tabs**: Tab management.
- **web_refresh / web_back / web_forward**: Page navigation.

### Native App Automation (UIA)
- **uia_inspect(depth)**: Inspect UI control tree of foreground window (names, types, positions).
- **uia_click(name)**: Click control by name (partial match). Reliable for buttons, menus, tabs.
- **uia_set_value(name, value)**: Set value of input control by name. Supports Chinese.
- **uia_get_text(name)**: Read text/value from a control by name.
- **run_command(command)**: Win+R → type command → Enter. For paths, executables, shell commands.

### Files & Documents
- **file_read(path)**: Read text file. Use instead of GUI to check file content.
- **file_write(path, content)**: Write text to file. Creates parent directories.
- **ReadDocument(path)**: Upload to Kimi and extract text (PDF, DOCX, images). Returns doc:<sha8> reference.
- **ListDocuments / DeleteDocument(ref) / CleanupDocuments**: Manage uploaded Kimi files (quota: 1000).

### Memory & Knowledge
- **note(text)**: Save to persistent notepad. Notes appear automatically in think(). No-arg call reads all notes.
- **memory(action, key, value)**: Remote persistent KV store across sessions. action: save/recall.
- **rethink(content)**: AI-driven consolidation of accumulated notes and findings.
- **DraftContent(task, persona, prefill, max_chars)**: Write long-form content in isolated session with own persona. Returns file path + preview — use file_read for full content.
- **GenerateImage(requirement)**: Generate SVG image via multi-round generation + visual self-review. Returns PNG path.

### Meta
- **think()**: Pause to reflect and plan next steps. Use when stuck, unsure, or after completing a sub-task. Does NOT perform actions — gives you space to think.
- **finish(success, summary, steps)**: MANDATORY. End the task. success: true/false. summary: what was accomplished or why it failed. steps: ordered list of key actions.
- **request_human_help(request)**: Pause for human assistance. Use for logins, CAPTCHAs, UAC dialogs."""


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

        # After compression, clean up: strip tool_calls + tool messages.
        # Assistant tool_calls may reference tool messages that were compressed away.
        valid_tool_ids = {m.get("tool_call_id", "") for m in keep if m["role"] == "tool"}
        cleaned_keep = []
        for msg in keep:
            if msg["role"] == "assistant" and "tool_calls" in msg:
                # Keep only tool_calls that have matching tool messages
                msg["tool_calls"] = [tc for tc in msg["tool_calls"] if tc.get("id") in valid_tool_ids]
                if not msg["tool_calls"]:
                    del msg["tool_calls"]
                    if not msg.get("content"):
                        continue  # Skip empty assistant message entirely
            if msg["role"] == "tool":
                # Remove tool messages whose tool_call_id no longer has a matching
                # assistant tool_call in keep
                tc_id = msg.get("tool_call_id", "")
                has_assistant = any(
                    m["role"] == "assistant" and "tool_calls" in m
                    and any(tc.get("id") == tc_id for tc in m["tool_calls"])
                    for m in keep
                )
                if not has_assistant:
                    continue  # Skip orphaned tool message
            cleaned_keep.append(msg)

        messages[:] = cleaned_keep

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

    model = config.get("model", "kimi-k3")
    base_url = config.get("base_url", "https://api.moonshot.cn/v1")
    max_tokens = config.get("max_completion_tokens") or config.get("max_tokens", 131072)
    max_iterations = config.get("max_iterations", 50)

    # Create OpenAI-compatible client
    client = OpenAI(api_key=api_key, base_url=base_url)

    # Index knowledge base on startup
    index_knowledge()

    # K3: 1M context + auto-caching — always send all tools, no classification needed.
    # The model handles tool selection natively.
    active_tools = ALL_TOOLS
    print(f"  Tools: {len(ALL_TOOLS)} total (K3 native selection, auto-cached)")

    # Search ChromaDB for similar past learnings to inject into first think()
    from cua.tools.think import set_think_context
    similar_text = _search_similar(task[:80])
    set_think_context(similar_text)

    # Search knowledge base for relevant manual guidance
    from cua.learning import search_knowledge
    knowledge_text = search_knowledge(task[:80])
    if knowledge_text:
        print(f"  [knowledge] task-start search: {len(knowledge_text.splitlines())} hits")

    token_usage = {"prompt": 0, "completion": 0, "total": 0}
    _compressed_up_to = 0   # how many action-rounds have been compressed so far
    _total_action_count = 0  # cumulative count, never decremented by cleanup

    from cua.tools.utility import clear_notes
    clear_notes()

    # Start trajectory recorder for potential replay
    from cua.replay import TrajectoryRecorder
    recorder = TrajectoryRecorder(task)

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screen_w = monitor["width"]
        screen_h = monitor["height"]

        # Virtual mouse starts at center
        mouse_pos = (0.5, 0.5)

        # Initialize messages early (needed by replay failure handler)
        learnings_text = get_learnings_prompt()
        knowledge_section = ""
        if knowledge_text:
            knowledge_section = f"\n## Relevant Knowledge Base Guidance\n\n{knowledge_text}\n"
        system_content = SYSTEM_PROMPT + learnings_text + knowledge_section
        messages = [{"role": "system", "content": system_content}]

        # Check for trajectory replay opportunity
        _replay_result = None
        if similar_text:
            from cua.replay import attempt_replay, find_trajectory
            print(f"  [replay] checking replay viability...")
            traj = find_trajectory(task[:80])
            if traj:
                print(f"  [replay] trajectory found ({len(traj['steps'])} steps), judging...")
                _replay_result = attempt_replay(
                    traj, task, similar_text, sct, mouse_pos, screen_w, screen_h,
                    client, model
                )
                if _replay_result.get("replayed"):
                    return {
                        "success": True,
                        "summary": f"Task completed via replay ({_replay_result['steps_done']} steps replayed).",
                        "steps": _replay_result.get("tool_log", []),
                        "tokens": token_usage,
                        "_tool_calls_log": _replay_result.get("tool_log", []),
                    }
                else:
                    print(f"  [replay] failed: {_replay_result.get('abort_reason', '')[:80]}")
                    if _replay_result.get("steps_done", 0) > 0:
                        # Pre-populate recorder with successful replay steps
                        for step in traj["steps"][:_replay_result["steps_done"]]:
                            recorder.steps.append(step)
                        messages.append({
                            "role": "user",
                            "content": [{"type": "text", "text": (
                                f"Trajectory replay was attempted but failed at step "
                                f"{_replay_result['steps_done']}/{_replay_result['steps_total']}.\n"
                                f"Reason: {_replay_result.get('abort_reason', '')}\n"
                                f"Agent taking over. Assess the current state and complete the task."
                            )}],
                        })
            else:
                print(f"  [replay] no matching trajectory found")

        # Initial screenshot for state (not sent to model yet)
        img = np.array(sct.grab(monitor))  # BGRA, (H, W, 4)

        # Tool call log (module-level for Ctrl+C recovery)
        _current_tool_log.clear()

        # Add startup recall hint to existing messages
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": (
                    f"Task: {task}\n"
                    f"Tip: recall past learnings with memory(action='recall'). "
                    f"Save new findings with memory(action='save') during the task."
                )},
            ],
        })
        messages.append({
            "role": "user",
            "content": _build_initial_content(task, mouse_pos, screen_w, screen_h),
        })

        while True:
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
                        max_completion_tokens=max_tokens,
                        reasoning_effort="max",
                    )
                except openai.AuthenticationError:
                    raise  # Auth errors are not retryable
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
                    # K3: preserve reasoning_content in text-only responses too
                    text_msg = {"role": "assistant", "content": msg.content}
                    if getattr(msg, "reasoning_content", None):
                        text_msg["reasoning_content"] = msg.reasoning_content
                    messages.append(text_msg)
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
    
                # K3: MUST preserve complete assistant message including reasoning_content.
                # Use model_dump() to capture all fields the API returns.
                try:
                    assistant_msg = msg.model_dump(exclude_none=True)
                except Exception:
                    # Fallback: manual reconstruction with reasoning_content
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
                    if getattr(msg, "reasoning_content", None):
                        assistant_msg["reasoning_content"] = msg.reasoning_content
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
    
                    # Record step (only save screenshots for action tools)
                    save_screenshot = (name in VERIFY_TOOLS)
                    recorder.record_step(name, args, img, screen_w, screen_h, mouse_pos, save_screenshot=save_screenshot)
    
                    # Save before-screenshot for verify step
                    img_before = img.copy() if name in VERIFY_TOOLS else None
    
                    # Before perception tools, sync physical cursor to virtual position
                    if name in PERCEPTION_TOOLS:
                        import pyautogui
                        px = round(mouse_pos[0] * screen_w)
                        py = round(mouse_pos[1] * screen_h)
                        pyautogui.moveTo(px, py)
    
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
                        result["_finish_report"]["_tool_calls_log"] = _current_tool_log
    
                        # Save trajectory for future replay
                        success = result["_finish_report"].get("success", False)
                        action_steps = sum(1 for s in recorder.steps if s.get("screenshot_b64") and len(s["screenshot_b64"]) > 100)
                        print(f"  [replay] finished: success={success}, action_steps={action_steps}/{len(recorder.steps)}")
                        if success:
                            try:
                                traj_id = recorder.save(
                                    task_summary=task[:80],
                                    client=client, model=model,
                                )
                                if traj_id:
                                    print(f"  [replay] trajectory saved: {traj_id}")
                                else:
                                    print(f"  [replay] trajectory skipped: need >=1 action step with screenshot")
                            except Exception as e:
                                print(f"  [replay] trajectory save failed: {e}")
    
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
                                from cua.tools.uia import _foreground_control, _force_read
                                fg = _foreground_control()
                                if fg is not None:
                                    uia_lines = []
    
                                    def _build_uia_tree(ctrl, depth=0, max_depth=6):
                                        if depth > max_depth:
                                            return
                                        _force_read(ctrl)  # triggers lazy UIA provider
                                        indent = "  " * depth
                                        name = ctrl.Name or ""
                                        ctype = ctrl.ControlTypeName
                                        auto_id = ctrl.AutomationId or ""
    
                                        # Force-read value on all nodes
                                        value = ""
                                        try:
                                            vp = ctrl.GetValuePattern()
                                            if vp.Value:
                                                value = f' = "{vp.Value[:80]}"'
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
                                        f"Raw OCR: {raw_ocr}\n\n"
                                        f"list_windows: {latest_windows}\n\n"
                                        f"web_get_content: {latest_web}\n\n"
                                        f"web_list_tabs: {latest_tabs}\n\n"
                                        f"UIA tree (foreground window): {uia_tree}\n\n"
                                        f"Synthesize the above into a concise situational summary (under 400 chars). "
                                        f"Surface: (1) which windows/apps are open, (2) where key interactive elements are "
                                        f"(coordinates for click targets, UIA control names for uia_click/uia_set_value), "
                                        f"(3) what input fields exist, (4) what action to take next. "
                                        f"Be specific and actionable."
                                    )},
                                ],
                            })
                            clean_resp = client.chat.completions.create(
                                model=model,
                                messages=clean_messages,
                                max_tokens=512,
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
                    do_verify = args.get("verify", True) if name in VERIFY_TOOLS else True
    
                    if name in VERIFY_TOOLS and do_verify:
                        # Start BEFORE OCR in background during the 1s wait
                        from concurrent.futures import ThreadPoolExecutor
                        from cua.tools.screenshot import _get_ocr_engine
                        # Downscale for VLM, keep full-res for OCR
                        before_scaled, _, _ = downsample_for_vlm(img_before, mouse_pos, screen_w, screen_h)
                        before_rgb = before_scaled[..., [2, 1, 0]]
                        before_full = img_before[..., [2, 1, 0]]
    
                        def _ocr_before():
                            engine = _get_ocr_engine()
                            return engine(before_full)
    
                        executor = ThreadPoolExecutor(max_workers=1)
                        try:
                            before_future = executor.submit(_ocr_before)
    
                            print(f"  [verify] waiting 1s (OCR in background), taking after-screenshot...")
                            time.sleep(1.0)
                            img_after = np.array(sct.grab(monitor))
                            img = img_after  # update current screenshot
    
                            after_scaled, _, _ = downsample_for_vlm(img_after, mouse_pos, screen_w, screen_h)
                            after_rgb = after_scaled[..., [2, 1, 0]]
                            after_full = img_after[..., [2, 1, 0]]
    
                            # Collect BEFORE OCR result + run AFTER OCR
                            try:
                                before_result, _ = before_future.result()
                            except Exception:
                                before_result = None
                            try:
                                ocr = _get_ocr_engine()
                                after_result, _ = ocr(after_full)
                            except Exception:
                                after_result = None
                        finally:
                            executor.shutdown(wait=False)
    
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
                                    {"type": "text", "text": (
                                        f"Task: {task}\n"
                                        + (f"Relevant past learnings:\n{similar_text}\n\n" if similar_text else "")
                                        + f"Action just taken: {name}\n"
                                        + "Analyze whether this action had the expected effect."
                                    )},
                                    {"type": "text", "text": f"BEFORE {name}:"},
                                    {"type": "image_url", "image_url": {"url": _np_to_png_b64(before_rgb)}},
                                    {"type": "text", "text": f"BEFORE OCR: {before_ocr}"},
                                    {"type": "text", "text": f"AFTER {name}:"},
                                    {"type": "image_url", "image_url": {"url": _np_to_png_b64(after_rgb)}},
                                    {"type": "text", "text": f"AFTER OCR: {after_ocr}"},
                                    {"type": "text", "text": (
                                        "Compare BEFORE and AFTER screenshots and OCR. "
                                        "Output a concise summary in Chinese under 200 chars: "
                                        "what changed and whether the action had the expected effect.\n"
                                        "Also output a short English phrase (under 80 chars) for knowledge "
                                        "base search. Include the specific application name, UI element type, "
                                        "and action attempted. Be specific — don't generalize.\n"
                                        "Example: 'WeChat service account chat keyboard icon button not found'\n"
                                        "Format as JSON: "
                                        '{"summary": "中文总结", "en_query": "English search phrase"}'
                                    )},
                                ],
                            })
                            analysis = client.chat.completions.create(
                                model=model,
                                messages=analyst_messages,
                                max_tokens=256,
                                response_format={"type": "json_object"},
                            )
                            raw_analyst = analysis.choices[0].message.content or ""
                            if hasattr(analysis, "usage") and analysis.usage:
                                token_usage["prompt"] += analysis.usage.prompt_tokens or 0
                                token_usage["completion"] += analysis.usage.completion_tokens or 0
                                token_usage["total"] += analysis.usage.total_tokens or 0
    
                            # Parse analyst JSON for summary + knowledge search
                            delta_summary = raw_analyst
                            knowledge_hits = ""
                            try:
                                parsed = json.loads(raw_analyst)
                                delta_summary = parsed.get("summary", raw_analyst)
                                en_query = parsed.get("en_query", "")
                                if en_query:
                                    from cua.learning import search_knowledge
                                    knowledge_hits = search_knowledge(en_query)
                                    if knowledge_hits:
                                        print(f"  [verify] knowledge: {len(knowledge_hits.splitlines())} hits")
                            except (json.JSONDecodeError, Exception):
                                pass  # Use raw text as summary
    
                            print(f"  [verify] analyst: {delta_summary[:120]}")
                        except Exception as e:
                            print(f"  [verify] analyst failed: {e}")
    
                        from cua.tools.think import THINK_PROMPT
    
                        verify_content = [
                            {"type": "text", "text": f"BEFORE {name}:"},
                            {"type": "image_url", "image_url": {"url": _np_to_png_b64(before_rgb)}},
                            {"type": "text", "text": f"AFTER {name}:"},
                            {"type": "image_url", "image_url": {"url": _np_to_png_b64(after_rgb)}},
                        ]
                        if delta_summary:
                            text = (
                                f"Analyst report: {delta_summary}\n\n"
                                + (f"Knowledge base: {knowledge_hits}\n\n" if knowledge_hits else "")
                                + f"Verify the effect of {name} by comparing BEFORE/AFTER above. "
                                + f"Then:\n\n{THINK_PROMPT}"
                            )
                            verify_content.append({"type": "text", "text": text})
                        else:
                            verify_content.append({
                                "type": "text",
                                "text": (
                                    f"Verify the effect of {name} by comparing BEFORE/AFTER above. "
                                    f"Then:\n\n{THINK_PROMPT}"
                                ),
                            })
                        messages.append({"role": "user", "content": verify_content})
    
                    # Context cleanup after state-changing actions
                    if name in VERIFY_TOOLS:
                        _total_action_count += 1
                        _cleanup_context(messages)
    
                        # Update the recorded step with AFTER screenshot
                        recorder.update_last_step_screenshot(img, screen_w, screen_h, mouse_pos)
    
                        # Every 5 actions, nudge to use memory if not used recently
                        if _total_action_count > 0 and _total_action_count % 5 == 0:
                            messages.append({
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": (
                                        f"You've taken {_total_action_count} actions. "
                                        "Consider saving key findings to memory(action='save'). "
                                        "If you've accumulated many notes, use rethink() to consolidate."
                                    )},
                                ],
                            })
                        # Every 10 actions beyond 20, compress the oldest 10
                        if _total_action_count >= _compressed_up_to + 20:
                            _compress_context(messages, client, model, max_tokens, _compressed_up_to)
                            _compressed_up_to += 10
    
            # Max iterations reached — ask user whether to continue
            print(f"\n  ⏸  Reached {max_iterations} iterations ({len(_current_tool_log)} tool calls).")
            try:
                choice = input("  Continue? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "n"
            if choice == "y":
                extra = 50
                print(f"  ▶  Extending by {extra} iterations (total now {max_iterations + extra})...")
                max_iterations += extra
                # Re-inject the near-limit reminder for the extended batch
                messages.append({
                    "role": "user",
                    "content": (
                        f"Granted {extra} more iterations. Continue working on the task. "
                        "If you're stuck or the task is done, call finish()."
                    ),
                })
                continue  # restart the for loop with new max_iterations
            else:
                return {
                    "success": False,
                    "interrupted": True,
                    "summary": f"Reached {max_iterations} iterations, user chose to stop.",
                    "steps": [],
                    "tokens": token_usage,
                    "_tool_calls_log": _current_tool_log,
                }

"""Fast replay engine — uses recorded templates for AI-free task execution.

Layered acceleration:
  Level 0: OpenCV multi-scale template matching + OCR verification (no AI)
  Level 1: MiniLM embedding similarity matching (lightweight, no API call)
  Level 2: Fall back to full K3 agent loop (heavy, last resort)

Usage: python cua/cli.py --replay "task description"
"""
import json
import os
import time

import numpy as np

# --- Window binding ---


def _find_window(class_name: str, pid: int = None, title_hint: str = "") -> int | None:
    """Find a top-level window matching the recorded template.

    Searches all top-level windows by class name, optionally filtering by PID
    and title substring match. Returns HWND or None.
    """
    import win32gui

    candidates = []

    def _enum(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            cls = win32gui.GetClassName(hwnd)
        except Exception:
            return
        if class_name.lower() not in cls.lower():
            return

        try:
            title = win32gui.GetWindowText(hwnd)
        except Exception:
            title = ""
        try:
            _, wpid = win32gui.GetWindowThreadProcessId(hwnd)
        except Exception:
            wpid = 0

        score = 0
        if pid and wpid == pid:
            score += 100
        if title_hint and title_hint.lower() in title.lower():
            score += 50
        rect = win32gui.GetWindowRect(hwnd)
        area = (rect[2] - rect[0]) * (rect[3] - rect[1])
        score += min(area // 10000, 30)  # prefer larger windows

        candidates.append((score, hwnd, title, wpid))

    win32gui.EnumWindows(_enum, None)
    candidates.sort(key=lambda x: -x[0])

    if candidates:
        best = candidates[0]
        print(f"  [replay] window found: class={class_name} hwnd={best[1]} "
              f"title='{best[2][:40]}' pid={best[3]}")
        return best[1]
    return None


def _activate_window(hwnd: int) -> bool:
    """Restore and bring a window to foreground."""
    import win32gui
    import win32con

    try:
        # Restore if minimized
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            time.sleep(0.3)
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.2)
        return True
    except Exception as e:
        print(f"  [replay] activate failed: {e}")
        return False


def _find_obscuring_windows(hwnd: int) -> list[int]:
    """Enumerate windows at higher Z-order that may obscure the target.

    Returns list of HWNDs that intersect the target's rectangle.
    """
    import win32gui

    try:
        target_rect = win32gui.GetWindowRect(hwnd)
    except Exception:
        return []

    obscuring = []

    def _enum(ohwnd, _):
        if ohwnd == hwnd:
            return
        if not win32gui.IsWindowVisible(ohwnd):
            return
        try:
            orect = win32gui.GetWindowRect(ohwnd)
        except Exception:
            return
        # Check rectangle intersection
        tx1, ty1, tx2, ty2 = target_rect
        ox1, oy1, ox2, oy2 = orect
        if tx1 < ox2 and tx2 > ox1 and ty1 < oy2 and ty2 > oy1:
            # Only count windows that are reasonably sized (not tiny overlays)
            ow, oh = ox2 - ox1, oy2 - oy1
            if ow > 40 and oh > 40:
                obscuring.append(ohwnd)

    win32gui.EnumWindows(_enum, None)
    return obscuring


# --- Local visual diff (popup detection) ---


def _detect_popup_in_roi(
    screenshot_bgr: np.ndarray,
    expected_clean_bgr: np.ndarray,
    threshold: int = 40,
) -> bool:
    """Check if ROI region has a popup/overlay by comparing to clean template.

    Returns True if significant difference detected (likely a popup).
    """
    import cv2

    if screenshot_bgr.shape != expected_clean_bgr.shape:
        # Resize clean template to match current ROI size
        expected_clean_bgr = cv2.resize(
            expected_clean_bgr,
            (screenshot_bgr.shape[1], screenshot_bgr.shape[0]),
            interpolation=cv2.INTER_AREA,
        )

    diff = cv2.absdiff(screenshot_bgr, expected_clean_bgr)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

    # Filter small noise
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    diff_ratio = np.count_nonzero(cleaned) / cleaned.size
    return diff_ratio > 0.15  # >15% area changed = likely popup


# --- Level 0: OpenCV template matching ---


def _template_match(
    screenshot_bgr: np.ndarray,
    template_bgr: np.ndarray,
    roi_rect: tuple[int, int, int, int],
    threshold: float = 0.70,
) -> tuple[tuple[int, int] | None, float]:
    """Multi-scale template matching restricted to ROI region.

    Args:
        screenshot_bgr: Full window screenshot (BGR).
        template_bgr: Button template image.
        roi_rect: (x, y, w, h) relative to window top-left.
        threshold: Minimum TM_CCOEFF_NORMED score to accept.

    Returns:
        ((center_x, center_y), score) or (None, 0) if no match.
    """
    import cv2

    x, y, w, h = roi_rect
    # Expand ROI by 100px for window offset tolerance
    margin = 100
    x1 = max(0, x - margin)
    y1 = max(0, y - margin)
    x2 = min(screenshot_bgr.shape[1], x + w + margin)
    y2 = min(screenshot_bgr.shape[0], y + h + margin)

    if x2 <= x1 or y2 <= y1:
        return None, 0

    roi = screenshot_bgr[y1:y2, x1:x2]
    th, tw = template_bgr.shape[:2]

    if th > roi.shape[0] or tw > roi.shape[1]:
        return None, 0

    best_score = 0
    best_pt = None

    # Try multiple scales (0.6x to 1.4x)
    for scale in [0.6, 0.8, 1.0, 1.2, 1.4]:
        scaled = cv2.resize(
            template_bgr,
            (int(tw * scale), int(th * scale)),
            interpolation=cv2.INTER_AREA,
        )
        if scaled.shape[0] > roi.shape[0] or scaled.shape[1] > roi.shape[1]:
            continue

        result = cv2.matchTemplate(roi, scaled, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val > best_score:
            best_score = max_val
            best_pt = (
                max_loc[0] + scaled.shape[1] // 2 + x1,
                max_loc[1] + scaled.shape[0] // 2 + y1,
            )

    if best_score >= threshold and best_pt is not None:
        return best_pt, best_score

    return None, best_score


# --- Level 1: Embedding similarity ---


def _embedding_match(
    screenshot_bgr: np.ndarray,
    target_vec: np.ndarray,
    roi_rect: tuple[int, int, int, int],
    step: int = 20,
    min_similarity: float = 0.60,
) -> tuple[tuple[int, int] | None, float]:
    """Sliding-window feature matching using MiniLM embeddings of OCR text.

    Divides ROI into patches, runs OCR on each, embeds text, compares to target.
    """
    from cua.recorder import _embed_text
    from cua.tools.screenshot import _get_ocr_engine

    x, y, w, h = roi_rect
    margin = 100
    x1 = max(0, x - margin)
    y1 = max(0, y - margin)
    x2 = min(screenshot_bgr.shape[1], x + w + margin)
    y2 = min(screenshot_bgr.shape[0], y + h + margin)

    roi = screenshot_bgr[y1:y2, x1:x2]
    rh, rw = roi.shape[:2]
    pw, ph = 80, 40  # patch size

    if rw < pw or rh < ph:
        return None, 0

    best_sim = 0
    best_pt = None
    ocr = _get_ocr_engine()

    for px in range(0, rw - pw, step):
        for py in range(0, rh - ph, step):
            patch = roi[py:py + ph, px:px + pw]
            patch_text = ""
            try:
                results, _ = ocr(patch)
                if results:
                    patch_text = " ".join(r[1] for r in results if r[2] and float(r[2]) > 0.5)
            except Exception:
                pass

            if not patch_text.strip():
                continue

            patch_vec = _embed_text(patch_text)
            sim = float(np.dot(patch_vec, target_vec) /
                        (np.linalg.norm(patch_vec) * np.linalg.norm(target_vec) + 1e-8))

            if sim > best_sim:
                best_sim = sim
                best_pt = (px + pw // 2 + x1, py + ph // 2 + y1)

    if best_sim >= min_similarity and best_pt is not None:
        return best_pt, best_sim

    return None, best_sim


# --- OCR verification ---


def _verify_ocr_text(screenshot_bgr: np.ndarray, click_pt: tuple[int, int],
                     expected_text: str) -> bool:
    """Verify button text at click point matches expected OCR text."""
    if not expected_text.strip():
        return True
    # Strip hash suffix + try function-name only (微信-顶栏-搜索 → 搜索)
    if "_" in expected_text:
        expected_text = expected_text.split("_")[0]
    if "-" in expected_text:
        func_text = expected_text.rsplit("-", 1)[-1]
        # Will try func_text as fallback below
    else:
        func_text = expected_text

    import cv2

    cx, cy = click_pt
    r = 60
    x1 = max(0, cx - r)
    y1 = max(0, cy - r)
    x2 = min(screenshot_bgr.shape[1], cx + r)
    y2 = min(screenshot_bgr.shape[0], cy + r)
    patch = screenshot_bgr[y1:y2, x1:x2]

    try:
        from cua.tools.screenshot import _get_ocr_engine
        ocr = _get_ocr_engine()
        results, _ = ocr(patch)
        if results:
            found_text = " ".join(r[1].lower() for r in results
                                   if r[2] and float(r[2]) > 0.5)
            expected_lower = expected_text.lower()
            func_lower = func_text.lower()
            return (expected_lower in found_text or found_text in expected_lower or
                    func_lower in found_text or found_text in func_lower)
    except Exception:
        pass
    return False


# --- Level 2: K3 agent fallback ---


def _agent_fallback(task: str, config: dict, failed_step: dict) -> dict:
    """Fall back to full K3 agent loop for this step."""
    print(f"  [replay] Level 2: falling back to K3 agent for step "
          f"'{failed_step.get('name', '?')}'")
    from cua.agent import run_task as agent_run
    # Create a focused sub-task for this single step
    sub_task = (
        f"Window context: {failed_step.get('window_class', 'unknown')}\n"
        f"Step: {failed_step.get('ocr_text', failed_step.get('name', 'unknown'))}\n"
        f"Task: {task}\n"
        f"Execute this single step and call finish() when done."
    )
    return agent_run(sub_task, config)


# --- Post-step verification ---


def _verify_step_complete(screenshot_bgr: np.ndarray, prev_screenshot_bgr: np.ndarray) -> bool:
    """Quick check if anything changed after the action."""
    import cv2
    if prev_screenshot_bgr.shape != screenshot_bgr.shape:
        return True  # Different resolution, assume changed
    diff = cv2.absdiff(screenshot_bgr, prev_screenshot_bgr)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    change_ratio = np.count_nonzero(gray > 30) / gray.size
    return change_ratio > 0.001  # Even tiny change counts


# --- Macro validation ---


def _validate_macro(task: str, macro: dict, config: dict) -> tuple[bool, str]:
    """Use K3 to judge whether a macro is appropriate for the task.

    Checks:
      - Semantic fit: does the macro's purpose match the task?
      - Initial conditions: is the desktop in the right state to execute?
      - Pre-requisites: should we Win+D first?

    Returns (approved, reason).
    """
    from openai import OpenAI

    api_key = config.get("moonshot_api_key", "") or os.environ.get("MOONSHOT_API_KEY", "")
    if not api_key:
        return True, "no API key — skipping validation"

    model = config.get("model", "kimi-k3")
    base_url = config.get("base_url", "https://api.moonshot.cn/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)

    steps_summary = "\n".join(
        f"{i+1}. [{s['tool']}] {s.get('ocr_text', '')[:60]}"
        for i, s in enumerate(macro["steps"][:10])
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": (
                    "You validate whether a recorded desktop automation macro can "
                    "be replayed for a given task. Output JSON only."
                )},
                {"role": "user", "content": (
                    f"New task: {task}\n\n"
                    f"Matched macro: {macro['name']}\n"
                    f"Original task: {macro['task']}\n"
                    f"Window: {macro.get('window_class', 'unknown')}\n"
                    f"Steps ({len(macro['steps'])}):\n{steps_summary}\n\n"
                    f"Judge:\n"
                    f"1. Does the macro accomplish the new task? (partial match = yes if overlap > 70%)\n"
                    f"2. Is the original task close enough semantically?\n"
                    f"3. Should we Win+D first? (yes if task starts from desktop, no if inside an app)\n\n"
                    f"Return JSON:\n"
                    f'{{"approved": true/false, "reason": "brief explanation", '
                    f'"win_d_first": true/false}}'
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
        )
        verdict = json.loads(resp.choices[0].message.content or "{}")
        approved = verdict.get("approved", True)
        reason = verdict.get("reason", "validation skipped")
        win_d = verdict.get("win_d_first", False)
        print(f"  [validate] approved={approved} win_d={win_d} "
              f"reason='{reason[:80]}'")
        return approved, win_d
    except Exception as e:
        print(f"  [validate] failed (allowing replay): {e}")
        return True, False  # Allow replay on validation error


# --- Macro replay ---


def replay_macro(macro_name: str, config: dict) -> dict:
    """Replay a saved macro by name. Fast path — no template search needed."""
    from cua.recorder import load_macro
    macro = load_macro(macro_name)
    if not macro:
        print(f"  [replay] macro not found: '{macro_name}'")
        return {"success": False, "summary": f"Macro '{macro_name}' not found",
                "steps": [], "tokens": {"total": 0}, "_tool_calls_log": []}

    print(f"  [replay] macro loaded: {macro['name']} ({len(macro['steps'])} steps)")

    # Validate macro fit with K3
    approved, win_d = _validate_macro(macro_name, macro, config)
    if not approved:
        print(f"  [replay] macro rejected — falling back to K3 agent")
        from cua.agent import run_task as agent_run
        return agent_run(macro_name, config)

    # Win+D to clear desktop if macro starts from clean desktop
    if win_d:
        print(f"  [replay] Win+D to minimize all windows...")
        import pyautogui
        pyautogui.hotkey("win", "d")
        time.sleep(0.5)

    return _execute_steps(macro["task"], config, macro["steps"],
                          macro.get("window_class", ""))


# --- Main replay entry point ---


def replay_task(task: str, config: dict) -> dict:
    """Execute a task using recorded templates, with layered fallback.

    Returns the same report dict format as agent.run_task().
    """
    from cua.recorder import find_template, list_templates
    import cv2
    import mss

    token_usage = {"prompt": 0, "completion": 0, "total": 0}
    tool_log = []

    # 1. Find matching templates for this task
    print(f"  [replay] searching templates for: {task[:60]}...")
    all_templates = list_templates()
    if not all_templates:
        print(f"  [replay] no templates recorded — falling back to K3 agent")
        from cua.agent import run_task as agent_run
        return agent_run(task, config)

    # Group templates by embedding similarity to task
    from cua.recorder import _embed_text
    task_vec = _embed_text(task[:200])
    scored = []
    for tmpl in all_templates:
        emb_hex = tmpl.get("embedding_384", "")
        if emb_hex and len(emb_hex) >= 32:
            emb_bytes = bytes.fromhex(emb_hex.ljust(768, "0")[:768])
            tmpl_vec = np.frombuffer(emb_bytes, dtype=np.float16)
            if len(tmpl_vec) < 384:
                tmpl_vec = np.pad(tmpl_vec, (0, 384 - len(tmpl_vec)))
        else:
            tmpl_vec = np.zeros(384, dtype=np.float16)
        sim = float(np.dot(task_vec, tmpl_vec) /
                    (np.linalg.norm(task_vec) * np.linalg.norm(tmpl_vec) + 1e-8))
        scored.append((sim, tmpl))
    scored.sort(key=lambda x: -x[0])

    # Take top-30 by similarity
    templates = [s[1] for s in scored if s[0] > 0.15][:30]
    best_sim = scored[0][0] if scored else 0

    # If best similarity < 0.10, templates are irrelevant — skip replay
    if not templates or best_sim < 0.10:
        print(f"  [replay] no relevant templates (best sim={best_sim:.3f}) "
              f"— falling back to K3 agent")
        from cua.agent import run_task as agent_run
        return agent_run(task, config)

    print(f"  [replay] {len(templates)} candidate templates (best sim={best_sim:.3f})")

    # 2. Bind to target window
    window_hwnd = None
    for tmpl in templates:
        cls = tmpl["window"]["class"]
        pid = tmpl["window"].get("pid", 0)
        title_hint = tmpl["window"].get("title", "")
        window_hwnd = _find_window(cls, pid, title_hint)
        if window_hwnd:
            break

    if not window_hwnd:
        print(f"  [replay] cannot find target window — falling back to K3 agent")
        from cua.agent import run_task as agent_run
        return agent_run(task, config)

    # 3. Activate window and check for obstructions
    _activate_window(window_hwnd)
    time.sleep(0.5)

    obscuring = _find_obscuring_windows(window_hwnd)
    if obscuring:
        print(f"  [replay] {len(obscuring)} potential obscuring window(s) detected")

    # 4. Execute steps via layered matching
    return _execute_steps(task, config, templates[:15], window_hwnd)


def _execute_steps(task: str, config: dict, steps: list[dict],
                   window_hwnd: int) -> dict:
    """Execute a list of template steps with layered matching.

    Shared by both template-based replay (replay_task) and macro-based
    replay (replay_macro).
    """
    import cv2
    import mss
    import win32gui

    token_usage = {"prompt": 0, "completion": 0, "total": 0}
    tool_log = []
    success_count = 0
    level0_count = 0
    level1_count = 0
    level2_count = 0

    # Get window screen position for ROI offset
    win_rect = win32gui.GetWindowRect(window_hwnd)
    win_offset_x, win_offset_y = win_rect[0], win_rect[1]

    # Select correct monitor and capture
    with mss.MSS() as sct:
        monitor = sct.monitors[1]
        for mon in sct.monitors[1:]:
            if (mon["left"] <= win_offset_x < mon["left"] + mon["width"] and
                mon["top"] <= win_offset_y < mon["top"] + mon["height"]):
                monitor = mon
                break

    with mss.MSS() as sct:
        for i, tmpl in enumerate(steps):
            step_name = tmpl.get("tool", "click")
            # ROI relative to window → convert to screen coords
            roi = (tmpl["roi"]["x"] + win_offset_x,
                    tmpl["roi"]["y"] + win_offset_y,
                    tmpl["roi"]["w"], tmpl["roi"]["h"])
            expected_text = tmpl.get("ocr_text", "")
            emb_hex = tmpl.get("embedding_384", "")
            if emb_hex and len(emb_hex) >= 32:
                emb_hex = emb_hex.ljust(768, "0")[:768]
                emb_vec = np.frombuffer(bytes.fromhex(emb_hex), dtype=np.float16)
                if len(emb_vec) < 384:
                    emb_vec = np.pad(emb_vec, (0, 384 - len(emb_vec)))
            else:
                emb_vec = np.zeros(384, dtype=np.float16)

            # Text / parameter actions: replay directly without visual matching
            if step_name in ("paste_text", "type_keys", "launch_app", "wait",
                             "scroll", "web_navigate", "drag"):
                import pyautogui
                if step_name == "paste_text":
                    text = tmpl.get("args", {}).get("text", "")
                    if text:
                        import pyperclip
                        pyperclip.copy(text)
                        pyautogui.hotkey("ctrl", "v")
                        time.sleep(0.4)
                elif step_name == "type_keys":
                    keys = tmpl.get("args", {}).get("keys", "")
                    if keys:
                        pyautogui.hotkey(*keys.replace(" ", "").split("+"))
                        time.sleep(0.3)
                elif step_name == "launch_app":
                    name = tmpl.get("args", {}).get("name", "")
                    if name:
                        import pyperclip
                        pyautogui.hotkey("win")
                        time.sleep(0.15)
                        pyperclip.copy(name)
                        pyautogui.hotkey("ctrl", "v")
                        time.sleep(0.15)
                        pyautogui.press("enter")
                        time.sleep(1.5)
                elif step_name == "wait":
                    secs = float(tmpl.get("args", {}).get("seconds", 1))
                    time.sleep(max(0.5, min(10, secs)))
                elif step_name == "scroll":
                    direction = tmpl.get("args", {}).get("direction", "down")
                    amount = tmpl.get("args", {}).get("amount", 3)
                    pyautogui.scroll(amount if direction == "up" else -amount)
                    time.sleep(0.2)
                elif step_name == "web_navigate":
                    url = tmpl.get("args", {}).get("url", "")
                    if url:
                        from cua.tools.web import execute_web_navigate
                        execute_web_navigate(url)
                        time.sleep(0.5)
                elif step_name == "drag":
                    args = tmpl.get("args", {})
                    fx, fy = args.get("from_x", 0), args.get("from_y", 0)
                    tx, ty = args.get("to_x", 0), args.get("to_y", 0)
                    sw, sh = pyautogui.size()
                    pyautogui.moveTo(int(fx * sw), int(fy * sh))
                    pyautogui.drag(int((tx - fx) * sw), int((ty - fy) * sh), duration=0.3)
                    time.sleep(0.3)
                success_count += 1
                tool_log.append(f"[sys] {step_name}: '{expected_text[:30]}'")
                print(f"  [replay] system action: {step_name} '{expected_text[:30]}'")
                continue

            # Capture current full-screen screenshot
            img_bgra = np.array(sct.grab(monitor))
            img_bgr = img_bgra[..., :3]

            # Load template image
            tmpl_path = tmpl.get("image_path", "")
            if not tmpl_path or not os.path.exists(tmpl_path):
                print(f"  [replay] template image missing: {tmpl_path} — L2 fallback")
                result = _agent_fallback(task, config, {
                    "name": step_name, "window_class": tmpl.get("window", {}).get("class", ""),
                    "ocr_text": expected_text,
                })
                level2_count += 1
                token_usage["total"] += result.get("tokens", {}).get("total", 0)
                if result.get("success"): success_count += 1
                tool_log.append(f"[L2] {step_name}: missing template")
                continue
            tmpl_bgr = cv2.imread(tmpl_path)
            if tmpl_bgr is None:
                print(f"  [replay] corrupt template image: {tmpl_path} — L2 fallback")
                result = _agent_fallback(task, config, {
                    "name": step_name, "window_class": tmpl.get("window", {}).get("class", ""),
                    "ocr_text": expected_text,
                })
                level2_count += 1
                token_usage["total"] += result.get("tokens", {}).get("total", 0)
                if result.get("success"): success_count += 1
                tool_log.append(f"[L2] {step_name}: corrupt image")
                continue

            click_pt = None

            # === Level 0 ===
            print(f"  [replay] step {i+1}/{len(steps)}: "
                  f"'{expected_text[:30]}' L0 template match...")
            pt, score = _template_match(img_bgr, tmpl_bgr, roi)
            if pt is not None:
                if _verify_ocr_text(img_bgr, pt, expected_text):
                    click_pt = pt
                    level0_count += 1
                    print(f"  [replay] L0 matched: score={score:.2f} pt=({pt[0]},{pt[1]})")
                else:
                    print(f"  [replay] L0 score OK ({score:.2f}) but OCR mismatch")

            # === Level 1 ===
            if click_pt is None and np.any(emb_vec != 0):
                print(f"  [replay] L1 embedding search...")
                pt1, sim1 = _embedding_match(img_bgr, emb_vec, roi)
                if pt1 is not None:
                    if _verify_ocr_text(img_bgr, pt1, expected_text):
                        click_pt = pt1
                        level1_count += 1
                        print(f"  [replay] L1 matched: sim={sim1:.2f}")

            # === Level 2 ===
            if click_pt is None:
                print(f"  [replay] L2 falling back to K3 agent...")
                result = _agent_fallback(task, config, {
                    "name": step_name, "window_class": tmpl.get("window", {}).get("class", ""),
                    "ocr_text": expected_text,
                })
                level2_count += 1
                token_usage["total"] += result.get("tokens", {}).get("total", 0)
                if result.get("success"): success_count += 1
                tool_log.append(f"[L2] {step_name}: {result.get('summary', '')[:80]}")
                continue

            # Execute click
            import pyautogui
            pyautogui.click(click_pt[0], click_pt[1])
            time.sleep(0.4)

            # Verify
            img_after = np.array(sct.grab(monitor))[..., :3]
            if _verify_step_complete(img_after, img_bgr):
                success_count += 1
                tool_log.append(
                    f"[L0] {step_name}: '{expected_text[:30]}' at ({click_pt[0]},{click_pt[1]})")
            else:
                print(f"  [replay] step verification: no visual change")

    total_steps = len(steps)
    print(f"\n  [replay] summary: {success_count}/{total_steps} steps passed "
          f"(L0={level0_count} L1={level1_count} L2={level2_count})")

    # Trigger self-heal if any step needed L2 or failed
    if level2_count > 0 or success_count < total_steps:
        print(f"  [heal] {level2_count} L2 fallback(s), {total_steps - success_count} failure(s)")
        print(f"  [heal] analyzing replay issues with K3...")
        try:
            _self_heal(task, steps, tool_log, level2_count, level1_count, config)
        except Exception as e:
            print(f"  [heal] auto-fix failed: {e}")

    return {
        "success": success_count >= total_steps * 0.7,
        "summary": (f"Replay: {success_count}/{total_steps} steps "
                    f"(L0={level0_count} L1={level1_count} L2={level2_count})"),
        "steps": tool_log,
        "tokens": token_usage,
        "_tool_calls_log": tool_log,
    }


def _self_heal(task: str, steps: list[dict], tool_log: list[str],
               l2_count: int, l1_count: int, config: dict):
    """Agent reviews replay failures and rewrites the .cua script.

    Takes the macro steps, failure log, and current screenshot. Asks K3
    to generate an improved script with waits, branches, and fallbacks.
    Saves the improved .cua alongside the original macro.
    """
    from openai import OpenAI
    import mss, cv2

    api_key = config.get("moonshot_api_key", "") or os.environ.get("MOONSHOT_API_KEY", "")
    if not api_key:
        return
    model = config.get("model", "kimi-k3")
    base_url = config.get("base_url", "https://api.moonshot.cn/v1")
    client = OpenAI(api_key=api_key, base_url=base_url)

    # Capture current screen
    img = np.array(mss.MSS().grab(mss.MSS().monitors[1]))
    from cua.tools.screenshot import downsample_for_vlm, _np_to_png_b64
    scaled, _, _ = downsample_for_vlm(img, (0.5, 0.5), img.shape[1], img.shape[0])

    # Build step summary
    steps_text = ""
    for i, s in enumerate(steps, 1):
        text = s.get("ocr_text", "")[:50]
        tool = s.get("tool", "?")
        steps_text += f"  {i}. [{tool}] {text}\n"

    failure_text = "\n".join(t for t in tool_log if "L1" in t or "L2" in t or "failed" in t.lower())

    prompt = (
        f"Original task: {task}\n\n"
        f"Recorded steps:\n{steps_text}\n"
        f"Failures during replay:\n{failure_text}\n"
        f"L2 (K3 agent) fallbacks: {l2_count}, L1 (embedding) fallbacks: {l1_count}\n\n"
        f"You are an automation script optimizer. Look at the screenshot. "
        f"Diagnose why some steps failed and rewrite the script to be more robust.\n\n"
        f"Rules:\n"
        f"- Add wait_until before steps that may need the UI to settle\n"
        f"- Add if ocr / if see checks before clicking critical elements\n"
        f"- Add if kimi branches for multi-state UI (e.g. login popup vs main screen)\n"
        f"- Use variables for dynamic text ($target, $message)\n"
        f"- Keep the original step order, only add guards and retries\n"
        f"- Use return 2 when the situation is beyond what a script can handle\n\n"
        f"Output ONLY the complete .cua script. No explanations, no markdown fences."
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": (
                    "You are a CUA script optimizer. You analyze failed macro replay "
                    "logs and rewrite .cua scripts to handle edge cases. Output ONLY "
                    "the complete improved script — no explanations, no markdown."
                )},
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": _np_to_png_b64(scaled)}},
                    {"type": "text", "text": prompt},
                ]},
            ],
            max_tokens=2000,
        )
        improved = (resp.choices[0].message.content or "").strip()
        # Strip markdown fences if present
        if improved.startswith("```"):
            improved = improved.split("\n", 1)[1] if "\n" in improved else improved
            if improved.endswith("```"):
                improved = improved[:-3]
        improved = improved.strip()

        if len(improved) < 20:
            print(f"  [heal] K3 returned empty/bad response")
            return

        # Save improved script
        from cua.recorder import MACRO_DIR
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in task[:40])[:40]
        script_path = MACRO_DIR.parent / "scripts" / f"{safe_name}_improved.cua"
        script_path.parent.mkdir(parents=True, exist_ok=True)
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(improved)
        print(f"  [heal] improved script saved: {script_path}")
        print(f"  [heal] diff with: code --diff {safe_name}.cua {safe_name}_improved.cua")

    except Exception as e:
        print(f"  [heal] K3 analysis failed: {e}")

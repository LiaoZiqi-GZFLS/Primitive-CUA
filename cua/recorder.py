"""Template recorder for fast replay mode.

Records button templates during agent execution:
  - Window info (HWND, class, PID, title OCR)
  - Button ROI relative to top-level window
  - Cropped button image (contour detection + OCR bounding)
  - 64-bit dHash
  - Multilingual embedding vector (float16)
  - OCR text label

Usage: python cua/cli.py --record "task description"
"""
import json
import os
import time
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).parent / "data" / "templates"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Name cache for O(1) dedup
_existing_names: set[str] | None = None


def _refresh_name_cache():
    global _existing_names
    _existing_names = set()
    if not DATA_DIR.exists():
        return
    for p in DATA_DIR.rglob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            _existing_names.add(d.get("ocr_text", ""))
        except Exception:
            pass


def _get_name_cache() -> set[str]:
    global _existing_names
    if _existing_names is None:
        _refresh_name_cache()
    return _existing_names

# Cache of existing OCR text names — loaded once to avoid disk scan on every record
_existing_names: set[str] | None = None


def _refresh_name_cache():
    """Load all existing element names into memory for fast dedup."""
    global _existing_names
    _existing_names = set()
    if not DATA_DIR.exists():
        return
    for p in DATA_DIR.rglob("*.json"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            _existing_names.add(d.get("ocr_text", ""))
        except Exception:
            pass


def _get_name_cache() -> set[str]:
    global _existing_names
    if _existing_names is None:
        _refresh_name_cache()
    return _existing_names

# --- dHash (64-bit difference hash) ---


def _dhash(img: np.ndarray) -> int:
    """Compute 64-bit dHash of a grayscale image.

    Resize to 9x8, compare adjacent horizontal pixels, return 64-bit int.
    """
    import cv2
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    resized = cv2.resize(gray, (9, 8), interpolation=cv2.INTER_AREA)
    h = 0
    for y in range(8):
        row = resized[y]
        for x in range(8):
            if row[x] > row[x + 1]:
                h |= 1 << (y * 8 + x)
    return h


def _dhash_distance(a: int, b: int) -> int:
    """Hamming distance between two dHashes."""
    return (a ^ b).bit_count()


# --- Embedding (reuses multilingual MiniLM) ---

def _get_embed_fn():
    """Get shared embedding function (delegates to learning.py cache)."""
    from cua.learning import _get_embedding_function
    return _get_embedding_function()


def _embed_text(text: str) -> np.ndarray:
    """Embed text and return float16 vector."""
    if not text or not text.strip():
        return np.zeros(384, dtype=np.float16)
    try:
        ef = _get_embed_fn()
        vec = np.array(ef([text])[0], dtype=np.float16)
        if not vec.any():
            _embed_text._warned = getattr(_embed_text, "_warned", False)
            if not _embed_text._warned:
                print("  [embed] WARNING: zero vector returned — model may be unavailable")
                _embed_text._warned = True
        return vec
    except Exception as e:
        _embed_text._warned = getattr(_embed_text, "_warned", False)
        if not _embed_text._warned:
            print(f"  [embed] WARNING: {e} — embeddings will be zero")
            _embed_text._warned = True
        return np.zeros(384, dtype=np.float16)


# --- Window info ---


def _get_window_at_point(px: int, py: int) -> int | None:
    """Get the HWND of the window under the given screen coordinates.

    This finds the actual target window under the mouse, not the foreground
    window (which might be the terminal during manual recording).
    """
    try:
        import win32gui
        return win32gui.WindowFromPoint((px, py))
    except ImportError:
        import ctypes
        from ctypes import wintypes
        try:
            pt = wintypes.POINT(px, py)
            return ctypes.windll.user32.WindowFromPoint(pt)
        except Exception:
            return None


def _get_window_info(hwnd: int = None) -> dict:
    """Capture window metadata for a given HWND (or foreground if None).

    Uses win32gui if available, falls back to ctypes Windows API.
    """
    import ctypes
    from ctypes import wintypes

    info = {"hwnd": hwnd or 0, "title": "", "class": "", "pid": 0, "rect": [0, 0, 0, 0]}

    try:
        import win32gui; import win32process; _use_win32 = True
    except ImportError:
        _use_win32 = False

    if _use_win32:
        if hwnd is None:
            hwnd = win32gui.GetForegroundWindow(); info["hwnd"] = hwnd
        try: info["title"] = win32gui.GetWindowText(hwnd)
        except: pass
        try: info["class"] = win32gui.GetClassName(hwnd)
        except: pass
        try: r = win32gui.GetWindowRect(hwnd); info["rect"] = [r[0], r[1], r[2]-r[0], r[3]-r[1]]
        except: pass
        try: _, info["pid"] = win32process.GetWindowThreadProcessId(hwnd)
        except: pass
    else:
        user32 = ctypes.windll.user32
        if hwnd is None:
            hwnd = user32.GetForegroundWindow(); info["hwnd"] = hwnd
        buf = ctypes.create_unicode_buffer(256)
        try: user32.GetWindowTextW(hwnd, buf, 256); info["title"] = buf.value or ""
        except: pass
        try: user32.GetClassNameW(hwnd, buf, 256); info["class"] = buf.value or ""
        except: pass
        try:
            r = wintypes.RECT(); user32.GetWindowRect(hwnd, ctypes.byref(r))
            info["rect"] = [r.left, r.top, r.right-r.left, r.bottom-r.top]
        except: pass
    return info


def _get_top_level_window(hwnd: int) -> int:
    """Walk up to find the top-level owner window."""
    try:
        import win32gui
        try:
            while True:
                owner = win32gui.GetWindow(hwnd, 4)
                if not owner: break
                hwnd = owner
        except Exception: pass
    except ImportError:
        import ctypes
        user32 = ctypes.windll.user32
        try:
            while True:
                owner = user32.GetWindow(hwnd, 4)
                if not owner: break
                hwnd = owner
        except Exception: pass
    return hwnd


# --- Button cropping ---


def _crop_button_around_click(
    screenshot: np.ndarray,
    click_px: tuple[int, int],
    max_expand: int = 160,
) -> np.ndarray | None:
    """Crop the button around a click point using contour detection + OCR.

    Args:
        screenshot: Full screenshot as BGR numpy array.
        click_px: (x, y) pixel coordinates of the click.
        max_expand: Max pixels to expand from click point for search region.

    Returns:
        Cropped button image (BGR), or None if detection fails.
    """
    import cv2

    h, w = screenshot.shape[:2]
    cx, cy = click_px

    # 1. Extract search region around click
    x1 = max(0, cx - max_expand)
    y1 = max(0, cy - max_expand)
    x2 = min(w, cx + max_expand)
    y2 = min(h, cy + max_expand)

    if x2 <= x1 or y2 <= y1:
        return None

    region = screenshot[y1:y2, x1:x2]
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)

    # 2. Edge detection + contour finding
    edges = cv2.Canny(gray, 30, 120)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # 3. Find contour closest to click point that looks like a button
    local_cx = cx - x1
    local_cy = cy - y1
    best_contour = None
    best_score = float("inf")

    for c in contours:
        bx, by, bw, bh = cv2.boundingRect(c)
        # Filter: reasonable button size
        if bw < 12 or bh < 8 or bw > max_expand * 2 or bh > max_expand * 2:
            continue
        if bw * bh < 100:  # too small
            continue
        # Must contain click point
        if not (bx <= local_cx <= bx + bw and by <= local_cy <= by + bh):
            continue
        # Prefer smaller, tighter boxes around the click point
        center_dist = abs((bx + bw / 2) - local_cx) + abs((by + bh / 2) - local_cy)
        score = bw * bh + center_dist * 2
        if score < best_score:
            best_score = score
            best_contour = c

    if best_contour is not None:
        bx, by, bw, bh = cv2.boundingRect(best_contour)
        # Expand slightly for padding
        pad = 4
        bx = max(0, bx - pad)
        by = max(0, by - pad)
        bw = min(region.shape[1] - bx, bw + pad * 2)
        bh = min(region.shape[0] - by, bh + pad * 2)
        return region[by:by + bh, bx:bx + bw]

    # 4. OCR fallback: use text bounding boxes around click
    try:
        from cua.tools.screenshot import _get_ocr_engine
        ocr = _get_ocr_engine()
        results, _ = ocr(region)
        if results:
            best_box = None
            best_dist = float("inf")
            for r in results:
                bbox = r[0]  # [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
                xs = [p[0] for p in bbox]
                ys = [p[1] for p in bbox]
                ox, oy = min(xs), min(ys)
                ow, oh = max(xs) - ox, max(ys) - oy
                if ow < 8 or oh < 5:
                    continue
                ocx, ocy = ox + ow / 2, oy + oh / 2
                d = ((ocx - local_cx) ** 2 + (ocy - local_cy) ** 2) ** 0.5
                if d < best_dist:
                    best_dist = d
                    best_box = (ox, oy, ow, oh)
            if best_box and best_dist < max_expand:
                ox, oy, ow, oh = best_box
                pad = 4
                ox = max(0, ox - pad)
                oy = max(0, oy - pad)
                ow = min(region.shape[1] - ox, ow + pad * 2)
                oh = min(region.shape[0] - oy, oh + pad * 2)
                return region[oy:oy + oh, ox:ox + ow]
    except Exception:
        pass

    # 5. Last resort: fixed-size crop around click
    r = 40
    fx1 = max(0, local_cx - r)
    fy1 = max(0, local_cy - r)
    fx2 = min(region.shape[1], local_cx + r)
    fy2 = min(region.shape[0], local_cy + r)
    if fx2 > fx1 and fy2 > fy1:
        return region[fy1:fy2, fx1:fx2]

    return None


# --- Record template ---




def record_element(
    screenshot_bgr: np.ndarray,
    click_px: tuple[int, int],
    window_hwnd: int = None,
    label: str = "",
) -> dict | None:
    """Record a UI element — a visual widget (button, icon, clickable area).

    Elements are pure visual data: cropped image, position, OCR text, hash,
    and embedding. They do NOT store tool type or action args — those belong
    to the macro step that uses the element.
    """
    import cv2

    # 1. Window info — use the window under the click point, not foreground
    hwnd_at_point = _get_window_at_point(click_px[0], click_px[1])
    win = _get_window_info(hwnd_at_point or window_hwnd)
    top_hwnd = _get_top_level_window(win["hwnd"])

    # 2. Crop button
    button_img = _crop_button_around_click(screenshot_bgr, click_px)
    if button_img is None:
        return None

    # 3. dHash
    dh = _dhash(button_img)

    # 4. ROI
    win_left, win_top = win["rect"][0], win["rect"][1]
    roi_x = click_px[0] - win_left
    roi_y = click_px[1] - win_top
    roi_w, roi_h = button_img.shape[1], button_img.shape[0]

    # 5. OCR or label
    name = label[:80] if label else ""
    if not name:
        try:
            from cua.tools.screenshot import _get_ocr_engine
            ocr = _get_ocr_engine()
            results, _ = ocr(button_img)
            if results:
                texts = [r[1] for r in results if r[2] and float(r[2]) > 0.6]
                name = " ".join(texts)[:100]
        except Exception:
            pass

    # 6. Auto-name: {app}-{position}-{function}
    import re
    app_hint = ""
    win_title = win.get("title", "")
    win_class = win.get("class", "")
    if win_class.lower() in ("progman", "workerw"):
        app_hint = "桌面"
    elif win_title:
        zh = re.findall(r'[一-鿿㐀-䶿]{2,8}', win_title)
        if zh: app_hint = zh[0][:8]
        else:
            en = re.findall(r'[a-zA-Z]{2,16}', win_title)
            if en and en[0].lower() not in ('the','and','for','not','doc','new','untitled','document'):
                app_hint = en[0][:12]

    # Position from ROI
    win_h = win["rect"][3] if win["rect"][3] > 0 else 1
    win_w = win["rect"][2] if win["rect"][2] > 0 else 1
    rel_y = roi_y / win_h
    rel_x = roi_x / win_w
    if rel_y < 0.12:      pos = "标题栏"
    elif rel_y < 0.22:    pos = "顶栏"
    elif rel_y < 0.35:    pos = "上部"
    elif rel_y < 0.65:    pos = "中部"
    elif rel_y < 0.80:    pos = "下部"
    elif rel_y < 0.92:    pos = "底部"
    else:                 pos = "底栏"
    if rel_x < 0.25 and rel_y < 0.22: pos = "左上"
    elif rel_x > 0.75 and rel_y < 0.22: pos = "右上"

    # Assemble name (skip assembly if label was explicitly given)
    if not label:
        if app_hint == "桌面" and not name:
            name = f"{app_hint}-{pos}-图标"[:80]
        elif app_hint and name and not name.startswith(app_hint):
            name = f"{app_hint}-{pos}-{name}"[:80]

    # 7. Dedup
    cache = _get_name_cache()
    if name in cache:
        name = f"{name}_{dh:04x}"[:80]
    cache.add(name)

    # 8. Embedding
    clean_text = name.split("_")[0] if "_" in name else name
    vec = _embed_text(clean_text[:60])

    # 9. Save
    safe_class = "".join(c if c.isalnum() or c in "-_" else "_" for c in win["class"])[:40]
    timestamp = int(time.time() * 1000)
    template_id = f"{safe_class}_{dh:016x}_{timestamp}"[:80]

    img_dir = DATA_DIR / safe_class
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / f"{template_id}.png"
    cv2.imwrite(str(img_path), button_img)

    meta = {
        "template_id": template_id, "timestamp": timestamp,
        "ocr_text": name,
        "window": {"hwnd": win["hwnd"], "top_hwnd": top_hwnd,
                   "class": win["class"], "title": win["title"][:200],
                   "pid": win["pid"], "rect": win["rect"]},
        "roi": {"x": roi_x, "y": roi_y, "w": roi_w, "h": roi_h},
        "click_px": list(click_px),
        "dhash": f"{dh:016x}",
        "embedding_384": vec.tobytes().hex(),
        "image_path": str(img_path),
    }
    meta_path = img_dir / f"{template_id}.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return meta


# Backward-compat alias
record_template = record_element


# --- Fast lookup for replay ---


def find_template(
    window_class: str,
    target_text: str = None,
    target_dhash: int = None,
    max_hamming: int = 10,
) -> list[dict]:
    """Find matching templates by window class, optionally filter by text or dHash."""
    img_dir = DATA_DIR / window_class
    if not img_dir.exists():
        return []

    results = []
    for meta_path in sorted(img_dir.glob("*.json"), reverse=True):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            continue

        if target_dhash is not None:
            stored_dh = int(meta["dhash"], 16)
            if _dhash_distance(stored_dh, target_dhash) > max_hamming:
                continue

        if target_text:
            stored_text = meta.get("ocr_text", "").lower()
            if target_text.lower() not in stored_text:
                continue

        results.append(meta)

    return results


# --- Macro (full task recording) ---

MACRO_DIR = DATA_DIR.parent / "macros"
MACRO_DIR.mkdir(parents=True, exist_ok=True)

_current_macro_steps: list[str] = []  # template IDs recorded in current session


def start_macro():
    """Begin a new macro recording session (called at task start)."""
    global _current_macro_steps
    _current_macro_steps = []


def add_macro_step(template_id: str):
    """Add a step to the current macro."""
    _current_macro_steps.append(template_id)


def save_macro(name: str, task: str, steps: list[dict]) -> str | None:
    """Save a complete task macro for one-click replay.

    Args:
        name: Macro name (kebab-case slug).
        task: Original task description.
        steps: List of template metadata dicts from this session.

    Returns:
        Macro file path, or None on failure.
    """
    if not steps:
        return None

    task_vec = _embed_text(task)

    macro = {
        "name": name,
        "task": task,
        "created": int(time.time() * 1000),
        "window_class": steps[0].get("window", {}).get("class", ""),
        "embedding_384": task_vec.tobytes().hex(),
        "steps": [
            {
                "template_id": s["template_id"],
                "tool": s["tool"],
                "args": s.get("args", {}),
                "ocr_text": s.get("ocr_text", ""),
                "roi": s.get("roi", {}),
                "image_path": s.get("image_path", ""),
                "embedding_384": s.get("embedding_384", ""),
                "dhash": s.get("dhash", "0"),
                "window": s.get("window", {}),
            }
            for s in steps
        ],
    }

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:60]
    macro_path = MACRO_DIR / f"{safe_name}.json"
    with open(macro_path, "w", encoding="utf-8") as f:
        json.dump(macro, f, ensure_ascii=False, indent=2)
    # Auto-generate .cua script alongside the macro
    _export_script(macro, safe_name)

    # Optionally improve the auto-generated script with K3
    if name and task:
        try:
            _improve_script(macro, safe_name, task)
        except Exception:
            pass  # Best-effort

    print(f"  [macro] saved: {safe_name} ({len(steps)} steps)")
    return str(macro_path)


def _improve_script(macro: dict, safe_name: str, task: str):
    """Ask K3 to review the recorded steps and add guards to the auto-generated script.

    Called after macro save during --record mode. The LLM has full context
    of the task it just executed and can add wait_until, if-checks, etc.
    """
    from openai import OpenAI
    import os as _os

    # Build step list for the prompt
    steps_text = ""
    for i, s in enumerate(macro.get("steps", []), 1):
        tool = s["tool"]
        text = s.get("ocr_text", "")[:60]
        steps_text += f"  {i}. [{tool}] {text}\n"

    api_key = _os.environ.get("MOONSHOT_API_KEY", "")
    if not api_key:
        try:
            from cua.config import load_config
            api_key = load_config().get("moonshot_api_key", "")
        except Exception:
            pass
    if not api_key:
        return

    model = "kimi-k3"
    base_url = "https://api.moonshot.cn/v1"
    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
    except Exception:
        return

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": (
                    "You improve desktop automation scripts. Given a recorded task trace, "
                    "add robustness guards. Output ONLY the complete improved .cua script."
                )},
                {"role": "user", "content": (
                    f"Task: {task}\n\nRecorded steps:\n{steps_text}\n\n"
                    f"Improve this script by adding:\n"
                    f"- wait_until see before clicking elements that may need loading time\n"
                    f"- wait after launch actions (apps take time to open)\n"
                    f"- if kimi checks for UI states that could vary (popups, login screens)\n"
                    f"- if ocr checks to confirm key text appears before clicking it\n"
                    f"- return 2 when something is unpredictable\n"
                    f"- set variables for any text values that might change\n\n"
                    f"Keep the original step order. Just add guards and retry logic.\n"
                    f"Output ONLY the .cua script — no markdown, no explanations."
                )},
            ],
            max_tokens=1500,
        )
        improved = (resp.choices[0].message.content or "").strip()
        if improved.startswith("```"):
            improved = improved.split("\n", 1)[1] if "\n" in improved else improved
            if improved.endswith("```"):
                improved = improved[:-3]
        improved = improved.strip()

        if len(improved) < 30:
            return

        # Overwrite the auto-generated script with the improved version
        SCRIPT_DIR = MACRO_DIR.parent / "scripts"
        SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
        script_path = SCRIPT_DIR / f"{safe_name}.cua"
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(improved)
        print(f"  [macro] K3-improved script: {script_path}")
    except Exception:
        pass  # Best-effort, don't block macro save


def _export_script(macro: dict, safe_name: str):
    """Auto-generate a .cua script from a macro JSON."""
    SCRIPT_DIR = MACRO_DIR.parent / "scripts"
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    script_path = SCRIPT_DIR / f"{safe_name}.cua"

    lines = [f"# Auto-generated from macro: {macro['name']}"]
    lines.append(f"# Task: {macro.get('task', '')}")
    lines.append("")
    lines.append(f"print Starting: {macro['name']}")
    lines.append("")

    for i, s in enumerate(macro.get("steps", [])):
        tool = s["tool"]
        text = s.get("ocr_text", "")
        args = s.get("args", {})

        if tool == "click":
            target = text or "target"
            lines.append(f"click {target}")
        elif tool == "uia_click":
            lines.append(f"uia_click {args.get('name', text)}")
        elif tool == "web_click":
            lines.append(f"web_click {args.get('text', text)}")
        elif tool == "paste_text":
            lines.append(f"type {args.get('text', text)}")
        elif tool == "type_keys":
            lines.append(f"keys {args.get('keys', '')}")
        elif tool == "launch_app":
            lines.append(f"launch {args.get('name', text)}")
        elif tool == "wait":
            lines.append(f"wait {args.get('seconds', 1)}")
        elif tool == "scroll":
            lines.append(f"scroll {args.get('direction', 'down')} {args.get('amount', 3)}")
        elif tool == "web_navigate":
            lines.append(f"navigate {args.get('url', '')}")
        elif tool == "drag":
            lines.append(f"drag {args.get('from_x',0)} {args.get('from_y',0)} "
                        f"{args.get('to_x',0)} {args.get('to_y',0)}")
        lines.append("")

    lines.append("return 0 Macro completed")
    lines.append("")

    with open(script_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def macro_to_script(macro_name: str) -> str | None:
    """Convert an existing macro to a .cua script. Returns script path."""
    macro = load_macro(macro_name)
    if not macro:
        return None
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in macro_name)[:60]
    _export_script(macro, safe_name)
    script_path = MACRO_DIR.parent / "scripts" / f"{safe_name}.cua"
    print(f"  [macro] script exported: {script_path}")
    return str(script_path) if script_path.exists() else None


def load_macro(query: str) -> dict | None:
    """Load the best-matching macro by embedding similarity.

    Embedding the query text against all stored macro task embeddings
    ensures semantic matching — '微信发消息' matches '打开微信搜索...'
    even when the strings are different.
    """
    candidates = sorted(MACRO_DIR.glob("*.json"))
    if not candidates:
        return None

    # Single candidate: return directly
    if len(candidates) == 1:
        try:
            with open(candidates[0], "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    # Embed query and compute cosine similarity against all macros
    query_vec = _embed_text(query[:200])
    scored = []
    for p in candidates:
        try:
            with open(p, "r", encoding="utf-8") as f:
                macro = json.load(f)
        except Exception:
            continue
        emb_hex = macro.get("embedding_384", "")
        if emb_hex and len(emb_hex) >= 32:
            try:
                emb_bytes = bytes.fromhex(emb_hex.ljust(768, "0")[:768])
                macro_vec = np.frombuffer(emb_bytes, dtype=np.float16)
                if len(macro_vec) < 384:
                    macro_vec = np.pad(macro_vec, (0, 384 - len(macro_vec)))
            except Exception:
                macro_vec = np.zeros(384, dtype=np.float16)
        else:
            macro_vec = np.zeros(384, dtype=np.float16)

        sim = float(np.dot(query_vec, macro_vec) /
                    (np.linalg.norm(query_vec) * np.linalg.norm(macro_vec) + 1e-8))
        scored.append((sim, macro))

    scored.sort(key=lambda x: -x[0])
    best_sim, best_macro = scored[0]

    if best_sim < 0.15:
        return None  # No relevant match

    print(f"  [macro] matched: '{best_macro['name']}' (sim={best_sim:.3f})")
    return best_macro


def list_macros() -> list[dict]:
    """List all saved macros."""
    results = []
    if not MACRO_DIR.exists():
        return results
    for p in sorted(MACRO_DIR.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                results.append(json.load(f))
        except Exception:
            pass
    return results


def list_templates() -> list[dict]:
    """List all recorded templates."""
    results = []
    if not DATA_DIR.exists():
        return results
    for meta_path in sorted(DATA_DIR.rglob("*.json")):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                results.append(json.load(f))
        except Exception:
            pass
    return results

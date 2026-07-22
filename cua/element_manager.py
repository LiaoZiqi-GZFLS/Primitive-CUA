"""UI Element Manager — manage buttons, inputs, and other UI elements.

Each element is a re-usable, named UI widget with:
  name        — human-readable name (e.g. "wechat_search_button")
  image       — cropped PNG template
  dHash       — 64-bit perceptual hash
  ocr_text    — OCR-extracted label text
  embedding   — MiniLM-384 text embedding of the label
  roi         — (x, y, w, h) relative to window
  window      — window class, title, PID

Elements are stored alongside auto-recorded templates in:
  cua/data/templates/

Usage:
  python cua/element_manager.py list                    # List all elements
  python cua/element_manager.py show <name>             # Show element details
  python cua/element_manager.py add <name>              # Add element (mouse position)
  python cua/element_manager.py edit <name>             # Re-capture element
  python cua/element_manager.py rename <name>           # Rename element label
  python cua/element_manager.py delete <name>           # Delete element
  python cua/element_manager.py preview [name]          # Open element image (name optional)
  python cua/element_manager.py test <name>             # Test match element on screen
  python cua/element_manager.py search <text>           # Search elements by OCR text
  python cua/element_manager.py export                  # Export all elements as JSON
  python cua/element_manager.py import <file>           # Import elements from JSON
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).parent / "data" / "templates"


def _load_all() -> list[dict]:
    """Load all element metadata from templates directory."""
    results = []
    if not DATA_DIR.exists():
        return results
    for p in sorted(DATA_DIR.rglob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            d["_file"] = str(p)
            results.append(d)
        except Exception:
            pass
    return results


def _find_by_name(name: str) -> dict | None:
    """Find an element by name (fuzzy match)."""
    all_el = _load_all()
    # Exact match first
    for el in all_el:
        if el.get("ocr_text", "") == name or el.get("template_id", "") == name:
            return el
    # OCR text contains name
    for el in all_el:
        if name.lower() in el.get("ocr_text", "").lower():
            return el
    # Template ID contains name
    for el in all_el:
        if name.lower() in el.get("template_id", "").lower():
            return el
    return None


def cmd_list():
    elements = _load_all()
    if not elements:
        print("No elements found.")
        return
    print(f"{'OCR Text / ID':<45s} {'Class':<25s} {'ROI':<20s} Img")
    print("-" * 100)
    for e in elements[-30:]:  # Show last 30
        text = e.get("ocr_text", e.get("template_id", "?"))[:43]
        cls = e.get("window", {}).get("class", "?")[:23]
        roi = e.get("roi", {})
        r = f"({roi.get('x',0)},{roi.get('y',0)} {roi.get('w',0)}x{roi.get('h',0)})"
        img = "✓" if e.get("image_path") and os.path.exists(e["image_path"]) else "✗"
        print(f"{text:<45s} {cls:<25s} {r:<20s} {img}")


def cmd_show(name: str):
    el = _find_by_name(name)
    if not el:
        print(f"Element not found: {name}")
        return
    print(f"Template ID:  {el.get('template_id', '?')}")
    print(f"OCR Text:     {el.get('ocr_text', '(none)')}")
    print(f"Tool:         {el.get('tool', '?')}")
    print(f"Args:         {json.dumps(el.get('args', {}), ensure_ascii=False)}")
    print(f"dHash:        {el.get('dhash', '?')}")
    roi = el.get("roi", {})
    print(f"ROI:          ({roi.get('x',0)}, {roi.get('y',0)} "
          f"{roi.get('w',0)}x{roi.get('h',0)})")
    win = el.get("window", {})
    print(f"Window Class: {win.get('class', '?')}")
    print(f"Window Title: {win.get('title', '?')[:60]}")
    img_path = el.get("image_path", "")
    print(f"Image:        {img_path} {'✓' if img_path and os.path.exists(img_path) else '✗'}")


def _unique_name(name: str) -> str:
    """Ensure unique element name. If collision, append short dHash suffix."""
    existing = [e.get("ocr_text", "") for e in _load_all()]
    if name not in existing:
        return name
    # Append last 4 chars of a hash-based suffix
    import hashlib
    suffix = hashlib.md5(f"{name}{time.time()}".encode()).hexdigest()[:4]
    return f"{name}_{suffix}"


def cmd_add(name: str):
    """Add a new element by positioning mouse and capturing."""
    import cv2
    import mss
    import pyautogui
    from cua.recorder import record_element, _get_window_info

    name = _unique_name(name)
    print(f"Adding element: {name}")

    # Countdown then capture (elements are pure visual widgets)
    print("  Move mouse to target...")
    for i in range(5, 0, -1):
        print(f"  {i}...")
        time.sleep(1)
    print("  Capturing!")

    mx, my = pyautogui.position()

    with mss.MSS() as sct:
        img = np.array(sct.grab(sct.monitors[1]))[..., :3]

    meta = record_element(
        screenshot_bgr=img, click_px=(mx, my),
        label=name,
    )
    if meta:
        print(f"  ✓ Element saved: {meta['template_id']}")
        print(f"    OCR: '{meta['ocr_text'][:40]}'")
        print(f"    dHash: {meta['dhash']}")
    else:
        print(f"  ⚠ Could not extract visual button — text-only element")
        # Save manually
        import cv2
        from cua.recorder import _get_window_info, _embed_text, _dhash, DATA_DIR
        win = _get_window_info()
        safe_class = "".join(c if c.isalnum() or c in "-_" else "_" for c in win["class"])[:40]
        ts = int(time.time() * 1000)
        tid = f"manual_{tool}_{ts}"
        img_dir = DATA_DIR / safe_class
        img_dir.mkdir(parents=True, exist_ok=True)
        img_path = img_dir / f"{tid}.png"
        cv2.imwrite(str(img_path), np.zeros((30, 100, 3), dtype=np.uint8))
        meta = {
            "template_id": tid, "timestamp": ts, "tool": tool, "args": args,
            "ocr_text": args.get("text", args.get("name", args.get("keys", ""))),
            "roi": {"x": mx - win["rect"][0], "y": my - win["rect"][1],
                    "w": 100, "h": 30},
            "dhash": "0", "embedding_384": _embed_text(name).tobytes().hex(),
            "image_path": str(img_path),
            "click": {"px": [mx, my], "normalized": [nx, ny]},
            "window": win,
        }
        meta_path = img_dir / f"{tid}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"  ✓ Text element saved: {tid}")


def cmd_preview(name: str = None):
    """Open element template images for visual inspection."""
    import os as _os

    if name:
        el = _find_by_name(name)
        if not el:
            print(f"Element not found: {name}")
            return
        img_path = el.get("image_path", "")
        if img_path and _os.path.exists(img_path):
            print(f"Opening: {img_path}")
            _os.startfile(img_path)
        else:
            print(f"No image for: {name} (text-only element)")
    else:
        # Preview all elements with images
        elements = _load_all()
        with_img = []
        for e in elements:
            p = e.get("image_path", "")
            if p and _os.path.exists(p):
                sz = _os.path.getsize(p)
                with_img.append((e, sz))
        if not with_img:
            print("No elements with images found.")
            return
        print(f"{'OCR Text':<45s} {'Size':>8s} {'Path'}")
        print("-" * 100)
        for e, sz in with_img:
            text = e.get("ocr_text", e.get("template_id", "?"))[:43]
            path = e.get("image_path", "")[:50]
            print(f"{text:<45s} {sz:>7d}B {path}")


def cmd_edit(name: str):
    """Re-capture an existing element (update its template)."""
    el = _find_by_name(name)
    if not el:
        print(f"Element not found: {name}")
        return
    # Delete old files
    old_img = el.get("image_path", "")
    old_json = el.get("_file", "")
    for p in [old_img, old_json]:
        if p and os.path.exists(p):
            try: os.remove(p)
            except: pass
    # Re-add
    cmd_add(name)


def cmd_rename(name: str):
    """Rename an element's OCR text (used as the click target)."""
    el = _find_by_name(name)
    if not el:
        print(f"Element not found: {name}")
        return
    old_name = el.get("ocr_text", el.get("template_id", "?"))
    new_name = input(f"New name (current: '{old_name[:50]}'): ").strip()
    if not new_name:
        return
    meta_path = el.get("_file", "")
    if meta_path and os.path.exists(meta_path):
        el["ocr_text"] = new_name
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(el, f, ensure_ascii=False, indent=2)
        print(f"  Renamed: '{old_name[:40]}' → '{new_name}'")


def cmd_delete(name: str):
    el = _find_by_name(name)
    if not el:
        print(f"Element not found: {name}")
        return
    for p in [el.get("image_path", ""), el.get("_file", "")]:
        if p and os.path.exists(p):
            os.remove(p)
            print(f"  Deleted: {p}")


def cmd_test(name: str):
    """Test whether an element can be matched on the current screen."""
    el = _find_by_name(name)
    if not el:
        print(f"Element not found: {name}")
        return

    import cv2, mss
    from cua.fast_replay import _template_match, _verify_ocr_text

    img_path = el.get("image_path", "")
    if not img_path or not os.path.exists(img_path):
        print("No template image available — cannot test.")
        return

    tmpl_bgr = cv2.imread(img_path)
    if tmpl_bgr is None:
        print("Corrupt template image.")
        return

    # Try window binding first for accurate ROI
    roi = el.get("roi", {})
    win_cls = el.get("window", {}).get("class", "")
    click_px = el.get("click_px", [0, 0])
    cx, cy = click_px[0], click_px[1]
    roi_w = max(roi.get("w", 20), 20)
    roi_h = max(roi.get("h", 10), 10)
    win_offset = [0, 0]
    try:
        import win32gui
        def _find(hwnd, _):
            if not win32gui.IsWindowVisible(hwnd): return
            try:
                if win_cls.lower() in win32gui.GetClassName(hwnd).lower():
                    r = win32gui.GetWindowRect(hwnd)
                    win_offset[0], win_offset[1] = r[0], r[1]
            except: pass
        win32gui.EnumWindows(_find, None)
    except: pass
    win_ox, win_oy = win_offset[0], win_offset[1]

    with mss.MSS() as sct:
        monitor = sct.monitors[1]
        if win_ox > -30000 and win_oy > -30000:
            for mon in sct.monitors[1:]:
                if (mon["left"] <= win_ox < mon["left"] + mon["width"] and
                    mon["top"] <= win_oy < mon["top"] + mon["height"]):
                    monitor = mon; break
        else:
            # Window not found — fall back to click point
            for mon in sct.monitors[1:]:
                if (mon["left"] <= cx < mon["left"] + mon["width"] and
                    mon["top"] <= cy < mon["top"] + mon["height"]):
                    monitor = mon; break
            win_ox, win_oy = cx - roi_w, cy - roi_h
        mon_left, mon_top = monitor["left"], monitor["top"]
        img = np.array(sct.grab(monitor))[..., :3]

    # ROI in monitor-local coordinates
    roi_rect = (roi.get("x", 0) + win_ox - mon_left,
                roi.get("y", 0) + win_oy - mon_top,
                max(roi_w * 2, 80), max(roi_h * 2, 40))
    pt, score = _template_match(img, tmpl_bgr, roi_rect)

    print(f"Element:   {el.get('ocr_text', name)}")
    print(f"Window at: ({win_ox}, {win_oy}) {'OK' if win_ox > -30000 else '(fallback to click)'}")
    print(f"ROI:       ({roi_rect[0]}, {roi_rect[1]} {roi_rect[2]}x{roi_rect[3]})")
    if pt is not None:
        print(f"Match:   score={score:.3f} position=({pt[0]},{pt[1]})")
        expected = el.get("ocr_text", "")
        if expected and score < 0.85:
            ok = _verify_ocr_text(img, pt, expected)
            print(f"OCR:     {'matches' if ok else 'mismatch'} '{expected[:40]}'")
        else:
            print(f"OCR:     {'skipped (high confidence)' if score >= 0.85 else 'skipped (no text)'}")
    else:
        print(f"Match:   best_score={score:.3f} (threshold=0.70)")


def cmd_search(text: str):
    elements = _load_all()
    found = [e for e in elements
             if text.lower() in e.get("ocr_text", "").lower()
             or text.lower() in e.get("template_id", "").lower()]
    if not found:
        print(f"No elements matching: {text}")
        return
    for e in found:
        print(f"  {e.get('ocr_text', e.get('template_id','?'))[:50]}")


def cmd_export():
    elements = _load_all()
    out_path = DATA_DIR.parent / "elements_export.json"
    export = []
    for e in elements:
        export.append({
            "name": e.get("ocr_text", e.get("template_id", "")),
            "tool": e.get("tool", "click"),
            "args": e.get("args", {}),
            "roi": e.get("roi", {}),
            "dhash": e.get("dhash", ""),
            "window_class": e.get("window", {}).get("class", ""),
        })
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)
    print(f"Exported {len(export)} elements → {out_path}")


def cmd_import(path: str):
    import shutil
    import cv2
    from cua.recorder import _embed_text, _dhash, _get_window_info, DATA_DIR

    with open(path, "r", encoding="utf-8") as f:
        items = json.load(f)
    if not isinstance(items, list):
        items = [items]

    win = _get_window_info()
    safe_class = "".join(c if c.isalnum() or c in "-_" else "_" for c in win["class"])[:40]
    img_dir = DATA_DIR / safe_class
    img_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for item in items:
        ts = int(time.time() * 1000) + count
        tid = f"import_{item.get('name','unknown')}_{ts}"[:80]
        img_path = img_dir / f"{tid}.png"
        cv2.imwrite(str(img_path), np.zeros((30, 100, 3), dtype=np.uint8))

        meta = {
            "template_id": tid, "timestamp": ts,
            "tool": item.get("tool", "click"),
            "args": item.get("args", {}),
            "ocr_text": item.get("name", ""),
            "roi": item.get("roi", {"x": 0, "y": 0, "w": 100, "h": 30}),
            "dhash": item.get("dhash", "0"),
            "embedding_384": _embed_text(item.get("name", "")).tobytes().hex(),
            "image_path": str(img_path),
            "click": {"px": [0, 0], "normalized": [0.5, 0.5]},
            "window": win,
        }
        meta_path = img_dir / f"{tid}.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        count += 1
    print(f"Imported {count} elements.")


def main():
    if len(sys.argv) < 2:
        print(__doc__); return

    cmd = sys.argv[1].lower()
    arg = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

    commands = {
        "list": lambda: cmd_list(),
        "show": lambda: cmd_show(arg) if arg else print("Usage: ... show <name>"),
        "add": lambda: cmd_add(arg) if arg else print("Usage: ... add <name>"),
        "preview": lambda: cmd_preview(arg) if arg else cmd_preview(),
        "edit": lambda: cmd_edit(arg) if arg else print("Usage: ... edit <name>"),
        "delete": lambda: cmd_delete(arg) if arg else print("Usage: ... delete <name>"),
        "rename": lambda: cmd_rename(arg) if arg else print("Usage: ... rename <name>"),
        "test": lambda: cmd_test(arg) if arg else print("Usage: ... test <name>"),
        "search": lambda: cmd_search(arg) if arg else print("Usage: ... search <text>"),
        "export": cmd_export,
        "import": lambda: cmd_import(arg) if arg else print("Usage: ... import <file>"),
    }

    fn = commands.get(cmd)
    if fn:
        fn()
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()

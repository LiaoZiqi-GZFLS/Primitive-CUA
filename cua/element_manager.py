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
  python cua/element_manager.py reimage <name>          # Replace element image
  python cua/element_manager.py refresh <name>          # Re-scan PNG to update ROI/dHash
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
    for p in sorted(DATA_DIR.rglob("*.json"),
                 key=lambda p: (p.parent.name, -p.stat().st_mtime)):
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
    print(f"{'OCR Text':<30s} {'File':<35s} {'ROI':<15s} Img")
    print("-" * 100)
    for e in elements[-30:]:
        text = e.get("ocr_text", e.get("template_id", "?"))[:28]
        fname = Path(e.get("_file", "")).stem[:33]
        roi = e.get("roi", {})
        r = f"({roi.get('x',0)},{roi.get('y',0)} {roi.get('w',0)}x{roi.get('h',0)})"
        img = "✓" if e.get("image_path") and os.path.exists(e["image_path"]) else "✗"
        print(f"{text:<30s} {fname:<35s} {r:<15s} {img}")


def cmd_show(name: str):
    el = _find_by_name(name)
    if not el:
        print(f"Element not found: {name}")
        return
    print(f"Template ID:  {el.get('template_id', '?')}")
    print(f"OCR Text:     {el.get('ocr_text', '(none)')}")
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


def _capture_box(box_w: int = 200, box_h: int = 80) -> tuple | None:
    """Show fullscreen overlay with a resizable selection box.

    Initial box is auto-detected from contour around mouse, falling back
    to box_w x box_h at cursor. Drag edges/corners to resize.
    Drag inside to move. Enter to confirm, ESC to cancel.
    """
    import tkinter as tk
    import cv2, mss

    with mss.MSS() as sct:
        full = np.array(sct.grab(sct.monitors[1]))[..., :3]
    h, w = full.shape[:2]
    import PIL.Image, PIL.ImageTk
    pil_img = PIL.Image.fromarray(full[..., ::-1])

    # Auto-detect button contour around mouse
    import pyautogui
    mx, my = pyautogui.position()
    bx, by = mx - box_w // 2, my - box_h // 2
    bw, bh = box_w, box_h

    # Try contour detection for a tighter initial box
    try:
        margin = 120
        x1 = max(0, mx - margin); y1 = max(0, my - margin)
        x2 = min(w, mx + margin); y2 = min(h, my + margin)
        region = full[y1:y2, x1:x2]
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 30, 120)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        local_mx, local_my = mx - x1, my - y1
        best = None
        for c in contours:
            cbx, cby, cbw, cbh = cv2.boundingRect(c)
            if cbw < 8 or cbh < 6 or cbw * cbh < 60: continue
            if cbx <= local_mx <= cbx + cbw and cby <= local_my <= cby + cbh:
                if best is None or cbw * cbh < best[2] * best[3]:
                    best = (cbx + x1, cby + y1, cbw, cbh)
        if best:
            bx, by, bw, bh = best
    except Exception:
        pass

    root = tk.Tk()
    root.attributes("-fullscreen", True, "-topmost", True)
    root.attributes("-alpha", 0.6)
    canvas = tk.Canvas(root, width=w, height=h, highlightthickness=0)
    canvas.pack()
    photo = PIL.ImageTk.PhotoImage(pil_img)
    canvas.create_image(0, 0, anchor="nw", image=photo)
    result = None
    drag_mode = [None]
    last = [0, 0]

    def draw():
        canvas.delete("box"); x2, y2 = bx + bw, by + bh
        canvas.create_rectangle(bx, by, x2, y2, outline="#00ff00", width=2, tags="box")
        r = 6
        for px, py in [(x2,y2),(bx,y2),(x2,by),(bx,by),
                       ((bx+x2)//2,by),((bx+x2)//2,y2),(bx,(by+y2)//2),(x2,(by+y2)//2)]:
            canvas.create_oval(px-r,py-r,px+r,py+r, fill="#00ff00", outline="", tags="box")

    draw()

    def _mode(x, y):
        n = 15
        if abs(x-bx)<n and abs(y-by)<n: return "nw"
        if abs(x-bx-bw)<n and abs(y-by)<n: return "ne"
        if abs(x-bx)<n and abs(y-by-bh)<n: return "sw"
        if abs(x-bx-bw)<n and abs(y-by-bh)<n: return "se"
        if abs(y-by)<n: return "n"
        if abs(y-by-bh)<n: return "s"
        if abs(x-bx)<n: return "w"
        if abs(x-bx-bw)<n: return "e"
        if bx <= x <= bx+bw and by <= y <= by+bh: return "move"
        return None

    def on_down(e):
        nonlocal drag_mode; last[0],last[1]=e.x,e.y; drag_mode[0]=_mode(e.x,e.y)

    def on_drag(e):
        nonlocal bx,by,bw,bh
        dx,dy = e.x-last[0], e.y-last[1]; m = drag_mode[0]
        if m=="move": bx+=dx; by+=dy
        elif m=="nw": bx+=dx; by+=dy; bw-=dx; bh-=dy
        elif m=="ne": by+=dy; bw+=dx; bh-=dy
        elif m=="sw": bx+=dx; bw-=dx; bh+=dy
        elif m=="se": bw+=dx; bh+=dy
        elif m=="n": by+=dy; bh-=dy
        elif m=="s": bh+=dy
        elif m=="w": bx+=dx; bw-=dx
        elif m=="e": bw+=dx
        if bw < 10: bw = 10
        if bh < 10: bh = 10
        draw(); last[0],last[1]=e.x,e.y

    def on_up(e): drag_mode[0]=None

    def on_enter(e):
        nonlocal result
        if bw>4 and bh>4:
            cx,cy=bx+bw//2,by+bh//2
            result=(full[by:by+bh,bx:bx+bw].copy(),cx,cy,bw,bh)
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_down)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_up)
    root.bind("<Return>", on_enter)
    root.bind("<Escape>", lambda e: root.destroy())
    canvas.create_text(w//2, h-30, text="Drag edges to resize | Enter confirm | ESC cancel",
                       fill="white", font=("Arial",14))
    root.mainloop()
    return result


def cmd_add(name: str, box_w: int = 200, box_h: int = 80):
    """Add a new element by dragging a selection box on screen.

    Optional: specify box size (e.g. 'add name 300 50' for a wide box).
    """
    import cv2
    from cua.recorder import (
        _dhash, _embed_text, _get_window_info, _get_window_at_point,
        _get_top_level_window, _get_name_cache, DATA_DIR,
    )
    import json, re

    name = _unique_name(name)
    print(f"Adding element: {name} (box {box_w}x{box_h})")
    for i in range(3, 0, -1):
        print(f"  {i}...")
        time.sleep(1)
    print("  Select region now!")
    result = _capture_box(box_w, box_h)
    if result is None:
        print("  Cancelled.")
        return

    crop_bgr, cx, cy, bw, bh = result
    print(f"  Captured: ({cx}, {cy}) {bw}x{bh}")

    hwnd = _get_window_at_point(cx, cy)
    win = _get_window_info(hwnd)
    top_hwnd = _get_top_level_window(win["hwnd"])
    dh = _dhash(crop_bgr)

    win_left, win_top = win["rect"][0], win["rect"][1]
    roi_x, roi_y = cx - win_left, cy - win_top

    app_hint = ""
    win_title = win.get("title", "")
    win_class = win.get("class", "")
    if win_class.lower() in ("progman", "workerw"):
        app_hint = "桌面"
    elif win_title:
        zh = re.findall(r'[一-鿿㐀-䶿]{2,8}', win_title)
        if zh: app_hint = zh[0][:8]

    label = name  # Manual add: use exact user-provided name
    cache = _get_name_cache()
    if label in cache:
        label = f"{label}_{dh:04x}"[:80]
    cache.add(label)
    vec = _embed_text(name)

    safe_class = "".join(c if c.isalnum() or c in "-_" else "_" for c in win["class"])[:40]
    ts = int(time.time() * 1000)
    tid = f"{safe_class}_{dh:016x}_{ts}"[:80]
    img_dir = DATA_DIR / safe_class
    img_dir.mkdir(parents=True, exist_ok=True)
    img_path = img_dir / f"{tid}.png"
    cv2.imwrite(str(img_path), crop_bgr)

    meta = {
        "template_id": tid, "timestamp": ts, "ocr_text": label,
        "window": {"hwnd": win["hwnd"], "top_hwnd": top_hwnd,
                   "class": win["class"], "title": win["title"][:200],
                   "pid": win["pid"], "rect": win["rect"]},
        "roi": {"x": roi_x, "y": roi_y, "w": bw, "h": bh},
        "click_px": [cx, cy],
        "dhash": f"{dh:016x}",
        "embedding_384": vec.tobytes().hex(),
        "image_path": str(img_path),
    }
    meta_path = img_dir / f"{tid}.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"  Saved: {label}")
    print(f"  ROI: ({roi_x}, {roi_y} {bw}x{bh})")


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


def cmd_refresh(name: str):
    """Re-read the PNG and update ROI, dHash from the actual image file."""
    el = _find_by_name(name)
    if not el:
        print(f"Element not found: {name}")
        return
    img_path = el.get("image_path", "")
    if not img_path or not os.path.exists(img_path):
        print("No image file — nothing to refresh.")
        return

    import cv2
    from cua.recorder import _dhash
    img = cv2.imread(img_path)
    if img is None:
        print("Cannot read image.")
        return

    h, w = img.shape[:2]
    dh = _dhash(img)

    el["roi"]["w"] = w
    el["roi"]["h"] = h
    el["dhash"] = f"{dh:016x}"

    meta_path = el.get("_file", "")
    if meta_path and os.path.exists(meta_path):
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(el, f, ensure_ascii=False, indent=2)
    print(f"  Refreshed: {w}x{h}  dhash={el['dhash']}")


def cmd_reimage(name: str):
    """Replace an element's template image with a custom PNG file."""
    el = _find_by_name(name)
    if not el:
        print(f"Element not found: {name}")
        return
    old_img = el.get("image_path", "")
    new_img = input(f"Path to new PNG (current: {old_img}): ").strip()
    if not new_img or not os.path.exists(new_img):
        print("File not found.")
        return

    import cv2, shutil
    img = cv2.imread(new_img)
    if img is None:
        print("Not a valid image file.")
        return

    # Copy to templates directory
    dest_dir = Path(old_img).parent if old_img else DATA_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    dest = dest_dir / f"custom_{ts}.png"
    cv2.imwrite(str(dest), img)

    # Recalculate dHash
    from cua.recorder import _dhash
    dh = _dhash(img)

    # Update metadata
    el["image_path"] = str(dest)
    el["dhash"] = f"{dh:016x}"
    el["roi"]["w"] = img.shape[1]
    el["roi"]["h"] = img.shape[0]

    meta_path = el.get("_file", "")
    if meta_path and os.path.exists(meta_path):
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(el, f, ensure_ascii=False, indent=2)
    print(f"  Image replaced: {old_img} → {dest}")
    print(f"  dHash updated: {el['dhash']}")
    print(f"  ROI updated: {img.shape[1]}x{img.shape[0]}")


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
            # Strip hash suffix for OCR comparison
            # Strip hash suffix and try function-name part
            clean = expected.split("_")[0] if "_" in expected else expected
            func = clean.rsplit("-", 1)[-1] if "-" in clean else clean
            ok = (_verify_ocr_text(img, pt, clean) or
                  _verify_ocr_text(img, pt, func) or
                  score >= 0.80)  # High score trumps OCR
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
        "add": lambda: (
            cmd_add(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
            if len(sys.argv) > 4 else
            cmd_add(sys.argv[2]) if len(sys.argv) > 2 else
            print("Usage: ... add <name> [w] [h]")
        ),
        "preview": lambda: cmd_preview(arg) if arg else cmd_preview(),
        "edit": lambda: cmd_edit(arg) if arg else print("Usage: ... edit <name>"),
        "delete": lambda: cmd_delete(arg) if arg else print("Usage: ... delete <name>"),
        "rename": lambda: cmd_rename(arg) if arg else print("Usage: ... rename <name>"),
        "reimage": lambda: cmd_reimage(arg) if arg else print("Usage: ... reimage <name>"),
        "refresh": lambda: cmd_refresh(arg) if arg else print("Usage: ... refresh <name>"),
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

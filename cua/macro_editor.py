"""Standalone macro management tool — record, view, play, delete macros.

Usage:
  python cua/macro_editor.py list                  List all macros
  python cua/macro_editor.py show <name>           Show macro details
  python cua/macro_editor.py play <name>           Replay a macro
  python cua/macro_editor.py delete <name>         Delete a macro
  python cua/macro_editor.py record <name> <task>  Manually record a macro
  python cua/macro_editor.py to-script <name>       Export macro as .cua script
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

from cua.recorder import (
    MACRO_DIR, DATA_DIR, list_macros, load_macro, save_macro,
    record_element, _get_window_info, _embed_text,
)


def cmd_list():
    """List all saved macros."""
    macros = list_macros()
    if not macros:
        print("No macros found.")
        return

    print(f"{'Name':<40s} {'Steps':<6s} {'Task'}")
    print("-" * 80)
    for m in macros:
        name = m["name"][:38]
        steps = len(m.get("steps", []))
        task = m.get("task", "")[:40]
        print(f"{name:<40s} {steps:<6d} {task}")


def cmd_show(name: str):
    """Show detailed steps of a macro."""
    macro = load_macro(name)
    if not macro:
        print(f"Macro not found: {name}")
        return

    print(f"Name:    {macro['name']}")
    print(f"Task:    {macro.get('task', '')}")
    print(f"Window:  {macro.get('window_class', '?')}")
    print(f"Created: {macro.get('created', 0)}")
    print(f"Steps:   {len(macro.get('steps', []))}")
    print()
    for i, s in enumerate(macro.get("steps", []), 1):
        tool = s.get("tool", "?")
        text = s.get("ocr_text", "")[:50]
        roi = s.get("roi", {})
        r = f"({roi.get('x',0)},{roi.get('y',0)} {roi.get('w',0)}x{roi.get('h',0)})"
        img = "✓" if s.get("image_path") and os.path.exists(s["image_path"]) else "✗"
        print(f"  {i:2d}. [{tool:<12s}] {text:<52s} roi={r:<20s} img={img}")


def cmd_play(name: str, step_mode: bool = False):
    """Replay a macro.

    Normal mode: fully automated replay.
    Step mode (--step): confirm each step before executing.
    """
    from cua.fast_replay import replay_macro, _execute_steps, _validate_macro
    from cua.config import load_config

    macro = load_macro(name)
    if not macro:
        print(f"Macro not found: {name}")
        return

    config = load_config()

    if not step_mode:
        # Full auto replay
        print(f"Replaying: {macro['name']} ({len(macro['steps'])} steps)")
        report = replay_macro(name, config)
    else:
        # Step-by-step interactive replay
        print(f"Macro: {macro['name']}")
        print(f"Task:  {macro.get('task', '')}")
        print(f"Steps: {len(macro['steps'])}")
        print()

        # Validate first
        approved, win_d = _validate_macro(
            macro.get("task", name), macro, config
        )
        if not approved:
            print("❌ Validation rejected. Continue anyway? [y/N]: ", end="")
            if input().strip().lower() != "y":
                return

        if win_d:
            import pyautogui
            pyautogui.hotkey("win", "d")
            print("Win+D cleared desktop.")
            import time
            time.sleep(0.5)

        # Bind window
        import win32gui
        window_cls = macro.get("window_class", "")
        window_hwnd = None

        def _enum(hwnd, _):
            nonlocal window_hwnd
            if not win32gui.IsWindowVisible(hwnd):
                return
            try:
                cls = win32gui.GetClassName(hwnd)
            except Exception:
                return
            if window_cls and window_cls.lower() in cls.lower():
                window_hwnd = hwnd

        win32gui.EnumWindows(_enum, None)

        if not window_hwnd:
            print(f"❌ Target window '{window_cls}' not found.")
            print("Open the app, then press Enter to retry: ", end="")
            input()
            win32gui.EnumWindows(_enum, None)
            if not window_hwnd:
                print("Still not found. Aborting.")
                return

        print(f"✓ Window found: {win32gui.GetWindowText(window_hwnd)}")

        # Step through each action
        for i, s in enumerate(macro["steps"], 1):
            tool = s["tool"]
            text = s.get("ocr_text", "")[:50]
            roi = s.get("roi", {})
            print(f"\n{'─'*50}")
            print(f"Step {i}/{len(macro['steps'])}")
            print(f"  Tool: {tool}")
            print(f"  Text: {text}")
            print(f"  ROI:  ({roi.get('x',0)},{roi.get('y',0)} "
                  f"{roi.get('w',0)}x{roi.get('h',0)})")

            choice = input("Execute? [Y=execute / s=skip / q=quit]: ").strip().lower()
            if choice == "q":
                print("Quit.")
                return
            if choice == "s":
                print("  ⏭ Skipped.")
                continue

            # Execute single step via _execute_steps
            result = _execute_steps(
                macro["task"], config, [s], window_hwnd
            )
            if result["success"]:
                print(f"  ✓ Done")
            else:
                print(f"  ✗ Failed: {result['summary']}")

        print(f"\n✓ Macro '{macro['name']}' completed.")

    # Print full report
    if not step_mode:
        print()
        if report["success"]:
            print("✓ Replay succeeded")
        else:
            print("✗ Replay failed")
        print(f"Summary: {report['summary']}")
        for s in report.get("steps", []):
            print(f"  {s}")


def cmd_delete(name: str):
    """Delete a macro."""
    macro = load_macro(name)
    if not macro:
        print(f"Macro not found: {name}")
        return

    # Find the file
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:60]
    path = MACRO_DIR / f"{safe_name}.json"
    if path.exists():
        path.unlink()
        print(f"Deleted: {path}")
    else:
        print(f"File not found: {path}")


def cmd_record(name: str, task: str):
    """Manually record a macro step by step.

    Position the mouse on each target element, then press Enter in the
    terminal to capture. Enter 'done' as tool name to finish.
    """
    import cv2
    import mss
    import pyautogui

    print(f"Recording macro: {name}")
    print(f"Task: {task}")
    print()
    print("Instructions:")
    print("  1. Move mouse to the target element")
    print("  2. Press Enter in this terminal to capture")
    print("  3. Enter tool type and parameters")
    print("  4. Type 'done' to finish, 'skip' to cancel")
    print()

    steps = []
    step_count = 0

    with mss.MSS() as sct:
        monitor = sct.monitors[1]

        while True:
            step_count += 1
            print(f"\n--- Step {step_count} ---")

            # Ask tool type FIRST, then capture — avoids delay between
            # mouse positioning and screenshot
            print("Tools: click / uia_click / web_click / paste_text / type_keys")
            print("       launch_app / wait / scroll / web_navigate / drag")
            tool = input("Tool [default=click]: ").strip()
            if not tool:
                tool = "click"
            if tool == "done":
                print("Finishing...")
                break
            if tool == "skip":
                step_count -= 1
                continue

            args = {}
            if tool == "paste_text":
                args["text"] = input("  Text: ").strip()
            elif tool == "type_keys":
                args["keys"] = input("  Keys (e.g. ctrl+c): ").strip()
            elif tool in ("launch_app",):
                args["name"] = input("  App name: ").strip()
            elif tool == "wait":
                try:
                    args["seconds"] = float(input("  Seconds: ").strip())
                except ValueError:
                    args["seconds"] = 1.0
            elif tool == "scroll":
                args["direction"] = input("  Direction [down/up]: ").strip() or "down"
                try:
                    args["amount"] = int(input("  Amount [default=3]: ").strip() or "3")
                except ValueError:
                    args["amount"] = 3
            elif tool == "web_navigate":
                args["url"] = input("  URL: ").strip()
            elif tool == "drag":
                try:
                    args["from_x"] = float(input("  From X (normalized): ").strip())
                    args["from_y"] = float(input("  From Y (normalized): ").strip())
                    args["to_x"] = float(input("  To X (normalized): ").strip())
                    args["to_y"] = float(input("  To Y (normalized): ").strip())
                except ValueError:
                    print("  Invalid coords — skipping")
                    step_count -= 1
                    continue

            # 5-second countdown — position mouse during this time
            print("  Move mouse to target...")
            for i in range(5, 0, -1):
                print(f"  {i}...")
                time.sleep(1)
            print("  Capturing!")

            mx, my = pyautogui.position()
            sw, sh = monitor["width"], monitor["height"]
            nx, ny = mx / sw, my / sh
            print(f"  Mouse at: ({mx}, {my}) = ({nx:.4f}, {ny:.4f})")

            # Capture screenshot and record
            img_bgra = np.array(sct.grab(monitor))
            img_bgr = img_bgra[..., :3]

            # Record element (visual only) or text action
            if tool in ("click", "uia_click", "web_click"):
                meta = record_element(screenshot_bgr=img_bgr, click_px=(mx, my))
                if meta:
                    meta["tool"] = tool
                    meta["args"] = args
                    steps.append(meta)
                    print(f"  Captured: {meta['template_id']}")
                else:
                    print(f"  No button detected")
            else:
                # Text action — store directly
                ts = int(time.time() * 1000)
                meta = {
                    "template_id": f"text_{tool}_{ts}",
                    "tool": tool, "args": args,
                    "ocr_text": args.get("text", args.get("name", args.get("keys", ""))),
                    "roi": {"x": mx, "y": my, "w": 100, "h": 30},
                    "image_path": "", "embedding_384": "", "dhash": "0",
                    "window": {"class": "", "title": "", "pid": 0, "rect": [0, 0, 0, 0]},
                }
                steps.append(meta)
                print(f"  Captured: {tool} action")
                continue

    if steps:
        path = save_macro(name, task, steps)
        print(f"\n✓ Macro saved: {path} ({len(steps)} steps)")
    else:
        print("\nNo steps recorded.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()

    if cmd == "list":
        cmd_list()
    elif cmd == "to-script":
        if len(sys.argv) < 3:
            print("Usage: python cua/macro_editor.py to-script <macro_name>")
            return
        from cua.recorder import macro_to_script
        macro_to_script(sys.argv[2])
    elif cmd == "show":
        if len(sys.argv) < 3:
            print("Usage: python cua/macro_editor.py show <name>")
            return
        cmd_show(sys.argv[2])
    elif cmd == "play":
        step_mode = "--step" in sys.argv
        args = [a for a in sys.argv[2:] if a != "--step"]
        if not args:
            print("Usage: python cua/macro_editor.py play [--step] <name>")
            return
        cmd_play(args[0], step_mode=step_mode)
    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("Usage: python cua/macro_editor.py delete <name>")
            return
        cmd_delete(sys.argv[2])
    elif cmd == "record":
        if len(sys.argv) < 4:
            print("Usage: python cua/macro_editor.py record <name> <task>")
            return
        cmd_record(sys.argv[2], " ".join(sys.argv[3:]))
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()

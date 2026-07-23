"""Compare UIA tree before and after screen-reader emulation.

Usage: python cua/test_uia_warmup.py
Make sure WeChat (or any target app) is in the foreground before running.
"""
import ctypes
from ctypes import wintypes
import time

import uiautomation as uia

MAX_DEPTH = 50


def _force_read(ctrl):
    """Force-read basic properties to trigger lazy provider generation."""
    try:
        _ = ctrl.ControlTypeName
        _ = (ctrl.Name or "")
        _ = (ctrl.AutomationId or "")
        _ = ctrl.BoundingRectangle
        _ = ctrl.IsEnabled
        _ = ctrl.IsOffscreen
    except Exception:
        pass
    try:
        vp = ctrl.GetValuePattern()
        _ = vp.Value
    except Exception:
        pass


def inspect_flat(depth: int = 4) -> tuple[int, str]:
    """Simple one-shot inspection — what automation tools normally see."""
    fg = uia.GetForegroundControl()
    if fg is None:
        return 0, "(no foreground window)"

    lines = [f"Window: {fg.Name} ({fg.ControlTypeName})"]
    count = [1]

    def walk(ctrl, d):
        if d > depth:
            return
        indent = "  " * d
        info = f"{indent}{ctrl.ControlTypeName}"
        if ctrl.Name:
            info += f" '{ctrl.Name}'"
        if ctrl.AutomationId:
            info += f" #{ctrl.AutomationId}"
        lines.append(info)
        try:
            for child in ctrl.GetChildren():
                count[0] += 1
                walk(child, d + 1)
        except Exception:
            pass

    walk(fg, 0)
    return count[0], "\n".join(lines)


def inspect_deep(depth: int = 8) -> tuple[int, str]:
    """Deep inspection with force-read — screen-reader-style probing."""
    fg = uia.GetForegroundControl()
    if fg is None:
        return 0, "(no foreground window)"

    lines = [f"Window: {fg.Name} ({fg.ControlTypeName})"]
    count = [1]

    def walk(ctrl, d):
        if d > depth:
            return
        _force_read(ctrl)  # triggers lazy provider
        indent = "  " * d
        info = f"{indent}{ctrl.ControlTypeName}"
        if ctrl.Name:
            info += f" '{ctrl.Name}'"
        if ctrl.AutomationId:
            info += f" #{ctrl.AutomationId}"
        # Show value if any
        try:
            vp = ctrl.GetValuePattern()
            if vp.Value:
                info += f' = "{vp.Value[:60]}"'
        except Exception:
            pass
        lines.append(info)
        try:
            for child in ctrl.GetChildren():
                count[0] += 1
                walk(child, d + 1)
        except Exception:
            pass

    walk(fg, 0)
    return count[0], "\n".join(lines)


def warmup_aggressive():
    """Simulate screen reader startup — WinEvents + deep scan + focus tracking."""
    print("  Subscribing to global WinEvents...")
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    WINEVENT_OUTOFCONTEXT = 0x0000
    WINEVENT_SKIPOWNPROCESS = 0x0002

    events = {
        "focus": 0x8005,
        "foreground": 0x0003,
        "create": 0x8000,
        "name_change": 0x800C,
        "state_change": 0x800A,
    }

    WinEventProc = ctypes.WINFUNCTYPE(
        None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
        wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
    )

    def cb(*args):
        pass

    callback = WinEventProc(cb)
    hooks = []
    for name, evt_id in events.items():
        h = user32.SetWinEventHook(
            evt_id, evt_id, 0, callback, 0, 0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        )
        if h:
            hooks.append(h)
            print(f"    Hooked {name} (0x{evt_id:04X})")
    print(f"  {len(hooks)}/{len(events)} WinEvent hooks active")

    # Deep scan
    print("  Deep-scanning desktop tree (depth=50, force-read all)...")
    root = uia.GetRootControl()
    try:
        for child in root.GetChildren():
            _force_read(child)
    except Exception:
        pass

    # Focus probe
    try:
        focused = uia.GetFocusedControl()
        if focused:
            _force_read(focused)
            print(f"  Focused: {focused.ControlTypeName} '{focused.Name}'")
    except Exception:
        pass

    # Poll focus/foreground a few times
    print("  Polling focus/foreground...")
    for _ in range(10):
        try:
            fg = uia.GetForegroundControl()
            if fg:
                _force_read(fg)
                for child in fg.GetChildren():
                    _force_read(child)
            fc = uia.GetFocusedControl()
            if fc:
                _force_read(fc)
        except Exception:
            pass
        time.sleep(0.3)

    print("  Warmup complete.\n")


def main():
    print("=" * 60)
    print("UIA Screen-Reader Emulation — Before/After Comparison")
    print("=" * 60)
    print()
    print("Make sure the TARGET APP is in the foreground!")
    print("Starting in 3 seconds...")
    for i in range(3, 0, -1):
        print(f"  {i}...")
        time.sleep(1)

    # --- BEFORE ---
    print()
    print("=" * 60)
    print("BEFORE: Standard one-shot automation tool")
    print("=" * 60)
    count_before, tree_before = inspect_flat(depth=4)
    print(f"\nNodes found: {count_before}")
    print(tree_before[:2000])

    # --- WARMUP ---
    print()
    print("=" * 60)
    print("WARMING UP: Aggressive screen-reader emulation")
    print("=" * 60)
    warmup_aggressive()

    # --- AFTER ---
    print("=" * 60)
    print("AFTER: Screen-reader emulation active")
    print("=" * 60)
    count_after, tree_after = inspect_deep(depth=8)
    print(f"\nNodes found: {count_after}")
    print(tree_after[:2000])

    # --- Summary ---
    print()
    print("=" * 60)
    print("COMPARISON SUMMARY")
    print("=" * 60)
    print(f"  Before: {count_before} nodes (standard depth=4)")
    print(f"  After:  {count_after} nodes (force-read depth=8 + WinEvents)")
    if count_after > count_before:
        delta = count_after - count_before
        pct = (count_after / max(count_before, 1) - 1) * 100
        print(f"  Delta:  +{delta} nodes (+{pct:.0f}%)")
    elif count_after == count_before:
        print("  No change — app may not respond to screen reader detection")
    else:
        print(f"  Delta:  {count_after - count_before} nodes (unexpected)")

    print()
    print("Note: 'nodes' = visible controls in the tree. If WeChat responded,")
    print("you should see new Pane, Button, ListItem, or Text controls appear")
    print("that were hidden in the BEFORE scan.")

    # Write full trees to files for diffing
    with open("uia_before.txt", "w", encoding="utf-8") as f:
        f.write(tree_before)
    with open("uia_after.txt", "w", encoding="utf-8") as f:
        f.write(tree_after)
    print("\nFull trees written to uia_before.txt / uia_after.txt")


if __name__ == "__main__":
    main()

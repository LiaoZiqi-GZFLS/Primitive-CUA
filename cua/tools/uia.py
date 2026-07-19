"""UI Automation tools: inspect, click, set_value, get_text via Windows UIA.

Implements a screen-reader-emulation layer to trigger full accessibility provider
loading in apps like WeChat that hide their UIA tree from one-shot automation tools.

Screen readers are detected by Windows apps through:
  - Subscribing to global WinEvents via SetWinEventHook (the definitive signal)
  - Long-lived UIA client instance (not per-call)
  - Frequent GetForegroundControl / GetFocusedElement calls

By emulating this pattern, we convince apps to load their full UIA provider.
"""
import atexit
import ctypes
from ctypes import wintypes
import threading
import time

import uiautomation as uia

# --- WinEvent hook (screen-reader-level event subscription) ---

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002

# Events that screen readers subscribe to — triggers full UIA provider loading
_WINEVENTS = {
    "focus": 0x8005,       # EVENT_OBJECT_FOCUS
    "foreground": 0x0003,  # EVENT_SYSTEM_FOREGROUND
    "create": 0x8000,      # EVENT_OBJECT_CREATE
    "name_change": 0x800C, # EVENT_OBJECT_NAMECHANGE
    "state_change": 0x800A,# EVENT_OBJECT_STATECHANGE
}

_WinEventProc = ctypes.WINFUNCTYPE(
    None,
    wintypes.HANDLE, wintypes.DWORD, wintypes.HWND,
    wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD,
)

# Module-level references MUST be kept alive — if GC'd, hooks stop firing
_hooks: list[int] = []
_callback = None


def _win_event_callback(hook, event, hwnd, obj_id, child_id, thread_id, time_ms):
    """Silent callback — the subscription itself is the signal to apps."""
    pass


def _subscribe_winevents() -> bool:
    """Subscribe to global WinEvents like a screen reader.

    This is the definitive signal that triggers apps like WeChat to load
    their full Qt+CEF accessibility provider. Returns True on success.
    """
    global _callback, _hooks

    if _hooks:
        return True  # Already subscribed

    _callback = _WinEventProc(_win_event_callback)

    for name, evt_id in _WINEVENTS.items():
        hook = _user32.SetWinEventHook(
            evt_id, evt_id,
            0,           # hmodWinEventProc — 0 for global
            _callback,   # callback
            0, 0,        # idProcess, idThread — 0 = all
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
        )
        if hook:
            _hooks.append(hook)
        else:
            err = _kernel32.GetLastError()
            print(f"  [uia] WinEvent hook '{name}' failed: err={err}")

    print(f"  [uia] WinEvent hooks: {len(_hooks)}/{len(_WINEVENTS)} subscribed")
    return len(_hooks) > 0


def _unhook_winevents():
    """Remove all WinEvent hooks (called on exit)."""
    global _hooks, _callback
    for hook in _hooks:
        try:
            _user32.UnhookWinEvent(hook)
        except Exception:
            pass
    _hooks.clear()
    _callback = None


# --- Screen-reader emulation session ---

_screen_reader = {
    "active": False,
    "warmed": False,
    "thread": None,
    "stop": False,
}


def _init_uia():
    """Initialize UIA COM in this thread (required before any UIA calls)."""
    try:
        uia.InitializeUIAutomationInCurrentThread()
    except Exception:
        pass  # May already be initialized


MAX_DEPTH = 50  # Unlimited — traverse entire subtree


def _force_read(ctrl):
    """Force-read all basic properties on a control.

    This coerces lazy accessibility providers (e.g. Qt/CEF in WeChat) to
    generate full accessibility nodes for every element, not just the
    interactive ones they expose to one-shot automation tools.
    """
    try:
        _ = ctrl.ControlTypeName
        _ = (ctrl.Name or "")
        _ = (ctrl.AutomationId or "")
        _ = ctrl.BoundingRectangle
        _ = ctrl.IsEnabled
        _ = ctrl.IsOffscreen
    except Exception:
        pass

    # Try ValuePattern — forces value to be generated
    try:
        vp = ctrl.GetValuePattern()
        _ = vp.Value
    except Exception:
        pass


def _force_read_deep(ctrl, depth=0):
    """Force-read this node AND all descendants up to MAX_DEPTH.

    The exhaustive traversal pattern is the screen-reader signature that
    triggers full UIA provider loading in WeChat (Qt+CEF) and similar apps.
    """
    if depth > MAX_DEPTH:
        return
    try:
        _force_read(ctrl)

        # CEF detection: if this is a Document or Group control, try
        # DocumentPattern to force the embedded web accessibility tree to load.
        ct = ctrl.ControlTypeName
        aid = (ctrl.AutomationId or "").lower()
        name = (ctrl.Name or "").lower()
        is_cef_host = (
            ct in ("Document", "Group", "Pane") and
            any(kw in aid or kw in name for kw in
                ("chrome", "cef", "browser", "web", "render", "widget"))
        )
        if is_cef_host:
            try:
                dp = ctrl.GetDocumentPattern()
                _ = dp  # forces provider activation
            except Exception:
                pass

        for child in ctrl.GetChildren():
            _force_read_deep(child, depth + 1)
    except Exception:
        pass


def _warm_uia():
    """Emulate a screen reader session to trigger full UIA provider loading.

    Called once before the first UIA tool call. The behaviors below match
    what Windows screen readers (Narrator, NVDA, JAWS) do, triggering apps
    like WeChat to load their full Qt+CEF accessibility provider.
    """
    global _screen_reader

    if _screen_reader["warmed"]:
        return

    _screen_reader["warmed"] = True
    _init_uia()

    print("  [uia] starting screen-reader emulation (aggressive)...")

    # 1. Subscribe to global WinEvents — THE definitive screen-reader signal.
    _subscribe_winevents()

    # 2. Global search timeout — screen readers are patient
    uia.SetGlobalSearchTimeout(10000)

    # 3. Aggressive full-desktop deep scan — depth=50, force-read all nodes.
    #    This simulates a screen reader doing its initial "scan everything".
    #    The exhaustive pattern triggers lazy providers to fully populate.
    print("  [uia] deep-scanning desktop tree (depth=50, force-read all)...")
    node_count = [0]
    try:
        root = uia.GetRootControl()
        for child in root.GetChildren():
            _force_read_deep(child, depth=0)
            node_count[0] += 1
    except Exception as e:
        print(f"  [uia] desktop scan interrupted: {e}")
    print(f"  [uia] desktop scan touched {node_count[0]} top-level windows")

    # 4. Get focused element explicitly — screen readers "read" the focus
    try:
        focused = uia.GetFocusedControl()
        if focused is not None:
            _force_read_deep(focused, depth=0)
            print(f"  [uia] focused: {focused.ControlTypeName} '{focused.Name}'")
    except Exception:
        pass

    # 5. Background focus tracker — continuous focus polling + subtree probing
    def _focus_tracker():
        prev_focus = None
        while not _screen_reader["stop"]:
            try:
                # Get foreground AND focused — screen readers track both
                fg = uia.GetForegroundControl()
                focused = uia.GetFocusedControl()

                if fg is not None:
                    # Force-read foreground window properties every cycle
                    fg_id = id(fg)
                    if fg_id != prev_focus:
                        prev_focus = fg_id
                        # Deep-scan the new foreground window — screen readers
                        # re-scan when foreground changes
                        _force_read_deep(fg, depth=0)

                if focused is not None:
                    # Force-read focused element + its ancestors (screen reader
                    # reads the focus chain on every change)
                    _force_read(focused)
                    try:
                        for child in focused.GetChildren():
                            _force_read(child)
                    except Exception:
                        pass
            except Exception:
                pass
            time.sleep(0.3)  # 300ms — faster polling for responsiveness

    _screen_reader["stop"] = False
    _screen_reader["thread"] = threading.Thread(
        target=_focus_tracker, daemon=True, name="uia-focus-tracker"
    )
    _screen_reader["thread"].start()
    _screen_reader["active"] = True

    print("  [uia] screen-reader emulation active (WinEvents + deep scan + focus tracking)")


def _ensure_warm():
    """Ensure screen-reader emulation is running before any UIA call."""
    if not _screen_reader["warmed"]:
        _warm_uia()


def _stop_screen_reader():
    """Stop background thread + unhook WinEvents (called on exit)."""
    global _screen_reader
    _screen_reader["stop"] = True
    _screen_reader["active"] = False
    _unhook_winevents()


atexit.register(_stop_screen_reader)


# --- Control helpers ---

def _foreground_control():
    """Get the foreground window's UIA control.

    On first call per window, triggers a deep property probe to force
    lazy accessibility providers to fully populate.
    """
    _ensure_warm()
    fg = uia.GetForegroundControl()
    if fg is not None:
        # Force-read top-level properties + immediate children
        _force_read(fg)
        try:
            for child in fg.GetChildren():
                _force_read(child)
        except Exception:
            pass
    return fg


def _find_control(name: str, max_depth: int = MAX_DEPTH):
    """Find a control by name (partial match, case-insensitive) in the foreground window.

    Uses exhaustive deep search (depth=50) — the aggressive traversal forces
    lazy UIA providers to fully populate their tree.
    """
    fg = _foreground_control()
    if fg is None:
        return None

    name_lower = name.lower()

    def search(ctrl, depth):
        if depth > max_depth:
            return None
        _force_read(ctrl)  # Force property generation on every node touched
        ctrl_name = (ctrl.Name or "").lower()
        if name_lower in ctrl_name:
            return ctrl
        try:
            for child in ctrl.GetChildren():
                result = search(child, depth + 1)
                if result:
                    return result
        except Exception:
            pass
        return None

    return search(fg, 0)


def _format_control(ctrl, depth=0):
    """Format a control into a readable tree line."""
    indent = "  " * depth
    info = f"{ctrl.ControlTypeName}"
    if ctrl.Name:
        info += f" '{ctrl.Name}'"
    if ctrl.AutomationId:
        info += f" #{ctrl.AutomationId}"
    rect = ctrl.BoundingRectangle
    if rect:
        info += f" ({rect.left}, {rect.top}, {rect.width()}x{rect.height()})"
    return f"{indent}{info}"


# --- Schemas ---

UIA_INSPECT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "uia_inspect",
        "description": "Inspect the UI controls of the current foreground window. Returns a tree of controls with their names, types, positions, and values. Performs exhaustive deep traversal (up to depth 50) — the aggressive probing forces apps like WeChat to expose their full UIA tree. Use this to understand the structure of native Windows apps, Office programs, and dialogs before interacting with them.",
        "parameters": {
            "type": "object",
            "properties": {
                "depth": {
                    "type": "integer",
                    "description": f"How deep to traverse (1-{MAX_DEPTH}, default 6). Higher = more detail at the cost of time.",
                },
            },
            "required": [],
        },
    },
}


UIA_CLICK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "uia_click",
        "description": "Click a UI control by its name (partial match, case-insensitive) in the current foreground window. Use uia_inspect first to see available controls. Works on buttons, menu items, tabs, checkboxes — any clickable control. Much more reliable than coordinate-based clicking for native apps.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Control name to click (e.g. 'OK', 'Cancel', 'File', 'Bold')"},
            },
            "required": ["name"],
        },
    },
}


UIA_SET_VALUE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "uia_set_value",
        "description": "Set the value of an input/editable control by its name. Use for typing into native app text fields, setting cell values in Excel, filling form fields in dialogs. Supports Chinese text. Use uia_inspect first to find the control name.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Control name to target (e.g. 'Document', 'File name:', 'Cell')"},
                "value": {"type": "string", "description": "The text value to set"},
            },
            "required": ["name", "value"],
        },
    },
}


UIA_GET_TEXT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "uia_get_text",
        "description": "Read the text/value of a UI control by its name. Use to read document content, cell values, label text, status messages. Use uia_inspect first to find the control name.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Control name to read from (e.g. 'Document', 'Status', 'Cell')"},
            },
            "required": ["name"],
        },
    },
}


# --- Executors ---

def execute_uia_inspect(depth: int = 6) -> dict:
    """Dump control tree of foreground window with full property probing.

    Traverses exhaustively (up to depth 50) and force-reads Name,
    AutomationId, ValuePattern on every node. This aggressive probing
    coerces lazy UIA providers to generate complete accessibility trees.
    """
    try:
        depth = max(1, min(MAX_DEPTH, depth))
        fg = _foreground_control()
        if fg is None:
            return {
                "content": [{"type": "text", "text": "No foreground window found."}],
                "mouse_pos": None, "last_screenshot": None,
            }

        lines = [f"Active window: {fg.Name}"]
        scanned = [0]

        def walk(ctrl, d):
            if d > depth:
                return
            # Force-read all properties — triggers lazy provider generation
            _force_read(ctrl)
            scanned[0] += 1
            # Format with value if available
            line = _format_control(ctrl, d)
            try:
                vp = ctrl.GetValuePattern()
                if vp.Value:
                    line += f' = "{vp.Value[:60]}"'
            except Exception:
                pass
            lines.append(line)
            try:
                for child in ctrl.GetChildren():
                    walk(child, d + 1)
            except Exception:
                pass

        walk(fg, 0)

        text = f"Scanned {scanned[0]} nodes at depth {depth}\n\n" + "\n".join(lines[:300])
        return {
            "content": [{"type": "text", "text": text}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"UIA inspect failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


def execute_uia_click(name: str) -> dict:
    """Click a control by name."""
    try:
        ctrl = _find_control(name)
        if ctrl is None:
            return {
                "content": [{"type": "text", "text": f"Control '{name}' not found. Try uia_inspect to see available controls."}],
                "mouse_pos": None, "last_screenshot": None,
            }

        # Click() often throws COM errors even when the click actually succeeds.
        try:
            ctrl.Click()
        except Exception:
            try:
                inv = ctrl.GetInvokePattern()
                inv.Invoke()
            except Exception:
                pass

        time.sleep(0.2)

        return {
            "content": [{"type": "text", "text": f"Clicked: {ctrl.Name} ({ctrl.ControlTypeName})"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"UIA click failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


def execute_uia_set_value(name: str, value: str) -> dict:
    """Set value of an editable control."""
    try:
        ctrl = _find_control(name)
        if ctrl is None:
            return {
                "content": [{"type": "text", "text": f"Control '{name}' not found. Try uia_inspect to see available controls."}],
                "mouse_pos": None, "last_screenshot": None,
            }

        # Try ValuePattern first (most reliable)
        try:
            vp = ctrl.GetValuePattern()
            vp.SetValue(value)
            time.sleep(0.1)
            return {
                "content": [{"type": "text", "text": f"Set value of '{ctrl.Name}': '{value}'"}],
                "mouse_pos": None, "last_screenshot": None,
            }
        except Exception:
            pass

        # Fallback: click to focus, then paste
        ctrl.Click()
        time.sleep(0.1)
        ctrl.SendKeys("{Ctrl}a")
        import pyperclip
        pyperclip.copy(value)
        ctrl.SendKeys("{Ctrl}v")
        time.sleep(0.1)

        return {
            "content": [{"type": "text", "text": f"Set value of '{ctrl.Name}' via paste: '{value}'"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"UIA set_value failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


def execute_uia_get_text(name: str) -> dict:
    """Read text/value from a control."""
    try:
        ctrl = _find_control(name)
        if ctrl is None:
            return {
                "content": [{"type": "text", "text": f"Control '{name}' not found. Try uia_inspect to see available controls."}],
                "mouse_pos": None, "last_screenshot": None,
            }

        text = ctrl.Name or ""
        try:
            vp = ctrl.GetValuePattern()
            text = vp.Value or text
        except Exception:
            pass

        return {
            "content": [{"type": "text", "text": f"Text of '{ctrl.Name}': {text}"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"UIA get_text failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


# --- Run dialog ---

RUN_COMMAND_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_command",
        "description": "Open the Windows Run dialog (Win+R), type a command, and press Enter. Use for: opening paths ('C:\\Users'), launching executables ('cmd', 'notepad', 'control'), opening URLs, running shell commands. Faster than Start menu search for system commands.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to run — path, executable name, URL, or shell command",
                },
            },
            "required": ["command"],
        },
    },
}


def execute_run_command(command: str) -> dict:
    """Win+R, type command, Enter."""
    import pyautogui
    import pyperclip

    try:
        pyautogui.hotkey("win", "r")
        time.sleep(0.2)

        # Use paste for non-ASCII, typewrite for ASCII
        if command.isascii():
            pyautogui.typewrite(command, interval=0.02)
        else:
            pyperclip.copy(command)
            time.sleep(0.05)
            pyautogui.hotkey("ctrl", "v")

        time.sleep(0.2)
        # Press Enter twice — Chinese IME may consume the first one
        pyautogui.press("enter")
        time.sleep(0.1)
        pyautogui.press("enter")
        time.sleep(0.5)

        return {
            "content": [{"type": "text", "text": f"Ran: {command}"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Run command failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }

UIA_CLICK_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

UIA_SET_VALUE_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

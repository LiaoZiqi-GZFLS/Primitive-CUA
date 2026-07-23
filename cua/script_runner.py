"""Script engine for CUA automation scripts (.cua).

Architecture:
  ScriptEngine  — importable engine: load + run scripts programmatically
  ScriptResult  — structured return: code 0/1/2 + summary + log
  CLI           — python cua/script_runner.py <script.cua> [--step] [--debug]

Return codes:
  0 — Success: task completed as expected
  1 — Failure: task could not be completed, do not retry
  2 — Delegate: neither success nor failure, hand over to K3 Agent

Usage:
  from cua.script_runner import ScriptEngine, ScriptResult
  engine = ScriptEngine(config)
  result = engine.run("cua/data/scripts/my_task.cua", step_mode=False)
  if result.code == 0:   print("Done")
  elif result.code == 2: agent_result = run_task(task, config)

=== Script Syntax ===

  # ── Return ──
  return 0 summary text       # Success
  return 1 summary text       # Failure
  return 2 summary text       # Delegate to K3 Agent

  # ── Variables ──
  set name value              # $name = value
  print text                  # Console output ($VAR expansion ok)

  # ── Actions ──
  click target_text           # Template-match + click
  dblclick target_text        # Template-match + double-click
  uia_click control_name      # UIA Invoke
  web_click element_text      # Playwright click
  type text                   # Paste via clipboard
  keys combo                  # Keyboard shortcut
  launch app_name             # Start menu launch
  wait seconds                # Sleep
  scroll direction amount     # Scroll (dir=up/down, amount=pixels)
  navigate url                # Web browser
  drag from_elem to_elem      # Drag from one element to another
  drag from_elem dir dist      # Drag from element: up/down/left/right Npx
  screenshot [path]           # Save screenshot
  ocr [path]                  # OCR → $ocr_result
  move x y                    # Move mouse (normalized 0-1)

  # ── Control flow ──
  if kimi question            # K3 vision: yes/no
  if see target               # Element visible via template match?
  if ocr text                 # Text on screen?
  if window title_part        # Window with title open?
  if url url_part             # Current browser URL contains?
  if not see target           # Negation — element NOT visible
    ...               (indent 4 spaces for body)
  else
    ...
  endif

  repeat N              (eats body lines; N iterations)
    ...
  endrepeat

  retry N               (repeat up to N times, stop on first success)
    ...
  endretry

  while kimi question   (re-evaluates condition each iteration)
    ...
  endwhile

  try                   (catch errors, execute catch block on failure)
    ...
  catch
    ...
  endtry

  goto label             label name
  wait_until see target [timeout 10]
  fail reason
  exec macro_name        # Run another macro inline
  input var prompt       # Read user input into $var
  sleep seconds          # Alias for wait

  # ── Built-in variables ──
  $screen_w / $screen_h   $ocr_result   $last_result   $now
"""
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).parent / "data" / "scripts"
SCRIPT_DIR.mkdir(parents=True, exist_ok=True)

_VAR_RE = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)")


@dataclass
class ScriptResult:
    """Structured return from script execution.

    code 0 = success, 1 = failure, 2 = delegate to K3 Agent.
    """
    code: int
    summary: str
    steps: list = field(default_factory=list)
    tokens: dict = field(default_factory=dict)
    step_count: int = 0
    success_count: int = 0

    @property
    def success(self) -> bool:
        return self.code == 0


class ScriptEngine:
    """Parse and execute .cua automation scripts.

    Importable API — create once with config, call .run() for each script.
    """

    def __init__(self, config: dict = None, step_mode: bool = False,
                 debug: bool = False):
        self.config = config or self._load_config()
        self.step_mode = step_mode
        self.debug = debug
        self.vars: dict[str, str] = {}
        self.labels: dict[str, int] = {}
        self._lines: list[dict] = []
        self._step_count = 0
        self._success_count = 0

    def _load_config(self):
        from cua.config import load_config
        return load_config()

    # ── Public API ──────────────────────────────────────────

    # ── Validation ──────────────────────────────────────────

    VALID_COMMANDS = {
        "click", "dblclick", "uia_click", "web_click", "type", "keys",
        "launch", "wait", "sleep", "scroll", "navigate", "drag",
        "screenshot", "ocr", "move", "set", "print", "input", "exec",
        "if", "else", "endif", "repeat", "endrepeat",
        "while", "endwhile", "retry", "endretry",
        "try", "catch", "endtry", "goto", "label",
        "wait_until", "fail", "finish", "return",
    }
    BLOCK_STARTS = {"if", "repeat", "while", "retry", "try"}
    BLOCK_ENDS = {"endif": "if", "endrepeat": "repeat", "endwhile": "while",
                  "endretry": "retry", "endtry": "try", "catch": "try"}
    REQUIRES_ARG = {
        "click", "dblclick", "uia_click", "web_click", "type", "keys", "launch",
        "goto", "label", "set", "scroll", "navigate", "wait_until",
        "if", "while", "finish", "return", "wait", "sleep", "fail",
        "retry", "input",
    }

    def validate(self, script_path: str) -> list[str]:
        """Validate a script without executing it. Returns list of errors."""
        path = Path(script_path)
        if not path.exists():
            return [f"Script not found: {script_path}"]

        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()

        # Parse without executing
        saved_labels = {}
        errors = []
        raw_lines = raw.splitlines()
        block_stack: list[tuple[str, int, str]] = []  # (block_type, lineno, cmd)

        for lineno, line in enumerate(raw_lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            parts = self._tokenize(stripped)
            if not parts:
                continue
            cmd = parts[0].lower()
            args = parts[1:]

            # Unknown command
            if cmd not in self.VALID_COMMANDS:
                errors.append(f"  L{lineno}: unknown command '{cmd}'")

            # Requires argument
            if cmd in self.REQUIRES_ARG and not args:
                errors.append(f"  L{lineno}: '{cmd}' requires arguments")
            if cmd == "drag" and len(args) not in (2, 3, 4):
                errors.append(f"  L{lineno}: 'drag' needs 2/3/4 args (element-to-element, element+direction+distance, or raw coords)")

            # Block tracking
            if cmd in self.BLOCK_STARTS:
                block_stack.append((cmd, lineno, stripped[:60]))
            elif cmd == "endif":
                if not block_stack or block_stack[-1][0] != "if":
                    errors.append(f"  L{lineno}: 'endif' without matching 'if'")
                else:
                    block_stack.pop()
            elif cmd in ("endrepeat", "endwhile", "endretry", "endtry", "catch"):
                expected = self.BLOCK_ENDS.get(cmd)
                if not block_stack or block_stack[-1][0] != expected:
                    errors.append(f"  L{lineno}: '{cmd}' without matching '{expected}'")
                elif cmd != "catch":  # catch doesn't pop
                    block_stack.pop()

            # Label registration
            if cmd == "label" and args:
                saved_labels[args[0]] = lineno

            # Return code check
            if cmd == "return" and args:
                try:
                    code = int(args[0])
                    if code not in (0, 1, 2):
                        errors.append(f"  L{lineno}: return code must be 0/1/2, got {code}")
                except ValueError:
                    pass

        # Unclosed blocks
        for bt, bl_no, bl_cmd in block_stack:
            errors.append(f"  L{bl_no}: unclosed '{bt}' block: {bl_cmd}")

        # goto target check
        for li, inst in enumerate(self._parse(raw)):
            if inst["cmd"] == "goto" and inst["args"]:
                target = inst["args"][0]
                if target not in saved_labels:
                    errors.append(f"  L{inst['lineno']}: goto target '{target}' not found")

        return errors

    # ── Public API ──────────────────────────────────────────

    def run(self, script_path: str) -> ScriptResult:
        """Load, validate, and execute a script file."""
        path = Path(script_path)
        if not path.exists():
            return ScriptResult(1, f"Script not found: {script_path}")

        # Validate first
        errors = self.validate(script_path)
        if errors:
            print(f"  [script] validation failed — {len(errors)} error(s):")
            for e in errors:
                print(e)
            return ScriptResult(1, f"Validation failed: {len(errors)} error(s)")

        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()

        self._lines = self._parse(raw)
        self._init_vars()
        print(f"  [script] {path.name} ({len(self._lines)} commands) valid")

        return self._execute()

    def run_string(self, source: str, name: str = "<inline>") -> ScriptResult:
        """Execute a script from a string (for testing or inline use)."""
        self._lines = self._parse(source)
        self._init_vars()
        print(f"  [script] {name} ({len(self._lines)} commands)")
        return self._execute()

    # ── Parser ──────────────────────────────────────────────

    def _init_vars(self):
        import pyautogui
        self.vars = {
            "screen_w": str(pyautogui.size()[0]),
            "screen_h": str(pyautogui.size()[1]),
            "now": str(int(time.time() * 1000)),
            "ocr_result": "",
            "last_result": "",
        }
        # Labels are registered during _parse() — don't clear them

    def _parse(self, raw: str) -> list[dict]:
        raw = self._expand_repeat(raw)
        instructions = []
        for lineno, line in enumerate(raw.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = len(line) - len(line.lstrip())
            parts = self._tokenize(stripped)
            if not parts:
                continue
            cmd = parts[0].lower()
            inst = {"lineno": lineno, "cmd": cmd, "args": parts[1:],
                    "raw": stripped, "indent": indent}
            if cmd == "label" and len(parts) > 1:
                self.labels[parts[1]] = len(instructions)
            instructions.append(inst)
        return instructions

    def _expand_repeat(self, raw: str) -> str:
        lines = raw.splitlines()
        result, i = [], 0
        while i < len(lines):
            s = lines[i].strip().lower()
            if s.startswith("repeat "):
                try:
                    n = int(s.split()[1])
                except (ValueError, IndexError):
                    n = 1
                indent = len(lines[i]) - len(lines[i].lstrip())
                j, depth = i + 1, 1
                while j < len(lines) and depth > 0:
                    js = lines[j].strip().lower()
                    ji = len(lines[j]) - len(lines[j].lstrip())
                    if ji == indent:
                        if js.startswith("endrepeat"): depth -= 1
                        elif js.startswith("repeat "): depth += 1
                    j += 1
                body = lines[i + 1:j - 1]
                for _ in range(n):
                    result.extend(body)
                i = j
            else:
                result.append(lines[i])
                i += 1
        return "\n".join(result)

    def _tokenize(self, line: str) -> list[str]:
        tokens, i = [], 0
        while i < len(line):
            if line[i].isspace():
                i += 1; continue
            if line[i] in ('"', "'"):
                end = line.find(line[i], i + 1)
                tokens.append(line[i + 1:end] if end >= 0 else line[i + 1:])
                i = (end + 1) if end >= 0 else len(line)
            else:
                j = i
                while j < len(line) and not line[j].isspace():
                    j += 1
                tokens.append(line[i:j])
                i = j
        return tokens

    def _expand(self, text: str) -> str:
        return _VAR_RE.sub(lambda m: self.vars.get(m.group(1), m.group(0)), text)

    def _xa(self, args: list[str]) -> list[str]:
        return [self._expand(a) for a in args]

    # ── Executor ────────────────────────────────────────────

    def _execute(self) -> ScriptResult:
        ip = 0
        if_stack: list[tuple[int, int, bool]] = []
        while_stack: list[tuple[int, int, int]] = []

        while ip < len(self._lines):
            inst = self._lines[ip]
            cmd = inst["cmd"]

            # Block control — compare indentation levels, not IPs
            if if_stack:
                skip = any(inst["indent"] > indent and not cond
                           for _, indent, cond in if_stack)
                if cmd == "else":
                    _, ei, pc = if_stack[-1]
                    if inst["indent"] == ei:
                        if_stack[-1] = (ei, ei, not pc)
                        ip += 1; continue
                if skip:
                    ip += 1; continue
                if cmd == "endif":
                    if inst["indent"] == if_stack[-1][1]:
                        if_stack.pop()
                    ip += 1; continue

            if cmd == "endwhile":
                if while_stack:
                    si, wi, _ = while_stack[-1]
                    while_stack.pop()
                    if self._while_cond(self._lines[si]):
                        ip = si + 1; continue
                ip += 1; continue
            if cmd in ("endrepeat", "endretry"):
                ip += 1; continue
            if cmd == "catch":
                # Skip catch block (already handled below)
                ip = self._skip_to(ip, "endtry") + 1; continue
            if cmd == "endtry":
                ip += 1; continue

            # Commands
            if cmd == "if":
                ip = self._do_if(inst, ip, if_stack)
            elif cmd == "while":
                cond = self._while_cond(inst)
                print(f"  [while] → {cond}")
                while_stack.append((ip, inst["indent"], 0))
                ip = ip + 1 if cond else self._skip_to(ip, "endwhile") + 1
            elif cmd == "retry":
                n = int(inst["args"][0]) if inst["args"] else 3
                print(f"  [retry] {n}x")
                self._do_retry(ip, n); ip = self._skip_to(ip, "endretry") + 1
            elif cmd == "try":
                print(f"  [try]")
                self._do_try(ip); ip = self._skip_to(ip, "endtry") + 1
            elif cmd == "input":
                self._do_input(inst); ip += 1
            elif cmd == "goto":
                print(f"  → goto {' '.join(inst['args'])}")
                ip = self._do_goto(inst, if_stack, while_stack)
            elif cmd == "label":
                print(f"  [{':'.join(inst['args'])}]")
                ip += 1
            elif cmd == "return":
                return self._do_return(inst)
            elif cmd == "finish":
                return self._do_return(inst)
            elif cmd == "set":
                self._do_set(inst); ip += 1
            elif cmd == "print":
                self._do_print(inst); ip += 1
            elif cmd == "exec":
                self._do_exec(inst); ip += 1
            elif cmd == "wait_until":
                self._do_wait_until(inst); ip += 1
            elif cmd == "fail":
                print(f"  FAIL: {' '.join(inst['args'])}")
                return self._do_fail(inst)
            else:
                self._do_action(inst); ip += 1

        return ScriptResult(0, f"Script: {self._success_count}/{self._step_count} steps",
                            step_count=self._step_count,
                            success_count=self._success_count)

    def _skip_to(self, ip: int, target: str) -> int:
        indent = self._lines[ip]["indent"]
        depth = 1; i = ip + 1
        while i < len(self._lines) and depth > 0:
            li = self._lines[i]
            if li["cmd"] == target and li["indent"] == indent:
                depth -= 1
                if depth == 0: return i
            elif li["cmd"] in self.BLOCK_STARTS and li["indent"] == indent:
                depth += 1
            i += 1
        return len(self._lines) - 1

    def _while_cond(self, inst: dict) -> bool:
        cond = inst["args"][0] if inst["args"] else ""
        return self._ask_kimi(" ".join(inst["args"][1:])) if cond == "kimi" else False

    # ── Control flow handlers ──

    def _do_if(self, inst, ip, if_stack) -> int:
        orig = inst["args"][:] if inst["args"] else []
        negate = False
        if orig and orig[0] == "not":
            negate = True; orig = orig[1:]
        cond = orig[0] if orig else ""
        prompt = " ".join(orig[1:])
        checks = {"kimi": self._ask_kimi, "see": self._check_template,
                  "ocr": self._check_ocr, "window": self._check_window,
                  "url": self._check_url}
        result = checks.get(cond, lambda _: False)(prompt)
        if negate:
            result = not result
        if_stack.append((ip, inst["indent"], result))
        print(f"  [if] {'not ' if negate else ''}{cond} → {result}")
        return ip + 1

    def _do_goto(self, inst, if_stack, while_stack) -> int:
        """Jump to label, clearing block stacks that we leave behind."""
        label = inst["args"][0] if inst["args"] else ""
        target = self.labels.get(label)
        if target is None:
            print(f"  [script] label '{label}' not found — continuing")
            return self._lines.index(inst) + 1

        # Clear block stacks when jumping to a different indent level
        target_indent = self._lines[target]["indent"]
        if_stack[:] = [e for e in if_stack if e[1] <= target_indent]
        while_stack.clear()  # Can't know loop state after jump

        return target

    def _do_return(self, inst) -> ScriptResult:
        args = self._xa(inst["args"])
        try:
            code = int(args[0]) if args else 0
        except ValueError:
            code = 0
        summary = " ".join(args[1:]) if len(args) > 1 else (
            "success" if code == 0 else ("failure" if code == 1 else "delegate"))
        return ScriptResult(code, summary,
                            step_count=self._step_count,
                            success_count=self._success_count)

    def _do_fail(self, inst) -> ScriptResult:
        reason = " ".join(self._xa(inst["args"])) if inst["args"] else "script failed"
        print(f"  FAIL: {reason}")
        return ScriptResult(1, reason,
                            step_count=self._step_count,
                            success_count=self._success_count)

    def _do_set(self, inst):
        if len(inst["args"]) >= 2:
            n, v = inst["args"][0], " ".join(inst["args"][1:])
            self.vars[n] = self._expand(v)

    def _do_print(self, inst):
        print(f"  [print] {' '.join(self._xa(inst['args']))}")

    def _do_exec(self, inst):
        name = " ".join(inst["args"])
        print(f"  [exec] → {name}")
        from cua.recorder import load_macro
        macro = load_macro(name)
        if macro:
            import win32gui
            hwnd = [None]
            def _enum(h, _):
                try:
                    if macro.get("window_class","").lower() in win32gui.GetClassName(h).lower():
                        hwnd[0] = h
                except: pass
            win32gui.EnumWindows(_enum, None)
            if hwnd[0]:
                from cua.fast_replay import _execute_steps
                r = _execute_steps(macro["task"], self.config, macro["steps"], hwnd[0])
                self._step_count += len(macro["steps"])
                if r["success"]:
                    self._success_count += len(macro["steps"])

    def _do_retry(self, ip: int, n: int):
        """Execute body up to N times, stop on first success."""
        end_ip = self._skip_to(ip, "endretry")
        self._step_count += 1
        print(f"  [retry] up to {n} times...")
        for attempt in range(n):
            if self.debug:
                print(f"  [retry] attempt {attempt + 1}/{n}")
            prev_ok = self._success_count
            # Execute body
            body_ip = ip + 1
            while body_ip < end_ip:
                inst = self._lines[body_ip]
                if inst["cmd"] in ("endrepeat", "endretry", "endwhile", "endif", "endtry"):
                    body_ip += 1; continue
                self._do_action(inst)
                body_ip += 1
            # If body succeeded (success count increased), stop
            if self._success_count > prev_ok:
                print(f"  [retry] success on attempt {attempt + 1}")
                break

    def _do_try(self, ip: int):
        """Execute try block, on failure execute catch block."""
        catch_ip = self._skip_to(ip, "catch")
        end_ip = self._skip_to(ip, "endtry")
        self._step_count += 1
        self._in_try = True
        try:
            body_ip = ip + 1
            while body_ip < catch_ip:
                inst = self._lines[body_ip]
                if inst["cmd"] in ("endrepeat", "endretry", "endwhile", "endif", "endtry"):
                    body_ip += 1; continue
                self._do_action(inst)
                body_ip += 1
        except Exception as e:
            print(f"  [try] caught: {e}")
            self._in_try = False
            # Execute catch block
            body_ip = catch_ip + 1
            while body_ip < end_ip:
                inst = self._lines[body_ip]
                if inst["cmd"] in ("endrepeat", "endretry", "endwhile", "endif", "endtry"):
                    body_ip += 1; continue
                if inst["cmd"] not in self.VALID_COMMANDS:
                    body_ip += 1; continue
                try: self._do_action(inst)
                except: pass
                body_ip += 1
        else:
            self._in_try = False

    def _do_input(self, inst):
        """Read user input into a variable."""
        var = inst["args"][0] if inst["args"] else "input"
        prompt = " ".join(inst["args"][1:]) + " " if len(inst["args"]) > 1 else ""
        self.vars[var] = input(f"  [input] {prompt}").strip()
        print(f"  [input] ${var} = '{self.vars[var][:40]}'")

    def _do_wait_until(self, inst):
        args = inst["args"]
        if len(args) < 2: return
        kind, rest = args[0], args[1:]
        timeout = 10
        for a in rest:
            if "=" in a:
                try: k, v = a.split("="); timeout = float(v) if k == "timeout" else timeout
                except: pass
        target = " ".join(a for a in rest if "=" not in a)
        deadline = time.time() + timeout
        check_fn = {"see": self._check_template, "ocr": self._check_ocr,
                    "window": self._check_window}.get(kind)
        if not check_fn: return
        while time.time() < deadline:
            if check_fn(target): return
            time.sleep(0.5)

    # ── Action dispatch ──

    def _do_action(self, inst: dict):
        cmd, args = inst["cmd"], self._xa(inst["args"])
        if self.step_mode:
            if input(f"\n  [{cmd}] {' '.join(args)[:70]} → Enter/s=skip: ").strip() == "s":
                return
        self._step_count += 1
        handlers = {
            "click": self._act_click, "dblclick": self._act_dblclick,
            "uia_click": self._act_uia_click,
            "web_click": self._act_web_click, "type": self._act_type,
            "keys": self._act_keys, "launch": self._act_launch,
            "wait": self._act_wait, "sleep": self._act_wait,
            "scroll": self._act_scroll,
            "navigate": self._act_navigate, "drag": self._act_drag,
            "screenshot": self._act_screenshot, "ocr": self._act_ocr,
            "move": self._act_move,
        }
        h = handlers.get(cmd)
        if h:
            try:
                h(args)
                self._success_count += 1
                print(f"  OK {cmd} {' '.join(args)[:60]}")
            except Exception as e:
                print(f"  FAIL {cmd}: {e}")
                if getattr(self, "_in_try", False):
                    raise

    # ── Actions ──

    def _act_click(self, args):
        t = " ".join(args)
        pt = self._find_template(t)
        if pt:
            import pyautogui; pyautogui.click(pt[0], pt[1]); time.sleep(0.3)
        else:
            raise RuntimeError(f"element '{t}' not found after retries")

    def _act_dblclick(self, args):
        t = " ".join(args)
        pt = self._find_template(t)
        if pt:
            import pyautogui; pyautogui.doubleClick(pt[0], pt[1]); time.sleep(0.3)
        else:
            raise RuntimeError(f"element '{t}' not found after retries")

    def _act_uia_click(self, args):
        from cua.tools.uia import execute_uia_click
        execute_uia_click(" ".join(args))

    def _act_web_click(self, args):
        from cua.tools.web import execute_web_click
        execute_web_click(" ".join(args))

    def _act_type(self, args):
        import pyperclip, pyautogui
        pyperclip.copy(" ".join(args)); pyautogui.hotkey("ctrl", "v"); time.sleep(0.3)

    def _act_keys(self, args):
        import pyautogui
        combo = "".join(args).replace(" ","").split("+")
        pyautogui.hotkey(*combo); time.sleep(0.2)

    def _act_launch(self, args):
        import pyperclip, pyautogui
        pyautogui.hotkey("win"); time.sleep(0.15)
        pyperclip.copy(" ".join(args)); pyautogui.hotkey("ctrl", "v")
        time.sleep(0.15); pyautogui.press("enter"); time.sleep(1.5)

    def _act_wait(self, args):
        time.sleep(max(0.1, min(120, float(args[0] if args else 1))))

    def _act_scroll(self, args):
        import pyautogui
        d, a = (args[0] if args else "down"), (int(args[1]) if len(args) > 1 else 3)
        pyautogui.scroll(a if d == "up" else -a); time.sleep(0.2)

    def _act_navigate(self, args):
        from cua.tools.web import execute_web_navigate
        execute_web_navigate(" ".join(args)); time.sleep(0.5)

    def _act_drag(self, args):
        """Drag from one element to another, or from element in a direction.

        Syntax:
          drag "from_element" "to_element"  — drag between two named elements
          drag "element" up|down|left|right N   — drag from element by N pixels
          drag "element" angle_degrees N     — drag at angle (0=right, 90=down)
        """
        import pyautogui

        if len(args) == 2:
            # Element-to-element: find both via template matching
            from_pt = self._find_template(args[0])
            to_pt = self._find_template(args[1])
            if from_pt and to_pt:
                pyautogui.moveTo(from_pt[0], from_pt[1])
                pyautogui.mouseDown()
                pyautogui.moveTo(to_pt[0], to_pt[1], duration=0.5)
                pyautogui.mouseUp()
                time.sleep(0.3)
            elif from_pt:
                print(f"  drag: element '{args[1]}' not found — falling back")
                # Fallback: interpret as direction
                self._drag_direction(from_pt, args[1])
            else:
                print(f"  drag: source element '{args[0]}' not found")

        elif len(args) == 3:
            # Element + direction + distance
            from_pt = self._find_template(args[0])
            if from_pt:
                self._drag_direction(from_pt, args[1], args[2])
            else:
                print(f"  drag: element '{args[0]}' not found")

        elif len(args) == 4:
            # Legacy: raw coordinates
            fx, fy, tx, ty = map(float, args[:4])
            sw, sh = pyautogui.size()
            pyautogui.moveTo(int(fx * sw), int(fy * sh))
            pyautogui.drag(int((tx - fx) * sw), int((ty - fy) * sh), duration=0.3)
            time.sleep(0.3)

    def _drag_direction(self, from_pt, direction, distance="100"):
        """Drag from a point in a direction for a given distance."""
        import pyautogui, math
        try: dist = int(distance) if isinstance(distance, str) else distance
        except: dist = 100

        dirs = {"up": -90, "down": 90, "left": 180, "right": 0}
        angle = dirs.get(str(direction).lower(), None)
        if angle is None:
            try: angle = float(direction)
            except: angle = 0

        rad = math.radians(angle)
        dx = int(dist * math.cos(rad))
        dy = int(dist * math.sin(rad))

        pyautogui.moveTo(from_pt[0], from_pt[1])
        pyautogui.mouseDown()
        pyautogui.moveTo(from_pt[0] + dx, from_pt[1] + dy, duration=0.5)
        pyautogui.mouseUp()
        time.sleep(0.3)

    def _act_screenshot(self, args):
        import cv2, mss
        path = args[0] if args else f"screenshot_{int(time.time())}.png"
        img = np.array(mss.MSS().grab(mss.MSS().monitors[1])); cv2.imwrite(path, img[..., :3])

    def _act_ocr(self, args):
        import mss
        from cua.tools.screenshot import _get_ocr_engine
        img = np.array(mss.MSS().grab(mss.MSS().monitors[1]))
        engine = _get_ocr_engine(); results, _ = engine(img[..., [2, 1, 0]])
        self.vars["ocr_result"] = " ".join(r[1] for r in (results or [])
                                           if r[2] and float(r[2]) > 0.5)[:200]

    def _act_move(self, args):
        import pyautogui
        pyautogui.moveTo(int(float(args[0]) * pyautogui.size()[0]),
                         int(float(args[1]) * pyautogui.size()[1])); time.sleep(0.1)

    # ── Perception ──

    def _find_template(self, target_text: str) -> tuple | None:
        from cua.recorder import list_templates, _embed_text
        tmpls = list_templates()
        if not tmpls: return None

        # Level 0: direct text match (fast, exact or substring)
        tlower = target_text.lower()
        best_t = None
        for tm in tmpls:
            ocr = tm.get("ocr_text", "").lower()
            if tlower == ocr or tlower in ocr or ocr in tlower:
                best_t = tm
                break

        # Level 1: embedding fallback (fuzzy, cross-language)
        if not best_t:
            tv = _embed_text(target_text)
            best_s = 0
            for tm in tmpls:
                eh = tm.get("embedding_384","")
                if eh and len(eh) >= 32:
                    try:
                        b = bytes.fromhex(eh.ljust(768,"0")[:768])
                        v = np.frombuffer(b, dtype=np.float16)
                        s = float(np.dot(tv,v) / (np.linalg.norm(tv) * np.linalg.norm(v) + 1e-8))
                        if s > best_s: best_s, best_t = s, tm
                    except: pass
            if not best_t or best_s < 0.12:
                return None

        if best_t:
            roi = best_t.get("roi", {})
            path = best_t.get("image_path", "")
            win_cls = best_t.get("window", {}).get("class", "")
            click_px = best_t.get("click_px", [0, 0])

            # Find window offset to convert window-relative ROI to screen coords
            win_offset = [0, 0]
            try:
                import win32gui
                def _find_win(h, _):
                    if not win32gui.IsWindowVisible(h): return
                    try:
                        if win_cls.lower() in win32gui.GetClassName(h).lower():
                            r = win32gui.GetWindowRect(h)
                            win_offset[0], win_offset[1] = r[0], r[1]
                    except: pass
                win32gui.EnumWindows(_find_win, None)
            except: pass
            win_ox, win_oy = win_offset[0], win_offset[1]

            # Prefer window-offset ROI; fall back to original click point
            if win_ox > -30000 and win_oy > -30000:
                screen_x, screen_y = roi.get("x", 0) + win_ox, roi.get("y", 0) + win_oy
            else:
                screen_x, screen_y = click_px[0], click_px[1]

            if path and os.path.exists(path):
                import cv2, mss
                tm_bgr = cv2.imread(path)
                if tm_bgr is not None:
                    from cua.fast_replay import _template_match
                    for _retry in range(3):
                        try:
                            with mss.MSS() as sct:
                                img = np.array(sct.grab(sct.monitors[1]))[...,:3]
                            if win_ox > -30000 and win_oy > -30000:
                                win_w = best_t.get("window", {}).get("rect", [0,0,1920,1080])[2]
                                win_h = best_t.get("window", {}).get("rect", [0,0,1920,1080])[3]
                                roi_rect = (win_ox, win_oy, min(win_w, 1920), min(win_h, 1080))
                            else:
                                roi_rect = (screen_x - max(roi.get("w",20)*5, 200),
                                            screen_y - max(roi.get("h",10)*5, 200),
                                            max(roi.get("w",20)*11, 500),
                                            max(roi.get("h",10)*11, 500))
                            pt, sc = _template_match(img, tm_bgr, roi_rect)
                            if pt and sc > 0.65:
                                return pt
                        except Exception:
                            pass
                        if _retry < 2:
                            time.sleep([1, 2][_retry])  # exponential backoff
            return None  # All retries failed
        return None

    def _check_template(self, t): return self._find_template(t) is not None
    def _check_ocr(self, t):
        import mss; from cua.tools.screenshot import _get_ocr_engine
        try:
            img = np.array(mss.MSS().grab(mss.MSS().monitors[1]))
            e = _get_ocr_engine(); r, _ = e(img[...,[2,1,0]])
            return t.lower() in " ".join(x[1].lower() for x in (r or [])
                                         if x[2] and float(x[2]) > 0.5)
        except: return False
    def _check_window(self, t):
        import win32gui; r = [False]
        def _e(h,_):
            if win32gui.IsWindowVisible(h):
                try:
                    if t.lower() in win32gui.GetWindowText(h).lower(): r[0]=True
                except: pass
        win32gui.EnumWindows(_e,None); return r[0]
    def _check_url(self, t):
        try:
            from cua.tools.web import _get_page
            return t.lower() in _get_page().url.lower()
        except: return False

    def _ask_kimi(self, question: str) -> bool:
        from openai import OpenAI
        ak = self.config.get("moonshot_api_key","") or os.environ.get("MOONSHOT_API_KEY","")
        if not ak: return True
        model = self.config.get("model","kimi-k3")
        base_url = self.config.get("base_url","https://api.moonshot.cn/v1")
        client = OpenAI(api_key=ak, base_url=base_url)
        import mss
        from cua.tools.screenshot import downsample_for_vlm, _np_to_png_b64
        img = np.array(mss.MSS().grab(mss.MSS().monitors[1]))
        sc,_,_ = downsample_for_vlm(img,(0.5,0.5),img.shape[1],img.shape[0])
        try:
            r=client.chat.completions.create(
                model=model,
                messages=[
                    {"role":"system","content":"You are a vision validator. Look at the screenshot. Output JSON: {\"answer\": true/false, \"brief\": \"why\"}"},
                    {"role":"user","content":[
                        {"type":"image_url","image_url":{"url":_np_to_png_b64(sc)}},
                        {"type":"text","text":question},
                    ]},
                ],
                response_format={"type":"json_object"}, max_tokens=100,
            )
            return json.loads(r.choices[0].message.content or "{}").get("answer",True)
        except: return True


# ── CLI ────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    path = sys.argv[1]
    step_mode = "--step" in sys.argv
    debug = "--debug" in sys.argv
    check_only = "--check" in sys.argv

    if not os.path.exists(path):
        print(f"Script not found: {path}"); return

    engine = ScriptEngine(step_mode=step_mode, debug=debug)

    if check_only:
        print(f"Checking: {path}")
        errors = engine.validate(path)
        if errors:
            print(f"\n{len(errors)} error(s) found:")
            for e in errors:
                print(e)
            sys.exit(1)
        else:
            print("OK - No errors found.")
            sys.exit(0)

    result = engine.run(path)
    print(f"\n  Return code: {result.code}")
    if result.code == 0:
        print(f"  SUCCESS: {result.summary}")
    elif result.code == 1:
        print(f"  FAILED: {result.summary}")
    else:
        print(f"  DELEGATE to K3: {result.summary}")


if __name__ == "__main__":
    main()

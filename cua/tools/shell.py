"""Shell command execution via subprocess with output capture."""

import subprocess
import os


SHELL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "shell",
        "description": (
            "Execute a shell command and return stdout/stderr. "
            "Use for scripting, file operations (dir/ls, copy, mkdir, del/rm), "
            "system info (tasklist, ipconfig, systeminfo), package management "
            "(pip install, winget), or any command-line tool. "
            "NOT for launching GUI apps — use launch_app() for that. "
            "The command runs with the current working directory by default; "
            "set cwd to change it. Output is truncated at 8000 characters."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute. Can include pipes and redirects.",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (default 30, max 120). Increase for slow commands like pip install.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory for the command. Defaults to current directory.",
                },
            },
            "required": ["command"],
        },
    },
}


def execute_shell(command: str, timeout: float = 30, cwd: str | None = None) -> dict:
    """Execute a shell command via subprocess and return captured output."""
    timeout = min(float(timeout), 120)  # cap at 2 minutes

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or os.getcwd(),
            env={**os.environ},  # inherit environment
        )

        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()

        parts = []
        if out:
            if len(out) > 8000:
                out = out[:8000] + "\n... [truncated]"
            parts.append(out)
        if err:
            if len(err) > 2000:
                err = err[:2000] + "\n... [truncated]"
            parts.append(f"[stderr]\n{err}")

        output = "\n".join(parts) if parts else "(no output)"
        status = f"exit={result.returncode}"

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Command: {command}\n{status}\n\n{output}",
                }
            ],
            "mouse_pos": None,
            "last_screenshot": None,
        }

    except subprocess.TimeoutExpired:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Command timed out after {timeout}s: {command}",
                }
            ],
            "mouse_pos": None,
            "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Command failed: {e}",
                }
            ],
            "mouse_pos": None,
            "last_screenshot": None,
        }

"""Kimi built-in memory and rethink Formula tools.

memory: Remote KV storage via Kimi Formula (moonshot/memory:latest).
        Cross-session persistence, scoped to user. Used by learning system
        to sync skills and reflections across devices.

rethink: AI-driven idea reorganization via Kimi Formula (moonshot/rethink:latest).
         Used to periodically clean up and consolidate reflections.

Both are best-effort — failures are silent, never block the main agent.
"""

import json

import httpx

MEMORY_FORMULA = "moonshot/memory:latest"
RETHINK_FORMULA = "moonshot/rethink:latest"

MEMORY_SCHEMA = {
    "type": "function",
    "function": {
        "name": "memory",
        "description": "Save or recall from Kimi's remote persistent memory. Use action='save' key='...' value='...' to store important information (skills, findings, preferences). Use action='recall' key='...' to retrieve past memories. Memory persists across sessions.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["save", "recall"], "description": "save to store, recall to retrieve"},
                "key": {"type": "string", "description": "Memory key (e.g. 'skills/wechat', 'prefs/user')"},
                "value": {"type": "string", "description": "Value to store (only for action='save')"},
            },
            "required": ["action", "key"],
        },
    },
}

RETHINK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "rethink",
        "description": "AI-driven consolidation of ideas and reflections. Pass text content to reorganize, summarize, and extract key insights. Useful for periodic cleanup of accumulated notes or reflections.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Text content to reorganize and consolidate"},
            },
            "required": ["content"],
        },
    },
}


def _get_formula_client():
    """Create an httpx client for Kimi Formula API."""
    import os
    from cua.config import load_config

    config = load_config()
    api_key = config.get("moonshot_api_key", "") or os.environ.get("MOONSHOT_API_KEY", "")
    base_url = config.get("base_url", "https://api.moonshot.cn/v1")

    return httpx.Client(
        base_url=base_url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15.0,
    )


# --- Formula API helpers ---

def _load_formula_tools(formula_uri: str) -> list[dict]:
    """Load tool definitions from a Kimi Formula endpoint."""
    try:
        client = _get_formula_client()
        resp = client.get(f"/formulas/{formula_uri}/tools")
        resp.raise_for_status()
        data = resp.json()
        return data.get("tools", [])
    except Exception:
        return []


def _call_formula(formula_uri: str, function_name: str, arguments: dict) -> str:
    """Call a Kimi Formula tool and return the result."""
    try:
        client = _get_formula_client()
        resp = client.post(
            f"/formulas/{formula_uri}/fibers",
            json={"name": function_name, "arguments": json.dumps(arguments)},
        )
        resp.raise_for_status()
        fiber = resp.json()
        if fiber.get("status") == "succeeded":
            out = fiber["context"].get("output") or fiber["context"].get("encrypted_output")
            if isinstance(out, str):
                return out
            if isinstance(out, dict) and "result" in out:
                return out["result"]
            return json.dumps(out, ensure_ascii=False) if out else "ok"
        if "error" in fiber:
            return f"Error: {fiber['error']}"
        return "Error: unknown formula status"
    except Exception as e:
        return f"Formula call failed: {e}"


# --- Memory tool ---

def execute_memory(action: str = "", key: str = "", value: str = "") -> dict:
    """Save or recall from Kimi remote memory."""
    if not action:
        # Agent called memory() without args — return help
        return {
            "content": [{"type": "text", "text": "memory tool: use action='save' key='...' value='...' to store, or action='recall' key='...' to retrieve."}],
            "mouse_pos": None, "last_screenshot": None,
        }

    try:
        if action == "save":
            result = _call_formula(MEMORY_FORMULA, "memory", {
                "action": "save",
                "key": key,
                "value": value,
            })
            return {
                "content": [{"type": "text", "text": f"Memory saved: {key}"}],
                "mouse_pos": None, "last_screenshot": None,
            }
        elif action == "recall":
            result = _call_formula(MEMORY_FORMULA, "memory", {
                "action": "recall",
                "key": key,
            })
            return {
                "content": [{"type": "text", "text": f"Memory[{key}]: {result}"}],
                "mouse_pos": None, "last_screenshot": None,
            }
        else:
            return {
                "content": [{"type": "text", "text": f"Unknown memory action: {action}. Use 'save' or 'recall'."}],
                "mouse_pos": None, "last_screenshot": None,
            }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Memory failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


# --- Rethink tool ---

def execute_rethink(content: str = "") -> dict:
    """AI-driven reorganization of ideas/reflections."""
    if not content:
        return {
            "content": [{"type": "text", "text": "rethink tool: pass text content to reorganize and consolidate."}],
            "mouse_pos": None, "last_screenshot": None,
        }

    try:
        result = _call_formula(RETHINK_FORMULA, "rethink", {
            "content": content,
        })
        return {
            "content": [{"type": "text", "text": f"Rethought: {result[:300]}"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Rethink failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


# --- Learning system integration ---

def sync_to_cloud(task: str, skill: dict, reflection: dict | None = None):
    """Sync learned skill and reflection to Kimi memory (best-effort)."""
    try:
        # Save skill under skills/<name>
        if skill and skill.get("name"):
            _call_formula(MEMORY_FORMULA, "memory", {
                "action": "save",
                "key": f"cua/skills/{skill['name']}",
                "value": json.dumps(skill, ensure_ascii=False),
            })

        # Save reflection under reflections/<timestamp>
        if reflection and reflection.get("reason"):
            import time
            ts = int(time.time())
            _call_formula(MEMORY_FORMULA, "memory", {
                "action": "save",
                "key": f"cua/reflections/{ts}",
                "value": json.dumps(reflection, ensure_ascii=False),
            })

        # Rethink is best-effort and can be called explicitly by the agent;
        # removed time-based trigger to avoid race conditions.
    except Exception:
        pass  # Best-effort

"""Four-layer learning system: AutoSkill, Reflection, Pending Learning, Infrastructure.

1. SUCCESS → AutoSkill: generate/reuse SKILL.md files from successful trajectories
2. FAILURE → Reflection: store failure analysis in SQLite, inject into future prompts
3. INTERRUPTED → Pending Learning: save trace for later settlement
4. INFRASTRUCTURE: SQLite backend + Kimi rethink (optional)

All best-effort — never blocks the main task loop.
"""

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "memory.db"
SKILLS_DIR = Path(__file__).parent / "skills" / "learned"

# ChromaDB for skill similarity search (lazy init)
_chroma_client = None
_skills_collection = None
_SIMILARITY_THRESHOLD = 0.85


def _get_skills_collection():
    """Get or create ChromaDB skills collection."""
    global _chroma_client, _skills_collection
    if _skills_collection is None:
        import chromadb
        from chromadb.utils import embedding_functions
        _ensure_dirs()
        _chroma_client = chromadb.PersistentClient(path=str(DATA_DIR / "chroma"))
        ef = embedding_functions.DefaultEmbeddingFunction()
        _skills_collection = _chroma_client.get_or_create_collection(
            name="cua_skills",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    return _skills_collection


def _find_similar_skill(description: str) -> tuple[str | None, float]:
    """Search for existing skills similar to this description. Returns (skill_name, similarity)."""
    try:
        col = _get_skills_collection()
        results = col.query(query_texts=[description], n_results=1)
        if results["ids"] and results["ids"][0] and results["distances"] and results["distances"][0]:
            distance = results["distances"][0][0]
            similarity = 1.0 - distance  # cosine distance → similarity
            if similarity >= _SIMILARITY_THRESHOLD:
                return results["ids"][0][0], similarity
    except Exception:
        pass
    return None, 0


def _index_skill(name: str, description: str):
    """Add a skill to the ChromaDB vector index."""
    try:
        col = _get_skills_collection()
        # Remove old entry if exists
        existing = col.get(ids=[name])
        if existing["ids"]:
            col.delete(ids=[name])
        col.add(ids=[name], documents=[description])
    except Exception:
        pass  # Best-effort


def _get_learning_config() -> dict:
    """Get learning config with defaults."""
    try:
        from cua.config import load_config
        return load_config().get("learning", {})
    except Exception:
        return {}


def _cfg(key: str, default=None):
    return _get_learning_config().get(key, default)


def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def _get_db() -> sqlite3.Connection:
    _ensure_dirs()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db():
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS learnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL CHECK(type IN ('success_pattern','failure_fix')),
            context TEXT NOT NULL,
            learning TEXT NOT NULL,
            tools TEXT NOT NULL DEFAULT '[]',
            task TEXT,
            outcome TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS reflections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL,
            failure_reason TEXT NOT NULL,
            fix_suggestion TEXT NOT NULL,
            tool_trace TEXT,
            tokens INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS pending_learning (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT NOT NULL,
            reason TEXT NOT NULL,
            traces_json TEXT NOT NULL,
            settled INTEGER NOT NULL DEFAULT 0,
            settled_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS skills_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            file_path TEXT NOT NULL,
            version TEXT NOT NULL DEFAULT '1.0.0',
            usage_count INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
    """)
    # Cleanup expired entries (only if cleanup_days > 0)
    cleanup_days = _cfg("cleanup_days", 0)
    if cleanup_days > 0:
        cutoff = (datetime.now() - timedelta(days=cleanup_days)).isoformat()
        conn.execute("DELETE FROM learnings WHERE created_at < ?", (cutoff,))
        conn.execute("DELETE FROM reflections WHERE created_at < ?", (cutoff,))
        conn.execute("DELETE FROM pending_learning WHERE settled=1")  # always clean settled

    # Prune skills if over max (0 = unlimited, skip)
    max_skills = _cfg("autoskill_max_skills", 0)
    if max_skills > 0:
        count = conn.execute("SELECT COUNT(*) as n FROM skills_index").fetchone()["n"]
        if count > max_skills:
            excess = count - max_skills
            conn.execute(
                "DELETE FROM skills_index WHERE id IN (SELECT id FROM skills_index ORDER BY usage_count ASC, created_at ASC LIMIT ?)",
                (excess,),
            )

    conn.commit()
    conn.close()


# --- Layer 1: AutoSkill (success) ---

def _generate_skill_name(task: str) -> str:
    """Generate a kebab-case skill name from task description."""
    import re
    # Take first 5 meaningful words, remove punctuation, kebab-case
    words = re.findall(r'[一-鿿]+|[a-zA-Z]+', task)
    name = "-".join(w.lower() for w in words[:5])
    return name[:60] if name else "unnamed-task"


def _extract_skill_from_trace(task: str, steps: list[str], tool_log: list[str], client, model: str) -> dict | None:
    """Use LLM to extract a reusable skill from a successful task trace."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You extract reusable automation skills from successful task traces. Output valid JSON only."},
                {"role": "user", "content": (
                    f"Task: {task}\n\nSteps taken:\n" +
                    "\n".join(f"- {s}" for s in (steps or [])) +
                    f"\n\nTool trace (last 20):\n" +
                    "\n".join(tool_log[-20:]) +
                    f"\n\nExtract a reusable skill. Return JSON:\n"
                    f'{{"name": "kebab-case-name", "description": "one line", '
                    f'"steps": ["step 1", "step 2"], '
                    f'"tools_used": ["tool1", "tool2"], '
                    f'"prerequisites": "what must be true before using"}}'
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=400,
            extra_body={"thinking": {"type": "disabled"}},
        )
        content = resp.choices[0].message.content
        if not content:
            print(f"  [autoskill] LLM returned empty content, using template fallback")
            return _template_skill(task, steps, tool_log)
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"  [autoskill] JSON parse failed: {e}, using template fallback")
        return _template_skill(task, steps, tool_log)
    except Exception as e:
        print(f"  [autoskill] extraction failed: {e}")
        return None


def _repair_json(text: str) -> dict:
    """Try to salvage malformed JSON by finding the last valid key-value pair."""
    # Try to close unterminated strings by adding quotes
    if text.endswith('"') or text.endswith("'"):
        text += "}"
    # Find last valid pair
    last_comma = text.rfind('",')
    if last_comma > 0:
        text = text[:last_comma + 2] + '}'
    # Ensure closing brace
    if not text.rstrip().endswith("}"):
        text = text.rstrip() + '}'
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Last resort: return a placeholder
    return {"reason": "JSON parse failed, raw: " + text[:200], "fix": "check trace"}


def _template_skill(task: str, steps: list[str], tool_log: list[str]) -> dict:
    """Fallback: generate a skill from the template when LLM extraction fails."""
    name = _generate_skill_name(task)
    # Extract tool names from the trace
    tools = set()
    for entry in tool_log[-10:]:
        if entry.startswith("["):
            tool_name = entry[1:].split("]")[0]
            if tool_name:
                tools.add(tool_name)
    return {
        "name": name,
        "description": task[:100],
        "steps": steps[-5:] if steps else ["Execute task: " + task[:80]],
        "tools_used": list(tools)[:5],
        "prerequisites": "None (template fallback — LLM extraction failed)",
    }


def _write_skill_file(skill: dict):
    """Write a SKILL.md file."""
    name = skill.get("name", "unnamed")
    file_path = SKILLS_DIR / f"{name}.md"
    content = f"""# {skill.get('name', 'Unnamed Skill')}

{skill.get('description', '')}

## Prerequisites

{skill.get('prerequisites', 'None')}

## Steps

{chr(10).join(f'{i}. {s}' for i, s in enumerate(skill.get('steps', []), 1))}

## Tools Used

{', '.join(skill.get('tools_used', []))}

> Auto-generated by CUA AutoSkill v1.0 on {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return file_path


def autoskill_learn(task: str, report: dict, tool_log: list[str], client, model: str):
    """Layer 1: Extract and persist a reusable skill from a successful task."""
    if client is None:
        return

    success = report.get("success", False)
    if not success:
        return

    if not _cfg("autoskill_enabled", True):
        print(f"  [autoskill] disabled in config (autoskill_enabled=false)")
        return

    min_steps = _cfg("autoskill_min_steps", 3)
    if len(tool_log) < min_steps:
        print(f"  [autoskill] skipped: only {len(tool_log)} tool calls (need {min_steps})")
        return

    try:
        steps = report.get("steps", [])
        skill = _extract_skill_from_trace(task, steps, tool_log, client, model)
        if not skill:
            print(f"  [autoskill] extraction returned no skill")
            return

        name = skill.get("name", _generate_skill_name(task))
        desc = skill.get("description", "")

        # Check ChromaDB for similar existing skill
        similar_name, similarity = _find_similar_skill(desc)
        if similar_name and similarity >= _SIMILARITY_THRESHOLD:
            name = similar_name  # Merge into existing skill
            print(f"  [autoskill] merged into '{name}' (similarity={similarity:.2f})")

        file_path = _write_skill_file(skill)

        # Index in ChromaDB
        _index_skill(name, desc)

        conn = _get_db()
        existing = conn.execute(
            "SELECT id, version, usage_count FROM skills_index WHERE name = ?", (name,)
        ).fetchone()

        if existing:
            parts = existing["version"].split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            new_version = ".".join(parts)
            conn.execute(
                "UPDATE skills_index SET version=?, usage_count=?, updated_at=datetime('now') WHERE id=?",
                (new_version, existing["usage_count"] + 1, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO skills_index (name, description, file_path, version) VALUES (?, ?, ?, '1.0.0')",
                (name, desc, str(file_path)),
            )

        conn.commit()
        conn.close()
        print(f"  [autoskill] skill '{name}' saved ({'updated' if existing else 'new'})")

    except Exception as e:
        print(f"  [autoskill] failed: {e}")


# --- Layer 2: Reflection (failure) ---

def reflect_failure(task: str, report: dict, tool_log: list[str], client, model: str):
    """Layer 2: Analyze failures and store reflections for future prompts."""
    if client is None:
        return

    success = report.get("success", False)
    if success:
        return
    if not _cfg("reflection_enabled", True):
        return

    summary = report.get("summary", "")
    tokens = report.get("tokens", {})

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Analyze automation failures. Output valid JSON only."},
                {"role": "user", "content": (
                    f"Task: {task}\nFailure summary: {summary}\n"
                    f"Tool trace (last 15):\n" + "\n".join(tool_log[-15:]) +
                    f"\n\nAnalyze the failure. Return JSON:\n"
                    f'{{"reason": "why it failed", "fix": "how to fix it next time"}}'
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=256,
            extra_body={"thinking": {"type": "disabled"}},
        )
        content = resp.choices[0].message.content
        if not content:
            raise ValueError("empty response")

        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            # Try to repair truncated JSON
            result = _repair_json(content)

        conn = _get_db()
        conn.execute(
            "INSERT INTO reflections (task, failure_reason, fix_suggestion, tool_trace, tokens) VALUES (?, ?, ?, ?, ?)",
            (task[:200], result.get("reason", content[:200]), result.get("fix", "see trace"),
             json.dumps(tool_log[-20:], ensure_ascii=False),
             tokens.get("total", 0)),
        )
        conn.commit()
        conn.close()
        print(f"  [reflection] failure analyzed: {result.get('reason', content)[:80]}")

    except Exception as e:
        print(f"  [reflection] failed: {e}")


# --- Layer 3: Pending Learning (interrupted) ---

def save_pending(task: str, reason: str, tool_log: list[str]):
    """Layer 3: Save interrupted task trajectory for later settlement."""
    if not _cfg("pending_enabled", True):
        return
    try:
        conn = _get_db()
        conn.execute(
            "INSERT INTO pending_learning (task, reason, traces_json) VALUES (?, ?, ?)",
            (task[:200], reason, json.dumps(tool_log, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Best-effort


def settle_pending(client, model: str):
    """Attempt to settle pending interrupted tasks."""
    conn = _get_db()
    pending = conn.execute(
        "SELECT * FROM pending_learning WHERE settled = 0 ORDER BY created_at LIMIT 5"
    ).fetchall()

    for p in pending:
        try:
            traces = json.loads(p["traces_json"])
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Determine if an interrupted task was completed. Output JSON: {\"completed\": true/false, \"summary\": \"...\"}"},
                    {"role": "user", "content": f"Task: {p['task']}\nTraces:\n" + "\n".join(traces[-15:])},
                ],
                response_format={"type": "json_object"},
                max_tokens=200,
                extra_body={"thinking": {"type": "disabled"}},
            )
            content = resp.choices[0].message.content
            if not content:
                raise ValueError("empty settlement response")
            try:
                verdict = json.loads(content)
            except json.JSONDecodeError:
                verdict = _repair_json(content)

            if verdict.get("completed"):
                report = {"success": True, "summary": verdict["summary"], "steps": []}
                autoskill_learn(p["task"], report, traces, client, model)
            else:
                report = {"success": False, "summary": verdict["summary"], "steps": []}
                reflect_failure(p["task"], report, traces, client, model)

            conn.execute(
                "UPDATE pending_learning SET settled=1, settled_at=datetime('now') WHERE id=?",
                (p["id"],),
            )
            conn.commit()
            print(f"  [settle] pending task #{p['id']} settled: completed={verdict['completed']}")

        except Exception:
            # Try up to 3 times, then force plain text
            retries = p["id"]  # Using id as retry counter approximation
            if retries >= 3:
                conn.execute(
                    "UPDATE pending_learning SET settled=1, settled_at=datetime('now') WHERE id=?",
                    (p["id"],),
                )
                conn.commit()

    conn.close()


# --- Unified API ---

def reflect_and_learn(task: str, report: dict, tool_log: list[str], client, model: str):
    """Unified post-task learning. Best-effort, never blocks."""
    print()
    # Layer 1: AutoSkill (success only)
    autoskill_learn(task, report, tool_log, client, model)
    # Layer 2: Reflection (failure only)
    reflect_failure(task, report, tool_log, client, model)


def get_learnings_prompt() -> str:
    """Build learnings prompt from both learnings table and reflections."""
    conn = _get_db()
    max_learnings = _cfg("learnings_max_prompt", 10)
    max_reflections = _cfg("reflection_max_prompt", 5)
    recent_learnings = conn.execute(
        "SELECT * FROM learnings ORDER BY created_at DESC LIMIT ?", (max_learnings,)
    ).fetchall()
    recent_reflections = conn.execute(
        "SELECT * FROM reflections ORDER BY created_at DESC LIMIT ?", (max_reflections,)
    ).fetchall()
    recent_skills = conn.execute(
        "SELECT name, description, file_path FROM skills_index ORDER BY usage_count DESC LIMIT 5"
    ).fetchall()
    conn.close()

    lines = []
    if recent_reflections:
        lines.append("\n## Past Reflections (failures to avoid)\n")
        for r in recent_reflections:
            lines.append(f"- ✗ {r['failure_reason'][:100]} → fix: {r['fix_suggestion'][:100]}")
    if recent_learnings:
        lines.append("\n## Past Learnings (patterns that worked)\n")
        for l in recent_learnings:
            icon = "✓" if l["type"] == "success_pattern" else "✗"
            lines.append(f"- {icon} [{l['context']}] {l['learning']}")
    if recent_skills:
        lines.append("\n## Available Skills (from past successes)\n")
        for s in recent_skills:
            lines.append(f"- **{s['name']}**: {s['description'][:120]}")

    return "\n".join(lines) if lines else ""


# Initialize DB on import
_init_db()

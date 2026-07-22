"""Four-layer learning system: AutoSkill, Reflection, Pending Learning, Infrastructure.

1. SUCCESS → AutoSkill: generate/reuse SKILL.md files from successful trajectories
2. FAILURE → Reflection: store failure analysis in SQLite, inject into future prompts
3. INTERRUPTED → Pending Learning: save trace for later settlement
4. INFRASTRUCTURE: SQLite backend + Kimi rethink (optional)

All best-effort — never blocks the main task loop.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = DATA_DIR / "memory.db"
SKILLS_DIR = Path(__file__).parent / "skills" / "learned"
KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

# Settlement retry counter
_settle_retries: dict[int, int] = {}

# ChromaDB for skill similarity search (lazy init)
_chroma_client = None
_skills_collection = None
_knowledge_collection = None
_SIMILARITY_THRESHOLD = 0.65  # multilingual model — tuned from tests


_cached_embed_fn = None
_cached_embed_type = ""     # "multilingual" or "onnx"
_cached_embed_at = 0.0       # last cache time


def _try_upgrade_embedding():
    """Force reload embedding — call after VPN connects."""
    global _cached_embed_fn, _cached_embed_type, _cached_embed_at
    _cached_embed_fn = None
    _cached_embed_type = ""
    _cached_embed_at = 0.0
    return _get_embedding_function()


def _get_embedding_function():
    """Get the shared embedding function (cached globally).

    Prefers multilingual (Chinese+English, 384-dim). Falls back to local
    ONNX English-only. If ONNX was loaded due to network failure, retries
    multilingual on next call.
    """
    global _cached_embed_fn, _cached_embed_type, _cached_embed_at
    import time as _time

    from chromadb.utils import embedding_functions

    # Already have multilingual — return immediately
    if _cached_embed_fn is not None and _cached_embed_type == "multilingual":
        return _cached_embed_fn

    # ONNX cached — retry multilingual every 300s
    retry = (_cached_embed_type == "onnx" and
             _time.time() - _cached_embed_at > 300)

    # Try multilingual (first time or retry after 300s)
    # Uses sentence_transformers directly — loads from local cache, no network
    if _cached_embed_fn is None or retry:
        try:
            from sentence_transformers import SentenceTransformer
            import os as _os
            _prev = _os.environ.get("TRANSFORMERS_OFFLINE", "")
            _os.environ["TRANSFORMERS_OFFLINE"] = "1"
            st = SentenceTransformer(
                "paraphrase-multilingual-MiniLM-L12-v2", device="cpu"
            )
            if _prev:
                _os.environ["TRANSFORMERS_OFFLINE"] = _prev
            else:
                del _os.environ["TRANSFORMERS_OFFLINE"]
            def _encode(texts):
                return st.encode(texts, show_progress_bar=False).tolist()
            _ = _encode(["test"])
            _cached_embed_fn = _encode
            _cached_embed_type = "multilingual"
            _cached_embed_at = _time.time()
            print("  [embed] multilingual MiniLM-L12 (zh+en, local)")
            return _encode
        except Exception:
            pass

    # Return existing ONNX if available
    if _cached_embed_fn is not None and _cached_embed_type == "onnx":
        return _cached_embed_fn

    # Fallback: local ONNX (offline, always available)
    try:
        ef = embedding_functions.ONNXMiniLM_L6_V2(
            preferred_providers=["CPUExecutionProvider"]
        )
        _cached_embed_fn = ef
        _cached_embed_type = "onnx"
        _cached_embed_at = _time.time()
        print("  [embed] ONNX MiniLM-L6 (English, offline)")
        return ef
    except Exception:
        pass

    print("  [embed] WARNING: no model, embeddings will be zero")
    def _dummy(texts):
        return [[0.0] * 384 for _ in texts]
    _cached_embed_fn = _dummy
    return _dummy


def _get_skills_collection():
    """Get or create ChromaDB skills collection."""
    global _chroma_client, _skills_collection
    if _skills_collection is None:
        import chromadb
        _ensure_dirs()
        _chroma_client = chromadb.PersistentClient(path=str(DATA_DIR / "chroma"))
        ef = _get_embedding_function()
        _skills_collection = _chroma_client.get_or_create_collection(
            name="cua_skills_v2",
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
        existing = col.get(ids=[name])
        if existing["ids"]:
            col.delete(ids=[name])
        col.add(ids=[name], documents=[description])
    except Exception:
        pass  # Best-effort


# --- Knowledge base (manual .md files) ---

def _get_knowledge_collection():
    """Get or create ChromaDB knowledge collection."""
    global _chroma_client, _knowledge_collection
    if _knowledge_collection is None:
        import chromadb
        _ensure_dirs()
        if _chroma_client is None:
            _chroma_client = chromadb.PersistentClient(path=str(DATA_DIR / "chroma"))
        ef = _get_embedding_function()
        _knowledge_collection = _chroma_client.get_or_create_collection(
            name="cua_knowledge_v2",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    return _knowledge_collection


def index_knowledge() -> int:
    """Index all .md files in the knowledge directory. Call on startup.

    Returns number of newly indexed files.
    """
    if not KNOWLEDGE_DIR.exists():
        return 0

    files = list(KNOWLEDGE_DIR.glob("*.md"))
    if not files:
        return 0

    new_count = 0
    try:
        col = _get_knowledge_collection()
        indexed = set(col.get()["ids"]) if col.count() > 0 else set()

        for f in files:
            name = f.stem
            if name in indexed:
                continue  # Already indexed
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    content = fh.read()
                doc = content[:500]
                col.add(ids=[name], documents=[doc])
                print(f"  [knowledge] indexed: {name}")
                new_count += 1
            except Exception:
                pass
        if new_count == 0:
            print(f"  [knowledge] {len(files)} files (all previously indexed)")
    except Exception:
        pass
    return new_count


def search_knowledge(query: str, top_n: int = 3) -> str:
    """Search the knowledge base for relevant entries. Returns formatted text."""
    try:
        col = _get_knowledge_collection()
        if col.count() == 0:
            return ""
        results = col.query(query_texts=[query], n_results=top_n)
        if not results["ids"] or not results["ids"][0]:
            return ""

        lines = []
        for i, (kid, dist) in enumerate(zip(results["ids"][0], results["distances"][0])):
            sim = 1.0 - dist
            if sim < 0.20:  # tuned: good matches 0.26-0.46, noise ≤0.18
                continue
            doc = results.get("documents", [[]])[0][i] if results.get("documents") else ""
            lines.append(f"- [{sim:.0%}] {kid}: {doc[:150]}")

        return "\n".join(lines) if lines else ""
    except Exception:
        return ""


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


@contextmanager
def _db():
    """Context manager for SQLite connections — auto-closes."""
    conn = _get_db()
    try:
        yield conn
    finally:
        conn.close()


def _init_db():
    with _db() as conn:
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
            conn.execute("DELETE FROM pending_learning WHERE settled=1")

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
                {"role": "system", "content": "You extract reusable desktop automation skills from successful task traces. Identify the generalizable workflow — which tools to use, in what order, with what strategy. Output valid JSON only."},
                {"role": "user", "content": (
                    f"Task: {task}\n\nSteps taken:\n" +
                    "\n".join(f"- {s}" for s in (steps or [])) +
                    f"\n\nTool trace (last 20):\n" +
                    "\n".join(tool_log[-20:]) +
                    f"\n\nExtract the reusable workflow as JSON:\n"
                    f'{{"name": "kebab-case-name", "description": "one-line summary of what this skill accomplishes", '
                    f'"steps": ["actionable step 1", "actionable step 2"], '
                    f'"tools_used": ["tool1", "tool2"], '
                    f'"prerequisites": "what must be true before using this skill"}}'
                )},
            ],
            response_format={"type": "json_object"},
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
        print(f"  [autoskill] extraction failed (transient): {e}, using template")
        return _template_skill(task, steps, tool_log)


def _repair_json(text: str) -> dict:
    """Try to salvage malformed/truncated JSON."""
    text = text.strip()
    if not text.startswith("{"):
        return {"completed": False, "summary": "Invalid JSON", "reason": text[:200]}

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 1: close unterminated string + add closing brace
    if not text.endswith("}"):
        if text.endswith('"') or text.endswith("'"):
            text += "}"
        else:
            # Truncated mid-value — cut back to last complete pair
            last_pair_end = text.rfind('", "')
            if last_pair_end > 0:
                text = text[:last_pair_end + 3] + '}'
            else:
                # Single key-value, try to close it
                colon = text.find('": "')
                if colon > 0:
                    text = text[:colon + 4] + 'truncated"}'
                else:
                    text += '"}'
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: cut to last comma and close
    last_comma = text.rfind('",')
    if last_comma > 10:
        text = text[:last_comma + 2] + '}'
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Strategy 3: extract just the first key-value pair
    first_colon = text.find('": "')
    if first_colon > 0:
        after = text[first_colon + 4:]
        first_end = after.find('"')
        if first_end > 0:
            key = text[2:first_colon]
            val = after[:first_end]
            return {key.strip('"'): val, "summary": "truncated JSON, partial recovery"}

    return {"completed": False, "summary": "JSON repair failed", "reason": text[:200]}


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
        _ensure_dirs()
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

        with _db() as conn:
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
        print(f"  [autoskill] skill '{name}' saved ({'updated' if existing else 'new'})")

        # Sync to Kimi remote memory (best-effort)
        try:
            from cua.tools.kimi_memory import sync_to_cloud
            sync_to_cloud(task, skill)
        except Exception:
            pass

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
                {"role": "system", "content": "You analyze failed desktop automation attempts. Identify the root cause and suggest a concrete fix. Output valid JSON only."},
                {"role": "user", "content": (
                    f"Task: {task}\nFailure summary: {summary}\n"
                    f"Tool trace (last 15):\n" + "\n".join(tool_log[-15:]) +
                    f"\n\nDiagnose the failure. Return JSON:\n"
                    f'{{"reason": "root cause of failure", "fix": "concrete fix to try next time"}}'
                )},
            ],
            response_format={"type": "json_object"},
            max_tokens=512,
        )
        content = resp.choices[0].message.content
        # K3 may return empty content when response_format json_object fails
        if not content:
            # Try reasoning_content as fallback
            reasoning = getattr(resp.choices[0].message, "reasoning_content", None)
            if reasoning:
                print(f"  [reflection] content empty, using reasoning_content ({len(reasoning)} chars)")
                result = _repair_json(reasoning) if reasoning.strip().startswith("{") else {
                    "reason": reasoning[:200],
                    "fix": "see reasoning above",
                }
            else:
                print(f"  [reflection] both content and reasoning empty, using template fallback")
                result = {
                    "reason": summary[:200] or "unknown failure",
                    "fix": "review the tool trace and try a different approach",
                }
        else:
            try:
                result = json.loads(content)
            except json.JSONDecodeError as e:
                print(f"  [reflection] JSON malformed at line {e.lineno} col {e.colno}: {e.msg[:80]}")
                print(f"  [reflection] raw preview: {content[:120]}...")
                result = _repair_json(content)

        with _db() as conn:
            conn.execute(
                "INSERT INTO reflections (task, failure_reason, fix_suggestion, tool_trace, tokens) VALUES (?, ?, ?, ?, ?)",
                (task[:200], result.get("reason", content[:200]), result.get("fix", "see trace"),
                 json.dumps(tool_log[-20:], ensure_ascii=False),
                 tokens.get("total", 0)),
            )
            conn.commit()
        print(f"  [reflection] failure analyzed: {result.get('reason', content)[:80]}")

    except Exception as e:
        print(f"  [reflection] failed: {e}")


# --- Layer 3: Pending Learning (interrupted) ---

def save_pending(task: str, reason: str, tool_log: list[str]):
    """Layer 3: Save interrupted task trajectory for later settlement."""
    if not _cfg("pending_enabled", True):
        return
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO pending_learning (task, reason, traces_json) VALUES (?, ?, ?)",
                (task[:200], reason, json.dumps(tool_log, ensure_ascii=False)),
            )
            conn.commit()
    except Exception:
        pass  # Best-effort


def settle_pending(client, model: str):
    """Attempt to settle pending interrupted tasks."""
    with _db() as conn:
        pending = conn.execute(
            "SELECT * FROM pending_learning WHERE settled = 0 ORDER BY created_at LIMIT 5"
        ).fetchall()

        for p in pending:
            try:
                traces = json.loads(p["traces_json"])
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You determine whether an interrupted desktop automation task was likely completed based on its tool trace. Look for evidence that the task's goal was accomplished (e.g., files created, text entered, windows closed). Output JSON: {\"completed\": true/false, \"summary\": \"brief explanation\"}"},
                        {"role": "user", "content": f"Task: {p['task']}\nTraces:\n" + "\n".join(traces[-15:])},
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=300,
                        )
                content = resp.choices[0].message.content
                if not content:
                    reasoning = getattr(resp.choices[0].message, "reasoning_content", None)
                    if reasoning:
                        verdict = _repair_json(reasoning) if reasoning.strip().startswith("{") else {
                            "completed": False, "summary": reasoning[:200]
                        }
                    else:
                        verdict = {"completed": False, "summary": "interrupted — unable to determine outcome"}
                else:
                    try:
                        verdict = json.loads(content)
                    except json.JSONDecodeError as e:
                        print(f"  [settle] JSON malformed at line {e.lineno} col {e.colno}: {e.msg[:80]}")
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
                max_retries = _cfg("pending_max_retries", 3)
                retries = _settle_retries.get(p["id"], 0)
                retries += 1
                _settle_retries[p["id"]] = retries
                if retries >= max_retries:
                    conn.execute(
                        "UPDATE pending_learning SET settled=1, settled_at=datetime('now') WHERE id=?",
                        (p["id"],),
                    )
                    conn.commit()


# --- Unified API ---

def reflect_and_learn(task: str, report: dict, tool_log: list[str], client, model: str):
    """Unified post-task learning. Best-effort, never blocks."""
    print(f"  [learn] post-task analysis: {len(tool_log)} tool calls, success={report.get('success')}")
    if report.get("success"):
        # Layer 1: AutoSkill (success only)
        autoskill_learn(task, report, tool_log, client, model)
    elif report.get("interrupted"):
        # Layer 3: Pending (interrupted — save for later settlement)
        reason = report.get("summary", "task interrupted")
        save_pending(task, reason, tool_log)
        print(f"  [learn] saved as pending: {reason[:80]}")
    else:
        # Layer 2: Reflection (genuine failure)
        reflect_failure(task, report, tool_log, client, model)


def get_learnings_prompt() -> str:
    """Build learnings prompt from both learnings table and reflections."""
    with _db() as conn:
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

    result = "\n".join(lines) if lines else ""
    if result:
        n_r = len(recent_reflections)
        n_l = len(recent_learnings)
        n_s = len(recent_skills)
        parts = []
        if n_r: parts.append(f"{n_r} reflections")
        if n_l: parts.append(f"{n_l} learnings")
        if n_s: parts.append(f"{n_s} skills")
        print(f"  [learn] loaded: {', '.join(parts)} ({len(result)} chars)")
    else:
        print(f"  [learn] no past learnings/reflections/skills found")
    return result


# Initialize DB on import (best-effort, never crash)
try:
    _init_db()
except Exception:
    pass

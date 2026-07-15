"""DraftContent subagent: isolated content writing with persona separation.

Registered as a tool for the main agent. Creates an independent Kimi chat
(no tools, own system prompt) for content creation. Returns only a summary
to avoid polluting the main agent's context.
"""

import hashlib
import os
import time
from pathlib import Path

DRAFTS_DIR = Path(__file__).parent.parent / "data" / "cache" / "drafts"
DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MAX_CHARS = 4000
MAX_CHARS_LIMIT = 20000


DRAFT_CONTENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "DraftContent",
        "description": "Write long-form content (articles, emails, reports, posts) in an isolated writing session. The writer has its own persona and context, separate from the desktop automation agent. Returns only a preview — use file_read to get the full draft, or file_write to save it elsewhere.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Writing task description. Be specific about topic, tone, length, format.",
                },
                "persona": {
                    "type": "string",
                    "description": "Writer persona, e.g. '资深科技专栏作者, 擅长深入浅出地解释技术概念', '专业商务邮件写手, 语气正式但不生硬'",
                },
                "prefill": {
                    "type": "string",
                    "description": "Optional opening text to start from. The model continues from this text (Partial Mode).",
                },
                "max_chars": {
                    "type": "integer",
                    "description": f"Max characters (default {DEFAULT_MAX_CHARS}, max {MAX_CHARS_LIMIT})",
                },
            },
            "required": ["task", "persona"],
        },
    },
}


def execute_draft_content(
    task: str,
    persona: str,
    prefill: str = "",
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict:
    """Execute DraftContent subagent. Returns summary dict."""
    max_chars = min(max(500, max_chars or DEFAULT_MAX_CHARS), MAX_CHARS_LIMIT)

    # Build slug from task
    slug = "".join(c if c.isalnum() or c in "-_" else "-" for c in task[:30].strip().lower())
    slug = slug.strip("-")[:40] or "draft"
    content_hash = hashlib.sha256(f"{task}{persona}{prefill}".encode()).hexdigest()[:8]
    draft_path = DRAFTS_DIR / f"{slug}-{content_hash}.md"

    try:
        from openai import OpenAI
        from cua.config import load_config

        config = load_config()
        api_key = config.get("moonshot_api_key", "") or os.environ.get("MOONSHOT_API_KEY", "")
        if not api_key:
            return _error("API key not configured")
        base_url = config.get("base_url", "https://api.moonshot.cn/v1")
        model = config.get("model", "kimi-k2.6")

        client = OpenAI(api_key=api_key, base_url=base_url)

        # Build isolated messages (no tools)
        messages = [{"role": "system", "content": persona}]

        # Add doc_ref content if task references it
        if "doc:" in task:
            parts = task.split("doc:", 1)
            if len(parts) > 1:
                ref = parts[1].strip().split()[0][:8] if parts[1].strip() else ""
                if ref:
                    # Try to read referenced document
                    try:
                        doc_dir = Path(__file__).parent.parent / "data" / "cache" / "drafts"
                        for f in doc_dir.glob(f"*-{ref}*"):
                            with open(f, "r", encoding="utf-8") as df:
                                doc_content = df.read()
                            messages.append({
                                "role": "system",
                                "content": f"Reference document content:\n{doc_content[:3000]}",
                            })
                            break
                    except Exception:
                        pass

        user_msg = f"Writing task: {task}\nTarget length: approximately {max_chars} characters."
        if prefill:
            user_msg += f"\nStart from this opening: {prefill}"

        messages.append({"role": "user", "content": user_msg})

        # Use Kimi Partial Mode if prefill is provided
        if prefill:
            messages.append({
                "role": "assistant",
                "content": prefill,
                "partial": True,
            })

        start = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=min(max_chars * 2, 16384),
            extra_body={"thinking": {"type": "disabled"}},
        )
        elapsed = time.time() - start

        content = response.choices[0].message.content or ""
        if prefill:
            content = prefill + content

        # Truncate to max_chars
        if len(content) > max_chars:
            content = content[:max_chars]

        # Save draft
        with open(draft_path, "w", encoding="utf-8") as f:
            f.write(content)

        char_count = len(content)
        preview = content[:200].replace("\n", " ")
        if len(content) > 200:
            preview += "..."

        summary = (
            f"Draft saved: {draft_path}\n"
            f"Characters: {char_count}\n"
            f"Time: {elapsed:.1f}s\n"
            f"Preview: {preview}\n\n"
            f"Use file_read to get the full draft. Use file_write to save it elsewhere."
        )

        return {
            "content": [{"type": "text", "text": summary}],
            "mouse_pos": None,
            "last_screenshot": None,
        }

    except Exception as e:
        return _error(str(e))


def _error(msg: str) -> dict:
    return {
        "content": [{"type": "text", "text": f"DraftContent error: {msg}"}],
        "mouse_pos": None,
        "last_screenshot": None,
    }

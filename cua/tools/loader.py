"""Tool group definitions and ChromaDB similarity search.

With K3's 1M context + auto-caching, all tools are always sent to the model.
The tool groups below are kept for reference and documentation purposes only.
"""

# --- Tool group definitions (reference) ---

BASE_TOOLS = [
    "screenshot", "set_mouse", "click", "drag", "scroll",
    "type_keys", "magnifier", "ocr",
    "paste_text", "read_clipboard",
    "think", "note", "wait",
    "file_read", "file_write",
    "finish", "request_human_help",
    "$web_search",
]

WEB_TOOLS = [
    "web_navigate", "web_get_content", "web_click", "web_type",
    "web_new_tab", "web_switch_tab", "web_close_tab",
    "web_refresh", "web_back", "web_forward",
    "web_list_tabs", "web_press", "web_scroll",
]

UIA_TOOLS = [
    "uia_inspect", "uia_click", "uia_set_value", "uia_get_text",
    "run_command",
]

WINDOWS_TOOLS = [
    "list_windows", "focus_window", "launch_app",
]

CONTENT_TOOLS = [
    "memory", "rethink",
    "DraftContent",
    "GenerateImage",
]

DOCUMENT_TOOLS = [
    "ReadDocument",
    "ListDocuments",
    "DeleteDocument",
    "CleanupDocuments",
]


# --- ChromaDB similarity search ---

def _search_similar(task_summary: str, top_n: int = 5) -> str:
    """Search ChromaDB for similar past skills/learnings. Returns formatted prompt snippet."""
    try:
        from cua.learning import _get_skills_collection
        col = _get_skills_collection()
        results = col.query(query_texts=[task_summary], n_results=top_n)
        if not results["ids"] or not results["ids"][0]:
            return ""

        lines = []
        for i, (sid, dist) in enumerate(zip(results["ids"][0], results["distances"][0])):
            sim = 1.0 - dist  # cosine distance → similarity
            if sim < 0.22:  # tuned: skills need higher confidence than knowledge
                continue
            doc = results.get("documents", [[]])[0][i] if results.get("documents") else ""
            lines.append(f"- [{sim:.0%}] {doc[:150]}")

        if lines:
            print(f"  [memory] found {len(lines)} relevant past skill(s)")
            return "\n".join(lines)
        else:
            print(f"  [memory] no similar skills found")
    except Exception:
        pass
    return ""

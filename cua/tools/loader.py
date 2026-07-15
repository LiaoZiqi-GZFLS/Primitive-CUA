"""Dynamic tool loader: classify task with LLM and load only relevant tools."""

# --- Tool group definitions ---

BASE_TOOLS = [
    "screenshot", "set_mouse", "click", "drag",
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
    "DraftContent",             # content writing subagent
    "GenerateImage",            # SVG image generation subagent
]

DOCUMENT_TOOLS = [
    "ReadDocument",             # upload + extract via Kimi Files API
    "ListDocuments",            # list uploaded files
    "DeleteDocument",           # delete single file
    "CleanupDocuments",         # clean up all files
]


# --- LLM classification ---

CLASSIFY_PROMPT = """Classify this desktop automation task. Which tool groups are needed?

Task: {task}

Categories:
- web: browsers, websites, search, login, forms, shopping, online content
- uia: Office apps (Word/Excel/PPT), Notepad, native Windows dialogs/controls
- content: writing articles/emails/reports/posts, generating images/icons/illustrations
- document: reading/extracting PDF/DOCX files, OCR, managing uploaded documents
- windows: desktop window management (always loaded)

Return JSON with: needs_web (bool), needs_uia (bool), needs_content (bool), needs_document (bool), reasoning (string, brief), summary (string, a 1-sentence task summary in ENGLISH for vector search against stored skills)."""


def _classify_llm(task: str, client, model: str) -> dict:
    """Use LLM with json_schema to classify the task."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You classify desktop automation tasks. Output valid JSON only."},
                {"role": "user", "content": CLASSIFY_PROMPT.format(task=task)},
            ],
            response_format={"type": "json_object"},
            max_tokens=200,
            extra_body={"thinking": {"type": "disabled"}},
        )
        import json
        result = json.loads(resp.choices[0].message.content)
        return {
            "needs_web": result.get("needs_web", False),
            "needs_uia": result.get("needs_uia", False),
            "needs_content": result.get("needs_content", False),
            "needs_document": result.get("needs_document", False),
            "needs_windows": True,
            "reasoning": result.get("reasoning", ""),
            "summary": result.get("summary", task[:80]),
        }
    except Exception as e:
        print(f"  [loader] LLM classification failed ({e}), falling back to keyword match")
        return None


# --- Keyword fallback ---

WEB_KEYWORDS = [
    "网页", "浏览器", "搜索", "百度", "谷歌", "google", "baidu",
    "登录", "注册", "填表", "下单", "购物", "新闻", "网站",
    "url", "http", "www", ".com", ".cn", ".org",
    "browser", "chrome", "edge", "firefox",
    "下载页面", "在线", "网页版",
]

UIA_KEYWORDS = [
    "word", "excel", "ppt", "powerpoint", "outlook",
    "office", "文档", "表格", "幻灯片", "演示",
    "记事本", "notepad",
    "对话框", "控件", "菜单栏", "工具栏",
    "另存为", "保存为", "导出", "打印",
    "设置", "控制面板", "属性",
    "visual studio", "vscode", "vs code",
    "原生", "桌面应用", "程序窗口",
]

CONTENT_KEYWORDS = [
    "写", "文章", "邮件", "报告", "文案", "总结",
    "生成", "画", "图", "图标", "插画", "示意图",
    "draft", "write", "article", "email", "image", "icon",
    "创作", "写作", "编写", "撰写",
]

DOCUMENT_KEYWORDS = [
    "pdf", "docx", "文档", "文件", "读取", "导入",
    "read", "extract", "document", "file",
    "ocr", "识别", "提取",
]


def _classify_keywords(task: str) -> dict:
    """Keyword-based classification fallback."""
    task_lower = task.lower()
    return {
        "needs_web": any(kw in task_lower for kw in WEB_KEYWORDS),
        "needs_uia": any(kw in task_lower for kw in UIA_KEYWORDS),
        "needs_content": any(kw in task_lower for kw in CONTENT_KEYWORDS),
        "needs_document": any(kw in task_lower for kw in DOCUMENT_KEYWORDS),
        "needs_windows": True,
        "reasoning": "keyword match",
        "summary": task[:80],  # keyword fallback uses raw task
    }


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
            if sim < 0.5:  # skip weak matches
                continue
            doc = results.get("documents", [[]])[0][i] if results.get("documents") else ""
            lines.append(f"- [{sim:.0%}] {doc[:150]}")

        if lines:
            return "\n".join(lines)
    except Exception:
        pass
    return ""


# --- Main API ---

def build_tools(task: str, client=None, model: str = "kimi-k2.6"):
    """Build the tools list based on task classification."""
    c = None
    if client is not None:
        c = _classify_llm(task, client, model)

    if c is None:
        c = _classify_keywords(task)

    # Search ChromaDB for similar past learnings
    task_summary = c.get("summary", task[:80])
    similar = _search_similar(task_summary)
    if similar:
        count = similar.count("- [")
        print(f"  [memory] found {count} relevant past skill(s) for: {task_summary[:60]}")

    tool_names = list(BASE_TOOLS)
    tool_names.extend(WINDOWS_TOOLS)

    if c.get("needs_web"):
        tool_names.extend(WEB_TOOLS)
    if c.get("needs_uia"):
        tool_names.extend(UIA_TOOLS)
    if c.get("needs_content"):
        tool_names.extend(CONTENT_TOOLS)
    if c.get("needs_document"):
        tool_names.extend(DOCUMENT_TOOLS)

    info_parts = [f"Base+Windows({len(BASE_TOOLS) + len(WINDOWS_TOOLS)})"]
    if c.get("needs_web"):
        info_parts.append(f"Web({len(WEB_TOOLS)})")
    if c.get("needs_uia"):
        info_parts.append(f"UIA({len(UIA_TOOLS)})")
    if c.get("needs_content"):
        info_parts.append(f"Content({len(CONTENT_TOOLS)})")
    if c.get("needs_document"):
        info_parts.append(f"Document({len(DOCUMENT_TOOLS)})")

    info = " + ".join(info_parts) + f" [{c.get('reasoning', '')}]"
    c["similar"] = similar
    return tool_names, info, c

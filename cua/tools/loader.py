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
]

WINDOWS_TOOLS = [
    "list_windows", "focus_window", "launch_app",
]

# --- LLM classification ---

CLASSIFY_PROMPT = """Classify this desktop automation task. Which tools are needed?

Task: {task}

Categories:
- web: tasks involving browsers, websites, search, login, forms, shopping, online content
- uia: tasks involving Office apps (Word/Excel/PPT), Notepad, native Windows dialogs, controls, menus
- windows: desktop window management (always true for non-trivial desktop tasks)

Return JSON with: needs_web (bool), needs_uia (bool), reasoning (string, brief)."""


def _classify_llm(task: str, client, model: str) -> dict:
    """Use LLM with json_schema to classify the task."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You classify desktop automation tasks. Output valid JSON only."},
                {"role": "user", "content": CLASSIFY_PROMPT.format(task=task)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "task_classification",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "needs_web": {"type": "boolean"},
                            "needs_uia": {"type": "boolean"},
                            "reasoning": {"type": "string"},
                        },
                        "required": ["needs_web", "needs_uia", "reasoning"],
                        "additionalProperties": False,
                    },
                },
            },
            max_tokens=200,
            extra_body={"thinking": {"type": "disabled"}},
        )
        import json
        result = json.loads(resp.choices[0].message.content)
        return {
            "needs_web": result.get("needs_web", False),
            "needs_uia": result.get("needs_uia", False),
            "needs_windows": True,
            "reasoning": result.get("reasoning", ""),
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


def _classify_keywords(task: str) -> dict:
    """Keyword-based classification fallback."""
    task_lower = task.lower()
    return {
        "needs_web": any(kw in task_lower for kw in WEB_KEYWORDS),
        "needs_uia": any(kw in task_lower for kw in UIA_KEYWORDS),
        "needs_windows": True,
        "reasoning": "keyword match",
    }


# --- Main API ---

def build_tools(task: str, client=None, model: str = "kimi-k2.6"):
    """Build the tools list based on task classification.

    Args:
        task: User's task description
        client: OpenAI client (for LLM classification). If None, uses keyword fallback.
        model: Model name for classification

    Returns:
        (tool_names_list, info_string, classification_dict)
    """
    # Try LLM classification first
    c = None
    if client is not None:
        c = _classify_llm(task, client, model)

    if c is None:
        c = _classify_keywords(task)

    tool_names = list(BASE_TOOLS)
    tool_names.extend(WINDOWS_TOOLS)

    if c["needs_web"]:
        tool_names.extend(WEB_TOOLS)
    if c["needs_uia"]:
        tool_names.extend(UIA_TOOLS)

    info_parts = [f"Base+Windows({len(BASE_TOOLS) + len(WINDOWS_TOOLS)})"]
    if c["needs_web"]:
        info_parts.append(f"Web({len(WEB_TOOLS)})")
    if c["needs_uia"]:
        info_parts.append(f"UIA({len(UIA_TOOLS)})")

    info = " + ".join(info_parts) + f" [{c.get('reasoning', '')}]"
    return tool_names, info, c

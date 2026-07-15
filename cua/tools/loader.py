"""Dynamic tool loader: classify task and load only relevant tools to save tokens."""

# --- Tool group definitions ---

BASE_TOOLS = [
    "screenshot",       # screen capture
    "set_mouse",        # cursor positioning
    "click",            # mouse click
    "drag",             # mouse drag
    "type_keys",        # keyboard input
    "magnifier",        # zoom inspect
    "ocr",              # text recognition
    "paste_text",       # clipboard paste
    "read_clipboard",   # clipboard read
    "think",            # reflection
    "note",             # notepad
    "wait",             # delay
    "file_read",        # file I/O
    "file_write",       # file I/O
    "finish",           # task end
    "request_human_help",  # human assistance
    "$web_search",      # Kimi built-in search
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


# --- Classification keywords ---

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
    "记事本", "notepad", "写字板", "wordpad",
    "对话框", "控件", "窗口", "菜单栏", "工具栏",
    "另存为", "保存为", "导出", "打印",
    "设置", "控制面板", "属性",
    "visual studio", "vscode", "vs code",
    "原生", "桌面应用", "程序窗口",
]


def classify_task(task: str) -> dict[str, bool]:
    """Classify a task to determine which tool groups are needed.

    Returns dict with keys: needs_web, needs_uia, needs_windows
    """
    task_lower = task.lower()

    needs_web = any(kw in task_lower for kw in WEB_KEYWORDS)
    needs_uia = any(kw in task_lower for kw in UIA_KEYWORDS)

    # Windows tools are almost always useful for desktop tasks
    needs_windows = True

    return {
        "needs_web": needs_web,
        "needs_uia": needs_uia,
        "needs_windows": needs_windows,
    }


def build_tools(task: str):
    """Build the tools list based on task classification.

    Returns (tools_list, classification_info_string)
    """
    c = classify_task(task)

    tool_names = list(BASE_TOOLS)
    tool_names.extend(WINDOWS_TOOLS)  # windows tools always loaded

    if c["needs_web"]:
        tool_names.extend(WEB_TOOLS)

    if c["needs_uia"]:
        tool_names.extend(UIA_TOOLS)

    info_parts = [f"Base+Windows({len(BASE_TOOLS) + len(WINDOWS_TOOLS)})"]
    if c["needs_web"]:
        info_parts.append(f"Web({len(WEB_TOOLS)})")
    if c["needs_uia"]:
        info_parts.append(f"UIA({len(UIA_TOOLS)})")

    return tool_names, " + ".join(info_parts), c

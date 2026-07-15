"""Web tools using Playwright: navigate, get_content, click, type."""
import time

from cua.tools.screenshot import _np_to_png_b64
from cua.overlay import draw_cursor


# Module-level browser state — lazy init, reused across calls
_browser = None
_page = None


def _get_page():
    """Get or create the Playwright page (lazy init)."""
    global _browser, _page
    from playwright.sync_api import sync_playwright

    if _browser is None:
        pw = sync_playwright().start()
        _browser = pw.chromium.launch(headless=False)
        _page = _browser.new_page()
    return _page


# --- Schemas ---

WEB_NAVIGATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_navigate",
        "description": "Open a URL in the Playwright-controlled browser. Use this to visit web pages.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to navigate to (e.g. 'https://www.baidu.com')"}
            },
            "required": ["url"],
        },
    },
}


WEB_GET_CONTENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_get_content",
        "description": "Get the text content of the current page: title, URL, headings, paragraphs, buttons, links, and input fields. Use this to understand what's on the page without OCR.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


WEB_CLICK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_click",
        "description": "Click an element on the web page by its visible text. Uses Playwright's text locator for reliable clicking (no coordinate guessing).",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The visible text of the element to click (e.g. '登录', 'Search', 'Submit')"}
            },
            "required": ["text"],
        },
    },
}


WEB_TYPE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_type",
        "description": "Type text into an input field on the web page. Finds the input by placeholder text, label, or nearby text.",
        "parameters": {
            "type": "object",
            "properties": {
                "label": {"type": "string", "description": "Placeholder text, label, or nearby text to identify the input field (e.g. '用户名', 'Search', 'Email')"},
                "text": {"type": "string", "description": "Text to type into the field"},
            },
            "required": ["label", "text"],
        },
    },
}


# --- Executors ---

def execute_web_navigate(url: str) -> dict:
    """Navigate to a URL."""
    try:
        page = _get_page()
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        title = page.title()
        return {
            "content": [
                {"type": "text", "text": f"Navigated to: {url}\nPage title: {title}"}
            ],
            "mouse_pos": None,
            "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Navigation failed: {e}"}],
            "mouse_pos": None,
            "last_screenshot": None,
        }


def execute_web_get_content() -> dict:
    """Extract page content."""
    try:
        page = _get_page()
        title = page.title()
        url = page.url

        # Extract structured content via JS
        content = page.evaluate("""() => {
            const result = { headings: [], buttons: [], links: [], inputs: [], paragraphs: [] };

            document.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(el => {
                const t = el.textContent.trim();
                if (t) result.headings.push({tag: el.tagName, text: t.slice(0, 80)});
            });

            document.querySelectorAll('button, [role="button"]').forEach(el => {
                const t = el.textContent.trim();
                if (t) result.buttons.push(t.slice(0, 60));
            });

            document.querySelectorAll('a').forEach(el => {
                const t = el.textContent.trim();
                if (t) result.links.push({text: t.slice(0, 60), href: el.href?.slice(0, 120) || ''});
            });

            document.querySelectorAll('input:not([type="hidden"]), textarea, [contenteditable="true"]').forEach(el => {
                result.inputs.push({
                    type: el.type || 'textarea',
                    placeholder: (el.placeholder || '').slice(0, 40),
                    name: (el.name || '').slice(0, 40),
                    id: (el.id || '').slice(0, 40),
                });
            });

            document.querySelectorAll('p, span, div').forEach(el => {
                if (el.children.length === 0) {
                    const t = el.textContent.trim();
                    if (t && t.length > 20 && t.length < 500) result.paragraphs.push(t.slice(0, 200));
                }
            });

            return result;
        }""")

        # Format
        lines = [f"URL: {url}", f"Title: {title}", ""]
        if content.get("headings"):
            lines.append("--- Headings ---")
            for h in content["headings"][:20]:
                lines.append(f"  {h['tag']}: {h['text']}")
        if content.get("buttons"):
            lines.append("--- Buttons ---")
            for b in content["buttons"][:20]:
                lines.append(f"  [{b}]")
        if content.get("inputs"):
            lines.append("--- Inputs ---")
            for inp in content["inputs"][:15]:
                lines.append(f"  [{inp['type']}] placeholder='{inp['placeholder']}' name='{inp['name']}'")
        if content.get("links"):
            lines.append("--- Links ---")
            for l in content["links"][:20]:
                lines.append(f"  [{l['text']}] -> {l['href']}")
        if content.get("paragraphs"):
            lines.append("--- Text ---")
            for p in content["paragraphs"][:5]:
                lines.append(f"  {p}")

        return {
            "content": [{"type": "text", "text": "\n".join(lines)}],
            "mouse_pos": None,
            "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Content extraction failed: {e}"}],
            "mouse_pos": None,
            "last_screenshot": None,
        }


def execute_web_click(text: str) -> dict:
    """Click an element by visible text."""
    try:
        page = _get_page()
        page.get_by_text(text, exact=False).first.click(timeout=5000)
        time.sleep(0.5)
        return {
            "content": [
                {"type": "text", "text": f"Clicked: {text}"}
            ],
            "mouse_pos": None,
            "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Click failed: {e}. Try web_get_content to see available elements."}],
            "mouse_pos": None,
            "last_screenshot": None,
        }


def execute_web_type(label: str, text: str) -> dict:
    """Type into an input field."""
    try:
        page = _get_page()
        # Try placeholder first, then label, then name/id
        inp = (
            page.get_by_placeholder(label).first
            or page.get_by_label(label).first
            or page.locator(f'[name="{label}"]').first
            or page.locator(f'#{label}').first
        )
        inp.fill(text)
        time.sleep(0.2)
        return {
            "content": [
                {"type": "text", "text": f"Typed '{text}' into field '{label}'"}
            ],
            "mouse_pos": None,
            "last_screenshot": None,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Type failed: {e}. Try web_get_content to see available inputs."}],
            "mouse_pos": None,
            "last_screenshot": None,
        }


# --- Browser navigation tools ---

WEB_NEW_TAB_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_new_tab",
        "description": "Open a new browser tab and switch to it.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


WEB_SWITCH_TAB_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_switch_tab",
        "description": "Switch to a browser tab by index (1-based). Use web_list_tabs first to see available tabs.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer", "description": "Tab index to switch to (1-based)"},
            },
            "required": ["index"],
        },
    },
}


WEB_CLOSE_TAB_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_close_tab",
        "description": "Close the current browser tab. If it's the last tab, the browser window closes.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


WEB_REFRESH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_refresh",
        "description": "Refresh/reload the current page.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


WEB_BACK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_back",
        "description": "Go back to the previous page in browser history.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


WEB_FORWARD_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_forward",
        "description": "Go forward to the next page in browser history.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


WEB_LIST_TABS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_list_tabs",
        "description": "List all open browser tabs with their titles and URLs.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def execute_web_new_tab() -> dict:
    try:
        from playwright.sync_api import sync_playwright
        page = _get_page()
        ctx = page.context
        new_page = ctx.new_page()
        global _page
        _page = new_page
        return {
            "content": [{"type": "text", "text": "Opened new tab."}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {"content": [{"type": "text", "text": f"New tab failed: {e}"}], "mouse_pos": None, "last_screenshot": None}


def execute_web_switch_tab(index: int) -> dict:
    try:
        page = _get_page()
        pages = page.context.pages
        if index < 1 or index > len(pages):
            return {
                "content": [{"type": "text", "text": f"Tab {index} out of range. {len(pages)} tabs available."}],
                "mouse_pos": None, "last_screenshot": None,
            }
        global _page
        _page = pages[index - 1]
        _page.bring_to_front()
        return {
            "content": [{"type": "text", "text": f"Switched to tab {index}/{len(pages)}: {_page.title()}"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Switch tab failed: {e}"}], "mouse_pos": None, "last_screenshot": None}


def execute_web_close_tab() -> dict:
    try:
        page = _get_page()
        pages = page.context.pages
        if len(pages) <= 1:
            return {
                "content": [{"type": "text", "text": "Last tab — closing it will close the browser. Use web_navigate to open a URL first if you want to keep browsing."}],
                "mouse_pos": None, "last_screenshot": None,
            }
        page.close()
        global _page
        _page = page.context.pages[-1]
        return {
            "content": [{"type": "text", "text": f"Tab closed. Now on: {_page.title()}"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Close tab failed: {e}"}], "mouse_pos": None, "last_screenshot": None}


def execute_web_refresh() -> dict:
    try:
        page = _get_page()
        page.reload(wait_until="domcontentloaded")
        return {
            "content": [{"type": "text", "text": f"Page refreshed: {page.title()}"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Refresh failed: {e}"}], "mouse_pos": None, "last_screenshot": None}


def execute_web_back() -> dict:
    try:
        page = _get_page()
        page.go_back(wait_until="domcontentloaded")
        return {
            "content": [{"type": "text", "text": f"Back to: {page.title()} ({page.url[:80]})"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Back failed: {e}"}], "mouse_pos": None, "last_screenshot": None}


def execute_web_forward() -> dict:
    try:
        page = _get_page()
        page.go_forward(wait_until="domcontentloaded")
        return {
            "content": [{"type": "text", "text": f"Forward to: {page.title()} ({page.url[:80]})"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Forward failed: {e}"}], "mouse_pos": None, "last_screenshot": None}


def execute_web_list_tabs() -> dict:
    try:
        page = _get_page()
        pages = page.context.pages
        tabs = []
        for i, p in enumerate(pages, 1):
            tabs.append(f"  [{i}] {p.title()[:60]} — {p.url[:80]}")
        return {
            "content": [{"type": "text", "text": f"{len(pages)} tabs open:\n" + "\n".join(tabs)}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {"content": [{"type": "text", "text": f"List tabs failed: {e}"}], "mouse_pos": None, "last_screenshot": None}


# --- Keyboard + scroll ---

WEB_PRESS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_press",
        "description": "Press a keyboard key on the web page. Use 'Enter' to submit forms, 'Escape' to close dialogs, 'Tab' to move focus, 'ArrowDown/Up' to navigate dropdowns, 'PageDown/Up' to scroll.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key name: Enter, Escape, Tab, ArrowDown, ArrowUp, ArrowLeft, ArrowRight, PageDown, PageUp, Home, End, Backspace, Delete, Space"},
            },
            "required": ["key"],
        },
    },
}


WEB_SCROLL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_scroll",
        "description": "Scroll the web page up or down. Positive = scroll down, negative = scroll up.",
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {"type": "integer", "description": "Pixels to scroll. Positive=down, negative=up. Use 500 for a typical page-down."},
            },
            "required": ["amount"],
        },
    },
}


def execute_web_press(key: str) -> dict:
    try:
        page = _get_page()
        page.keyboard.press(key)
        return {
            "content": [{"type": "text", "text": f"Pressed: {key}"}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Press failed: {e}"}], "mouse_pos": None, "last_screenshot": None}


def execute_web_scroll(amount: int) -> dict:
    try:
        page = _get_page()
        page.evaluate("(a) => window.scrollBy(0, a)", amount)
        return {
            "content": [{"type": "text", "text": f"Scrolled {amount}px {'down' if amount > 0 else 'up'}."}],
            "mouse_pos": None, "last_screenshot": None,
        }
    except Exception as e:
        return {"content": [{"type": "text", "text": f"Scroll failed: {e}"}], "mouse_pos": None, "last_screenshot": None}

WEB_NAVIGATE_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

WEB_CLICK_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

WEB_TYPE_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

WEB_NEW_TAB_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

WEB_SWITCH_TAB_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

WEB_CLOSE_TAB_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

WEB_REFRESH_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

WEB_BACK_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

WEB_FORWARD_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

WEB_PRESS_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

WEB_SCROLL_SCHEMA["function"]["parameters"]["properties"]["verify"] = {'type': 'boolean', 'description': 'Auto-verify and think after action? Default true. Set false for rapid multi-step sequences.'}

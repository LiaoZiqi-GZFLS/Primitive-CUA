"""Web tools using Playwright: navigate, get_content, click, type."""
import time

from cua.tools.screenshot import _np_to_jpeg_b64
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

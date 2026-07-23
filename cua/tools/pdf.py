"""Generate PDF reports via fpdf2 — lightweight, pure Python, no system deps."""

import os
from pathlib import Path


PDF_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_pdf",
        "description": (
            "Generate a styled PDF report. Use after completing a task to produce "
            "a summary document. Supports basic markdown: # heading, ## subheading, "
            "- bullet, numbered items, and plain paragraphs. "
            "Chinese text is fully supported. "
            "Returns the path to the generated PDF file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Document title — appears as large heading on first page.",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Report content in plain text. Use # for top-level headings, "
                        "## for sub-headings, - for bullet points. "
                        "Separate paragraphs with blank lines. "
                        "Keep under 10000 characters for best results."
                    ),
                },
                "filename": {
                    "type": "string",
                    "description": "Output filename (e.g., 'report.pdf'). Defaults to 'report_<timestamp>.pdf' in the Documents folder.",
                },
            },
            "required": ["title", "content"],
        },
    },
}


def execute_generate_pdf(title: str, content: str, filename: str = "") -> dict:
    """Generate a PDF report and return the file path."""
    from fpdf import FPDF
    import time

    # Determine output path
    if not filename:
        ts = int(time.time())
        filename = f"report_{ts}.pdf"
    if not filename.endswith(".pdf"):
        filename += ".pdf"

    out_dir = Path(os.path.expanduser("~")) / "Documents" / "CUA_Reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename

    # Find a CJK font (use system fonts on Windows)
    font_path = _find_cjk_font()
    if not font_path:
        return {
            "content": [{"type": "text", "text": (
                "Error: No CJK font found. On Windows, ensure 'C:\\Windows\\Fonts\\msyh.ttc' "
                "or 'C:\\Windows\\Fonts\\simsun.ttc' exists. "
                "Install fpdf2 and try again."
            )}],
            "mouse_pos": None, "last_screenshot": None,
        }

    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        # Register CJK font
        pdf.add_font("CJK", "", font_path, uni=True)
        pdf.add_font("CJK", "B", font_path, uni=True)

        # ── Title ──
        pdf.set_font("CJK", "B", 18)
        pdf.multi_cell(0, 10, title, align="C")
        pdf.ln(4)

        # Separator line
        pdf.set_draw_color(150)
        y = pdf.get_y()
        pdf.line(15, y, pdf.w - 15, y)
        pdf.ln(6)

        # ── Content ──
        pdf.set_font("CJK", "", 11)
        for block in content.split("\n\n"):
            block = block.strip()
            if not block:
                continue

            lines = block.split("\n")
            first = lines[0]

            # Heading detection
            if first.startswith("# "):
                pdf.set_font("CJK", "B", 14)
                pdf.ln(2)
                pdf.cell(0, 8, first[2:])
                pdf.ln(8)
                pdf.set_font("CJK", "", 11)
                continue

            if first.startswith("## "):
                pdf.set_font("CJK", "B", 12)
                pdf.ln(2)
                pdf.cell(0, 7, first[2:])
                pdf.ln(7)
                pdf.set_font("CJK", "", 11)
                continue

            # Bullet list
            if first.startswith("- ") or first.startswith("* "):
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("- ") or stripped.startswith("* "):
                        pdf.set_x(20)
                        pdf.cell(4, 6, chr(8226))  # bullet
                        pdf.multi_cell(0, 6, stripped[2:])
                pdf.ln(2)
                continue

            # Numbered list (1. 2. etc.)
            if first[0].isdigit() and ". " in first[:4]:
                for line in lines:
                    pdf.set_x(20)
                    pdf.multi_cell(0, 6, line.strip())
                pdf.ln(2)
                continue

            # Regular paragraph
            for line in lines:
                pdf.multi_cell(0, 6, line)
            pdf.ln(2)

        # ── Footer ──
        pdf.ln(4)
        pdf.set_draw_color(200)
        y = pdf.get_y()
        pdf.line(15, y, pdf.w - 15, y)
        pdf.ln(4)
        pdf.set_font("CJK", "", 8)
        import datetime
        pdf.cell(0, 5, f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}  |  CUA Agent Report", align="C")

        pdf.output(str(out_path))
        return {
            "content": [{"type": "text", "text": f"PDF report generated: {out_path} ({os.path.getsize(out_path)} bytes)"}],
            "mouse_pos": None, "last_screenshot": None,
        }

    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"PDF generation failed: {e}"}],
            "mouse_pos": None, "last_screenshot": None,
        }


def _find_cjk_font() -> str | None:
    """Locate a CJK-capable font file on the system."""
    import sys

    candidates = []

    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", "C:\\Windows")
        candidates = [
            os.path.join(windir, "Fonts", "msyh.ttc"),   # Microsoft YaHei
            os.path.join(windir, "Fonts", "msyhbd.ttc"), # Microsoft YaHei Bold
            os.path.join(windir, "Fonts", "simsun.ttc"),  # SimSun
            os.path.join(windir, "Fonts", "simhei.ttf"),  # SimHei
            os.path.join(windir, "Fonts", "simkai.ttf"),  # KaiTi
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        ]

    for path in candidates:
        if os.path.exists(path):
            return path
    return None

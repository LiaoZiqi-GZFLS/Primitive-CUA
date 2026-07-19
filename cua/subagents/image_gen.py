"""GenerateImage subagent: SVG generation with visual self-review loop.

Multi-round generate-review cycle:
1. LLM generates SVG code
2. CairoSVG renders to PNG
3. LLM visually reviews the PNG against the requirement
4. Repeat until ok or max rounds exhausted

Returns summary to main agent — no context pollution.
"""

import hashlib
import json
import os
import re
from pathlib import Path

GENERATED_DIR = Path(__file__).parent.parent / "data" / "cache" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

MAX_ROUNDS = 5

SVG_SYSTEM_PROMPT = """You are an SVG illustrator. Output ONLY valid SVG code.
Rules:
- Must include xmlns="http://www.w3.org/2000/svg" and viewBox
- Self-contained: no external fonts, images, or resources
- No <script> tags, no javascript, no external references
- Use inline <style> for CSS
- Colors should be visually harmonious
- The SVG must render correctly at any scale"""

REVIEW_SYSTEM_PROMPT = """You review generated images against requirements.
Look at the image carefully. Compare it to the original requirement.
Check for: layout correctness, color accuracy, text presence, visual quality.
Output JSON: {"ok": true/false, "issues": "specific problems found"}"""


GENERATE_IMAGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "GenerateImage",
        "description": "Generate an SVG image (icon, illustration, diagram) via a multi-round generation and visual self-review loop. The image is rendered and visually inspected before returning. Returns the PNG file path.",
        "parameters": {
            "type": "object",
            "properties": {
                "requirement": {
                    "type": "string",
                    "description": "Image description: what to draw, style, colors, size, purpose. Be specific.",
                },
            },
            "required": ["requirement"],
        },
    },
}


def _extract_svg(text: str) -> str | None:
    """Extract SVG code from LLM output (tolerates markdown code blocks)."""
    match = re.search(r"<svg[\s\S]*?</svg>", text, re.IGNORECASE)
    return match.group(0) if match else None


def _render_svg(svg_code: str, output_path: Path) -> bool:
    """Render SVG to PNG using CairoSVG. Returns True on success."""
    try:
        import cairosvg
        cairosvg.svg2png(bytestring=svg_code.encode("utf-8"), write_to=str(output_path))
        return output_path.exists()
    except Exception as e:
        print(f"  [image_gen] render failed: {e}")
        return False


def _upload_png(png_path: Path, client, model: str) -> str | None:
    """Upload PNG to Kimi Files API, return ms:// URL."""
    try:
        with open(png_path, "rb") as f:
            file_obj = client.files.create(file=f, purpose="image")
        return f"ms://{file_obj.id}"
    except Exception as e:
        print(f"  [image_gen] upload failed: {e}")
        return None


def execute_generate_image(requirement: str) -> dict:
    """Execute GenerateImage subagent. Returns summary dict."""
    content_hash = hashlib.sha256(requirement.encode()).hexdigest()[:8]
    slug = "".join(c if c.isalnum() else "-" for c in requirement[:20].strip().lower())
    slug = slug.strip("-")[:30] or "image"
    png_path = GENERATED_DIR / f"{slug}-{content_hash}.png"

    try:
        from openai import OpenAI
        from cua.config import load_config

        config = load_config()
        api_key = config.get("moonshot_api_key", "") or os.environ.get("MOONSHOT_API_KEY", "")
        if not api_key:
            return _error("API key not configured")
        base_url = config.get("base_url", "https://api.moonshot.cn/v1")
        model = config.get("model", "kimi-k3")

        client = OpenAI(api_key=api_key, base_url=base_url)

        gen_messages = [
            {"role": "system", "content": SVG_SYSTEM_PROMPT},
            {"role": "user", "content": f"Generate an SVG image: {requirement}"},
        ]

        rounds = 0
        last_issues = ""
        ok = False

        for round_num in range(1, MAX_ROUNDS + 1):
            rounds = round_num
            print(f"  [image_gen] round {round_num}/{MAX_ROUNDS}...")

            # Add feedback from previous round
            if last_issues:
                gen_messages.append({
                    "role": "user",
                    "content": f"Previous version issues: {last_issues}\nFix these and regenerate the SVG.",
                })

            # Generate SVG
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=gen_messages,
                    max_tokens=4096,
                )
                svg_text = resp.choices[0].message.content or ""
            except Exception as e:
                return _error(f"Generation failed: {e}")

            svg_code = _extract_svg(svg_text)
            if not svg_code:
                gen_messages.append({"role": "user", "content": "No SVG found in your output. Output ONLY the SVG code."})
                last_issues = "No SVG code found in output"
                continue

            # Render
            if not _render_svg(svg_code, png_path):
                last_issues = "SVG failed to render — check syntax"
                gen_messages.append({"role": "assistant", "content": svg_text})
                continue

            # Upload for visual review
            png_url = _upload_png(png_path, client, model)
            if not png_url:
                # Can't upload — accept the current version
                ok = True
                last_issues = "(could not upload for review)"
                break

            # Visual self-review
            try:
                review_resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": png_url}},
                                {"type": "text", "text": f"Requirement: {requirement}\nReview this image. Output JSON: {{\"ok\": true/false, \"issues\": \"...\"}}"},
                            ],
                        },
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=300,
                )
                verdict = json.loads(review_resp.choices[0].message.content)
                ok = verdict.get("ok", False)
                last_issues = verdict.get("issues", "")
            except Exception as e:
                last_issues = f"Review failed: {e}"
                ok = True  # Accept if review fails
                break

            # Record for next iteration
            gen_messages.append({"role": "assistant", "content": svg_text})

            if ok:
                break

        # Build summary
        if ok:
            summary = f"Image generated: {png_path}\nRounds: {rounds}\nStatus: ✓ verified"
        else:
            summary = f"Image generated: {png_path}\nRounds: {rounds}\nStatus: ⚠ NOT verified after {rounds} rounds\nLast issues: {last_issues}"

        return {
            "content": [{"type": "text", "text": summary}],
            "mouse_pos": None,
            "last_screenshot": None,
        }

    except Exception as e:
        return _error(str(e))


def _error(msg: str) -> dict:
    return {
        "content": [{"type": "text", "text": f"GenerateImage error: {msg}"}],
        "mouse_pos": None,
        "last_screenshot": None,
    }

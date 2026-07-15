"""Full-screen screenshot tool using mss."""
import io
import base64
from typing import Any

import numpy as np
from PIL import Image

from cua.overlay import draw_cursor


def _np_to_jpeg_b64(img: np.ndarray, quality: int = 85) -> str:
    """Convert numpy array (RGBA or RGB) to base64 JPEG data URI."""
    if img.shape[-1] == 4:
        img = img[..., :3]
    pil_img = Image.fromarray(img, "RGB")
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _annotated_screenshot(
    original: np.ndarray, px: int, py: int, scale: float
) -> np.ndarray:
    """Return annotated copy of screenshot."""
    return draw_cursor(original, px, py, scale)


def _run_ocr(img: np.ndarray) -> str:
    """Run RapidOCR on the screenshot, return text blocks as bracketed format."""
    from rapidocr_onnxruntime import RapidOCR

    if img.shape[-1] == 4:
        img_rgb = img[..., [2, 1, 0]]  # BGRA → RGB
    else:
        img_rgb = img

    engine = RapidOCR()
    result, _ = engine(img_rgb)

    if not result:
        return "[no text detected]"

    blocks = []
    for item in result:
        text = item[1]
        blocks.append(f"[{text}]")

    return " ".join(blocks)


SCREENSHOT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "screenshot",
        "description": "Take a full-screen screenshot. Returns the original image, an annotated version with the virtual mouse cursor, and OCR-extracted text from the screen.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def execute_screenshot(
    sct: Any, mouse_pos: tuple[float, float], screen_w: int, screen_h: int
) -> dict:
    """Take a screenshot and return original + annotated as base64 JPEG + OCR text."""
    # Capture
    monitor = sct.monitors[1]
    img = np.array(sct.grab(monitor))  # BGRA, (H, W, 4)

    px = round(mouse_pos[0] * screen_w)
    py = round(mouse_pos[1] * screen_h)

    annotated = _annotated_screenshot(img, px, py, scale=1.0)

    original_rgb = img[..., [2, 1, 0]]
    annotated_rgb = annotated[..., [2, 1, 0]]

    original_b64 = _np_to_jpeg_b64(original_rgb)
    annotated_b64 = _np_to_jpeg_b64(annotated_rgb)

    # Run OCR on the screenshot
    ocr_text = _run_ocr(img)

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": original_b64}},
            {"type": "image_url", "image_url": {"url": annotated_b64}},
            {
                "type": "text",
                "text": (
                    f"Screen: {screen_w}x{screen_h}. "
                    f"Virtual mouse: ({mouse_pos[0]:.4f}, {mouse_pos[1]:.4f})\n"
                    f"OCR text: {ocr_text}"
                ),
            },
        ],
        "last_screenshot": img,
    }

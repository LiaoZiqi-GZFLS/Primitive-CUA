"""Full-screen screenshot tool using mss."""
import io
import base64
from typing import Any

import numpy as np
from PIL import Image

from cua.overlay import draw_cursor


def _downscale(img: np.ndarray, screen_w: int, screen_h: int) -> tuple[np.ndarray, float]:
    """Tiered downscaling to reduce VLM token consumption.

    Scaling strategy:
    - 1080p (≤1920) → keep original
    - 2K (≤2560)     → target 1080p
    - 4K (≤4096)     → target 2K
    - 4K+             → target 4K

    Returns (resized_image, scale_factor).
    """
    max_dim = max(screen_w, screen_h)
    if max_dim <= 1920:
        target_w, target_h = screen_w, screen_h  # 1080p — keep
    elif max_dim <= 2560:
        # 2K → 1080p
        scale = 1920 / max_dim
        target_w, target_h = int(screen_w * scale), int(screen_h * scale)
    elif max_dim <= 4096:
        # 4K → 2K
        scale = 2560 / max_dim
        target_w, target_h = int(screen_w * scale), int(screen_h * scale)
    else:
        # 4K+ → 4K
        scale = 3840 / max_dim
        target_w, target_h = int(screen_w * scale), int(screen_h * scale)

    factor = screen_w / target_w

    h, w = img.shape[:2]
    pil = Image.fromarray(img[..., [2, 1, 0, 3]] if img.shape[-1] == 4 else img)
    pil = pil.resize((target_w, target_h), Image.LANCZOS)
    result = np.array(pil)
    if img.shape[-1] == 4:
        result = result[..., [2, 1, 0, 3]]  # RGBA → BGRA
    return result, float(factor)


def downsample_for_vlm(img: np.ndarray, mouse_pos: tuple[float, float], screen_w: int, screen_h: int):
    """Downscale image and compute overlay pixel coords. Used by all image tools.

    Returns (img_scaled, px, py) where (px, py) are cursor coords in the downscaled image.
    """
    scaled_img, factor = _downscale(img, screen_w, screen_h)
    sh, sw = scaled_img.shape[:2]
    px = round(mouse_pos[0] * sw)
    py = round(mouse_pos[1] * sh)
    return scaled_img, px, py


def _np_to_png_b64(img: np.ndarray) -> str:
    """Convert numpy array (RGB) to base64 PNG data URI."""
    if img.shape[-1] == 4:
        img = img[..., :3]
    pil_img = Image.fromarray(img, "RGB")
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _annotated_screenshot(
    original: np.ndarray, px: int, py: int, scale: float
) -> np.ndarray:
    """Return annotated copy of screenshot."""
    return draw_cursor(original, px, py, scale)


_ocr_engine = None


def _get_ocr_engine():
    """Get or create a shared RapidOCR engine with GPU preference."""
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    # Patch RapidOCR to support DML before creating the engine
    from cua.ocr_patch import _patched_init  # noqa: F401
    from rapidocr_onnxruntime import RapidOCR
    _ocr_engine = RapidOCR()
    return _ocr_engine


def _run_ocr(img: np.ndarray, screen_w: int, screen_h: int) -> str:
    """Run RapidOCR on the screenshot, return text blocks with normalized coordinates."""
    engine = _get_ocr_engine()

    if img.shape[-1] == 4:
        img_rgb = img[..., [2, 1, 0]]
    else:
        img_rgb = img

    result, _ = _ocr_engine(img_rgb)

    if not result:
        return "[no text detected]"

    blocks = []
    for item in result:
        text = item[1]
        bbox = item[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        center_x = (bbox[0][0] + bbox[2][0]) / 2 / screen_w
        center_y = (bbox[0][1] + bbox[2][1]) / 2 / screen_h
        blocks.append(f"[{text}] ({center_x:.4f}, {center_y:.4f})")

    return " ".join(blocks)


SCREENSHOT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "screenshot",
        "description": "Take a full-screen screenshot. Returns the original image, an annotated version with the virtual mouse cursor, and OCR-extracted text from the screen.",
        "parameters": {
            "type": "object",
            "properties": {
                "delay": {
                    "type": "number",
                    "description": "Seconds to wait before taking the screenshot (0-5, default 0). Use after clicking/launching to let the UI settle before capturing.",
                },
            },
            "required": [],
        },
    },
}


def execute_screenshot(
    sct: Any, mouse_pos: tuple[float, float], screen_w: int, screen_h: int,
    delay: float = 0.0,
) -> dict:
    """Take a screenshot and return original + annotated as base64 PNG + OCR text."""
    if delay > 0:
        import time
        time.sleep(min(delay, 5.0))
    # Capture full-res for OCR/magnifier
    monitor = sct.monitors[1]
    img = np.array(sct.grab(monitor))  # BGRA, (H, W, 4)

    # Tiered downscaling for VLM images
    scaled_img, _ = _downscale(img, screen_w, screen_h)
    scaled_h, scaled_w = scaled_img.shape[:2]

    px = round(mouse_pos[0] * scaled_w)
    py = round(mouse_pos[1] * scaled_h)

    annotated = _annotated_screenshot(scaled_img, px, py, scale=1.0)

    original_rgb = scaled_img[..., [2, 1, 0]]
    annotated_rgb = annotated[..., [2, 1, 0]]

    original_b64 = _np_to_png_b64(original_rgb)
    annotated_b64 = _np_to_png_b64(annotated_rgb)

    # Run OCR on FULL-RES image (not downscaled)
    ocr_text = _run_ocr(img, screen_w, screen_h)

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": original_b64}},
            {"type": "image_url", "image_url": {"url": annotated_b64}},
            {
                "type": "text",
                "text": (
                    f"Screen: {scaled_w}x{scaled_h} (from {screen_w}x{screen_h}). "
                    f"Virtual mouse: ({mouse_pos[0]:.4f}, {mouse_pos[1]:.4f})\n"
                    f"OCR text: {ocr_text}"
                ),
            },
        ],
        "last_screenshot": img,
    }

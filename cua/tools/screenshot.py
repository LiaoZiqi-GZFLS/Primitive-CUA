"""Full-screen screenshot tool using mss."""
import io
import base64
from typing import Any

import numpy as np
from PIL import Image

from cua.overlay import draw_cursor


def _np_to_jpeg_b64(img: np.ndarray, quality: int = 85) -> str:
    """Convert numpy array (RGBA or RGB) to base64 JPEG data URI."""
    # Remove alpha if present for JPEG
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


SCREENSHOT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "screenshot",
        "description": "Take a full-screen screenshot. Returns the original image and an annotated version with the virtual mouse cursor position marked.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def execute_screenshot(
    sct: Any, mouse_pos: tuple[float, float], screen_w: int, screen_h: int
) -> dict:
    """Take a screenshot and return original + annotated as base64 JPEG."""
    import mss as _mss

    # Capture
    monitor = sct.monitors[1]
    img = np.array(sct.grab(monitor))  # BGRA, (H, W, 4)

    px = round(mouse_pos[0] * screen_w)
    py = round(mouse_pos[1] * screen_h)

    annotated = _annotated_screenshot(img, px, py, scale=1.0)

    # Both img and annotated are BGRA. Convert to RGB for JPEG.
    original_rgb = img[..., [2, 1, 0]]  # BGRA -> RGB (drop alpha)
    annotated_rgb = annotated[..., [2, 1, 0]]  # BGRA -> RGB (drop alpha)

    original_b64 = _np_to_jpeg_b64(original_rgb)
    annotated_b64 = _np_to_jpeg_b64(annotated_rgb)

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": original_b64}},
            {"type": "image_url", "image_url": {"url": annotated_b64}},
            {
                "type": "text",
                "text": (
                    f"Screen: {screen_w}x{screen_h}. "
                    f"Virtual mouse: ({mouse_pos[0]:.4f}, {mouse_pos[1]:.4f})"
                ),
            },
        ],
        "last_screenshot": img,
    }

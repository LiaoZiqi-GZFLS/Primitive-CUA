"""Magnifier tool: square crop centered on virtual mouse."""
import numpy as np
from cua.overlay import draw_cursor
from cua.tools.screenshot import _np_to_jpeg_b64


MAGNIFIER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "magnifier",
        "description": "Take a square crop of the screen centered on the current virtual mouse position. The crop side length equals half the shorter screen dimension. Returns the original crop and an annotated version with a proportionally scaled cursor marker. Use this to see fine details near the cursor.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def execute_magnifier(
    sct,
    mouse_pos: tuple[float, float],
    screen_w: int,
    screen_h: int,
    last_screenshot: np.ndarray,
) -> dict:
    """Crop a square around the virtual mouse, with proportional overlay."""
    px = round(mouse_pos[0] * screen_w)
    py = round(mouse_pos[1] * screen_h)
    crop_side = min(screen_w, screen_h) // 2
    scale = crop_side / min(screen_w, screen_h)

    # Compute crop bounds (clamped to image edges)
    half = crop_side // 2
    left = max(0, min(screen_w - crop_side, px - half))
    top = max(0, min(screen_h - crop_side, py - half))

    # Crop from the last screenshot (BGRA)
    crop = last_screenshot[top : top + crop_side, left : left + crop_side].copy()

    # Local cursor position within the crop
    local_px = px - left
    local_py = py - top

    annotated_crop = draw_cursor(crop, local_px, local_py, scale=scale)

    # Convert BGRA → RGB for JPEG
    crop_rgb = crop[..., [2, 1, 0]]
    annotated_rgb = annotated_crop[..., [2, 1, 0]]

    return {
        "content": [
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(crop_rgb)}},
            {"type": "image_url", "image_url": {"url": _np_to_jpeg_b64(annotated_rgb)}},
            {
                "type": "text",
                "text": (
                    f"Magnifier: {crop_side}x{crop_side} crop at "
                    f"({mouse_pos[0]:.4f}, {mouse_pos[1]:.4f}), "
                    f"scale={scale:.2f}"
                ),
            },
        ],
        "mouse_pos": mouse_pos,
        "last_screenshot": last_screenshot,
    }

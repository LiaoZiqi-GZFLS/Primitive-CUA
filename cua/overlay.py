"""Draw virtual mouse cursor overlay on screenshots."""
import numpy as np
from PIL import Image, ImageDraw


def draw_cursor(
    image: np.ndarray,
    px: int,
    py: int,
    scale: float = 1.0,
) -> np.ndarray:
    """Draw virtual mouse cursor on a screenshot.

    Draws a red crosshair (full image) + red circle with white border at (px, py).
    Returns a NEW array (does not mutate input).

    Args:
        image: BGRA numpy array from mss (H, W, 4)
        px, py: Pixel position of cursor center
        scale: Size multiplier for magnifier mode

    Returns:
        RGBA numpy array with overlay drawn
    """
    h, w = image.shape[:2]

    # Convert BGRA (mss format) to RGBA for Pillow
    img_rgba = image[..., [2, 1, 0, 3]]
    pil_img = Image.fromarray(img_rgba, "RGBA")
    draw = ImageDraw.Draw(pil_img)

    # Line and circle sizes
    line_width = max(1, int(2 * scale))
    outer_radius = int(18 * scale)
    inner_radius = int(15 * scale)
    outer_width = max(1, int(4 * scale))
    inner_width = max(1, int(3 * scale))

    red = (231, 76, 60, 255)  # #e74c3c
    white = (255, 255, 255, 255)

    # Full-image crosshair
    draw.line([(0, py), (w, py)], fill=red, width=line_width)
    draw.line([(px, 0), (px, h)], fill=red, width=line_width)

    # White outer ring
    draw.ellipse(
        [px - outer_radius, py - outer_radius, px + outer_radius, py + outer_radius],
        outline=white,
        width=outer_width,
    )

    # Red inner circle (no fill)
    draw.ellipse(
        [px - inner_radius, py - inner_radius, px + inner_radius, py + inner_radius],
        outline=red,
        width=inner_width,
    )

    return np.array(pil_img)

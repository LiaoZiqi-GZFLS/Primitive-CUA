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
    scale = max(0.1, scale)
    h, w = image.shape[:2]

    if image.shape[2] != 4:
        raise ValueError(f"Expected 4-channel BGRA image, got {image.shape[2]} channels")

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

    # Colors with alpha for translucency
    crosshair_color = (231, 76, 60, 100)   # semi-transparent red for crosshair
    circle_fill = (231, 76, 60, 50)         # very transparent red fill
    circle_outline = (231, 76, 60, 200)     # slightly transparent red outline
    ring_color = (255, 255, 255, 180)       # semi-transparent white outer ring

    # Full-image crosshair (semi-transparent)
    draw.line([(0, py), (w, py)], fill=crosshair_color, width=line_width)
    draw.line([(px, 0), (px, h)], fill=crosshair_color, width=line_width)

    # White outer ring
    draw.ellipse(
        [px - outer_radius, py - outer_radius, px + outer_radius, py + outer_radius],
        outline=ring_color,
        width=outer_width,
    )

    # Red inner circle (semi-transparent fill + outline)
    draw.ellipse(
        [px - inner_radius, py - inner_radius, px + inner_radius, py + inner_radius],
        fill=circle_fill,
        outline=circle_outline,
        width=inner_width,
    )

    # Convert RGBA back to BGRA for mss compatibility
    result = np.array(pil_img)
    return result[..., [2, 1, 0, 3]]  # RGBA → BGRA

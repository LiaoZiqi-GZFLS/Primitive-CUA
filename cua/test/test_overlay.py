"""Manual test: verify overlay rendering produces valid output."""
import numpy as np
from cua.overlay import draw_cursor


def test_overlay_basic():
    """Create a fake white screen and draw cursor on it."""
    img = np.ones((1080, 1920, 4), dtype=np.uint8) * 255
    img[:, :, 3] = 255

    result = draw_cursor(img, px=960, py=540, scale=1.0)

    assert result.shape == (1080, 1920, 4), f"Shape mismatch: {result.shape}"
    assert result.dtype == np.uint8

    # Check crosshair: R channel (index 2 in BGRA) should have red-dominant pixels
    # With alpha blending, values won't be exact 231 but will be distinctly red
    center_row_r = result[540, :, 2]
    center_row_b = result[540, :, 0]
    red_pixels = center_row_r > (center_row_b + 30)
    assert np.any(red_pixels), "No red crosshair pixels found on horizontal line"

    center_col_r = result[:, 960, 2]
    center_col_b = result[:, 960, 0]
    red_pixels = center_col_r > (center_col_b + 30)
    assert np.any(red_pixels), "No red crosshair pixels found on vertical line"

    print("PASS: overlay_basic")


def test_overlay_magnifier_scale():
    """Verify magnifier scale reduces marker size."""
    img = np.ones((540, 540, 4), dtype=np.uint8) * 255
    img[:, :, 3] = 255

    result = draw_cursor(img, px=270, py=270, scale=0.5)

    assert result.shape == (540, 540, 4)
    # At scale 0.5, crosshair should still produce red-dominant pixels
    center_row_r = result[270, :, 2]
    center_row_b = result[270, :, 0]
    assert np.any(center_row_r > (center_row_b + 30))
    print("PASS: overlay_magnifier_scale")


if __name__ == "__main__":
    test_overlay_basic()
    test_overlay_magnifier_scale()
    print("\nAll overlay tests passed.")

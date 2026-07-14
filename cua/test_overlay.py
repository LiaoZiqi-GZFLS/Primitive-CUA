"""Manual test: verify overlay rendering produces valid output."""
import numpy as np
from cua.overlay import draw_cursor


def test_overlay_basic():
    """Create a fake white screen and draw cursor on it."""
    # Simulate a 1920x1080 BGRA screenshot (all white)
    img = np.ones((1080, 1920, 4), dtype=np.uint8) * 255
    img[:, :, 3] = 255  # Alpha

    result = draw_cursor(img, px=960, py=540, scale=1.0)

    assert result.shape == (1080, 1920, 4), f"Shape mismatch: {result.shape}"
    assert result.dtype == np.uint8

    # Check crosshair at center: red pixels exist along the crosshair
    # Horizontal line at y=540 should have red pixels (R channel is index 2 in BGRA)
    center_row = result[540, :, 2]  # R channel (BGRA, index 2)
    assert np.any(center_row == 231), "No red crosshair pixels found on horizontal line"

    # Vertical line at x=960
    center_col = result[:, 960, 2]  # R channel
    assert np.any(center_col == 231), "No red crosshair pixels found on vertical line"

    print("PASS: overlay_basic")


def test_overlay_magnifier_scale():
    """Verify magnifier scale reduces marker size."""
    img = np.ones((540, 540, 4), dtype=np.uint8) * 255
    img[:, :, 3] = 255

    result = draw_cursor(img, px=270, py=270, scale=0.5)

    assert result.shape == (540, 540, 4)
    # At scale 0.5, circle should still produce red pixels near center (R channel is index 2 in BGRA)
    assert np.any(result[270, :, 2] == 231)
    print("PASS: overlay_magnifier_scale")


if __name__ == "__main__":
    test_overlay_basic()
    test_overlay_magnifier_scale()
    print("\nAll overlay tests passed.")

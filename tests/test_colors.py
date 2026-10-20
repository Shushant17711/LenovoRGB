from __future__ import annotations

import pytest

from lenovorgb import colors


def test_parse_hex_variants():
    assert colors.parse_hex("#ff0000") == (255, 0, 0)
    assert colors.parse_hex("00ff00") == (0, 255, 0)
    assert colors.parse_hex("#0f0") == (0, 255, 0)
    assert colors.parse_hex("nope", default=(1, 2, 3)) == (1, 2, 3)
    assert colors.parse_hex(None, default=(4, 5, 6)) == (4, 5, 6)  # type: ignore[arg-type]


def test_to_hex_round_trip():
    assert colors.to_hex((255, 128, 0)) == "#ff8000"
    assert colors.to_hex((300, -5, 12)) == "#ff000c"


def test_as_color_clamps():
    assert colors.as_color((-10, 0, 300)) == (0, 0, 255)
    assert colors.as_color((127.9, 0.5, 254)) == (127, 0, 254)


def test_hsv_primary_colors():
    assert colors.hsv(0.0) == (255, 0, 0)
    assert colors.hsv(1.0 / 3.0) == (0, 255, 0)
    assert colors.hsv(2.0 / 3.0) == (0, 0, 255)
    assert colors.hsv(0.0, 0.0, 0.0) == (0, 0, 0)


def test_rgb_hsv_round_trip():
    hue, saturation, value = colors.rgb_to_hsv((255, 0, 0))
    assert hue == pytest.approx(0.0)
    assert saturation == pytest.approx(1.0)
    assert value == pytest.approx(1.0)


def test_normalize_frame_pads_and_truncates():
    padded = colors.normalize_frame([(10, 20, 30)])
    assert len(padded) == 4
    assert padded[0] == (10, 20, 30)
    assert padded[3] == (0, 0, 0)

    truncated = colors.normalize_frame([(1, 1, 1)] * 9)
    assert len(truncated) == 4


def test_normalize_frame_brightness():
    frame = colors.normalize_frame([(200, 100, 50)] * 4, brightness=50)
    assert frame[0] == (100, 50, 25)
    dark = colors.normalize_frame([(255, 255, 255)] * 4, brightness=0)
    assert dark == [(0, 0, 0)] * 4


def test_lerp_and_scale():
    assert colors.lerp((0, 0, 0), (100, 200, 300), 0.5) == (50, 100, 150)
    assert colors.lerp((0, 0, 0), (10, 10, 10), 5.0) == (10, 10, 10)
    assert colors.scale((255, 100, 10), 0.5) == (127, 50, 5)


def test_is_black():
    assert colors.is_black([(0, 0, 0)] * 4)
    assert not colors.is_black([(0, 0, 1)] * 4)

from __future__ import annotations

import numpy as np

from lenovorgb.modes.screen import compute_zone_colors


def solid(height: int, width: int, color) -> np.ndarray:
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[:, :] = color
    return image


def test_black_screen_is_black():
    colors = compute_zone_colors(solid(80, 320, (0, 0, 0)))
    assert colors == [(0, 0, 0)] * 4


def test_pure_red_screen_is_red():
    colors = compute_zone_colors(solid(80, 320, (255, 0, 0)))
    for red, green, blue in colors:
        assert red > 200
        assert green < 40
        assert blue < 40


def test_half_red_half_blue_maps_left_to_right():
    image = np.zeros((80, 400, 3), dtype=np.uint8)
    image[:, :200] = (255, 0, 0)
    image[:, 200:] = (0, 0, 255)
    colors = compute_zone_colors(image)
    assert colors[0][0] > colors[0][2]
    assert colors[1][0] > colors[1][2]
    assert colors[2][2] > colors[2][0]
    assert colors[3][2] > colors[3][0]


def test_grayscale_is_dim_and_cool():
    colors = compute_zone_colors(solid(80, 320, (130, 130, 130)))
    for red, green, blue in colors:
        assert max(red, green, blue) < 120
        assert blue >= red


def test_dark_noise_is_not_a_white_glow():
    rng = np.random.default_rng(0)
    image = rng.integers(0, 12, size=(60, 240, 3), dtype=np.uint8)
    colors = compute_zone_colors(image)
    for red, green, blue in colors:
        assert max(red, green, blue) < 30


def test_saturation_boost_parameter():
    image = solid(60, 240, (120, 100, 110))
    plain = compute_zone_colors(image, saturation_boost=1.0)
    boosted = compute_zone_colors(image, saturation_boost=2.5)
    assert plain != boosted or plain[0][0] == plain[0][2]


def test_empty_and_tiny_images():
    assert compute_zone_colors(None) == [(0, 0, 0)] * 4  # type: ignore[arg-type]
    assert compute_zone_colors(np.zeros((0, 0, 3), dtype=np.uint8)) == [(0, 0, 0)] * 4
    assert compute_zone_colors(np.zeros((1, 2, 3), dtype=np.uint8)) == [(0, 0, 0)] * 4

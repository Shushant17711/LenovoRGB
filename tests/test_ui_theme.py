from __future__ import annotations

from lenovorgb import colors
from lenovorgb.modes import MODES
from lenovorgb.ui import theme


def test_categories_have_colours():
    for category in {mode.category for mode in MODES}:
        assert category in theme.CATEGORY_COLORS
        assert theme.CATEGORY_COLORS[category].startswith("#")


def test_palette_contrast_is_usable():
    # Text on the window background should be clearly lighter.
    bg = colors.parse_hex(theme.BG)
    text = colors.parse_hex(theme.TEXT)
    assert sum(text) > sum(bg) + 300
    assert sum(colors.parse_hex(theme.TEXT_SECONDARY)) > sum(bg) + 200


def test_accent_is_bright():
    accent = colors.parse_hex(theme.ACCENT)
    assert max(accent) > 180
    assert min(accent) < 100

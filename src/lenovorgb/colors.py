"""Small, dependency-free color helpers shared by modes and the UI."""

from __future__ import annotations

import colorsys
import re
from collections.abc import Iterable, Sequence
from typing import List, Tuple

from .constants import ZONE_COUNT

Color = Tuple[int, int, int]
BLACK: Color = (0, 0, 0)
WHITE: Color = (255, 255, 255)

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def clamp8(value: float) -> int:
    return 0 if value <= 0 else 255 if value >= 255 else int(value)


def as_color(value: Sequence[float]) -> Color:
    return (clamp8(value[0]), clamp8(value[1]), clamp8(value[2]))


def scale(color: Sequence[float], factor: float) -> Color:
    """Multiply a color by a factor (brightness / fade)."""
    return (clamp8(color[0] * factor), clamp8(color[1] * factor), clamp8(color[2] * factor))


def add(a: Sequence[float], b: Sequence[float]) -> Color:
    return (clamp8(a[0] + b[0]), clamp8(a[1] + b[1]), clamp8(a[2] + b[2]))


def lerp(a: Sequence[float], b: Sequence[float], t: float) -> Color:
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return (
        clamp8(a[0] + (b[0] - a[0]) * t),
        clamp8(a[1] + (b[1] - a[1]) * t),
        clamp8(a[2] + (b[2] - a[2]) * t),
    )


def hsv(hue: float, saturation: float = 1.0, value: float = 1.0) -> Color:
    r, g, b = colorsys.hsv_to_rgb(hue % 1.0, _unit(saturation), _unit(value))
    return (clamp8(r * 255), clamp8(g * 255), clamp8(b * 255))


def rgb_to_hsv(color: Sequence[float]) -> Tuple[float, float, float]:
    return colorsys.rgb_to_hsv(
        _unit(color[0] / 255.0), _unit(color[1] / 255.0), _unit(color[2] / 255.0)
    )


def _unit(value: float) -> float:
    return 0.0 if value < 0 else 1.0 if value > 1 else float(value)


def parse_hex(text: str, default: Color = (91, 140, 255)) -> Color:
    """Parse ``#rgb`` / ``#rrggbb`` (with or without ``#``)."""
    if not isinstance(text, str):
        return default
    match = _HEX_RE.match(text.strip())
    if not match:
        return default
    digits = match.group(1)
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))


def to_hex(color: Sequence[float]) -> str:
    return f"#{clamp8(color[0]):02x}{clamp8(color[1]):02x}{clamp8(color[2]):02x}"


def normalize_frame(colors: Iterable[Sequence[float]], brightness: float = 100.0) -> List[Color]:
    """Clamp any iterable of colors to exactly ``ZONE_COUNT`` RGB tuples.

    ``brightness`` is a percentage (0-100) applied in software so users get
    fine-grained dimming without rewriting the hardware brightness byte.
    """
    factor = max(0.0, min(100.0, float(brightness))) / 100.0
    result: List[Color] = []
    for color in colors:
        if len(color) < 3:
            result.append(BLACK)
        else:
            result.append(
                (
                    clamp8(float(color[0]) * factor),
                    clamp8(float(color[1]) * factor),
                    clamp8(float(color[2]) * factor),
                )
            )
        if len(result) >= ZONE_COUNT:
            break
    while len(result) < ZONE_COUNT:
        result.append(BLACK)
    return result


def is_black(frame: Iterable[Sequence[float]]) -> bool:
    return all(max(color[0], color[1], color[2]) <= 0 for color in frame)


def lighten(color: Sequence[float], amount: float) -> Color:
    return (
        clamp8(color[0] + (255 - color[0]) * amount),
        clamp8(color[1] + (255 - color[1]) * amount),
        clamp8(color[2] + (255 - color[2]) * amount),
    )

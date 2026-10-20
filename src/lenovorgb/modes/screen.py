"""Screen ambilight mode."""

from __future__ import annotations

import colorsys
from collections.abc import Sequence
from typing import List

import numpy as np

from .. import colors as col
from ..inputs.screen import ScreenGrabber
from .base import Frame, Mode, ModeContext

Color = Sequence[float]


def compute_zone_colors(
    image: np.ndarray,
    saturation_boost: float = 1.6,
    black_threshold: float = 0.05,
) -> List[Color]:
    """Reduce a screenshot to four representative colors.

    The screen is split into four vertical strips matching the keyboard.
    Dark pixels are ignored, saturated pixels are weighted more heavily so a
    mostly-black IDE does not wash the keyboard out.
    """
    if image is None or image.size == 0:
        return [(0, 0, 0)] * 4
    height, width = image.shape[:2]
    if height < 2 or width < 4:
        return [(0, 0, 0)] * 4

    data = image.astype(np.float32) / 255.0
    # Nearest-neighbour downscale keeps this cheap at 4K.
    step_y = max(1, height // 90)
    step_x = max(1, width // 180)
    data = data[::step_y, ::step_x]
    width = data.shape[1]
    edges = [int(round(i * width / 4)) for i in range(5)]

    result: List[Color] = []
    for zone in range(4):
        block = data[:, edges[zone] : edges[zone + 1], :3].reshape(-1, 3)
        if block.size == 0:
            result.append((0, 0, 0))
            continue
        luma = block @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        average_luma = float(luma.mean())

        if average_luma < black_threshold * 0.6:
            result.append((0, 0, 0))
            continue

        if average_luma < black_threshold:
            # Near-black content: a faint tint, never a glowing white.
            factor = (average_luma - black_threshold * 0.6) / (black_threshold * 0.4)
            tint = block.mean(axis=0) * float(factor) * 90.0
            result.append(col.as_color(tint))
            continue

        high = block.max(axis=1)
        low = block.min(axis=1)
        saturation = (high - low) / np.maximum(high, 1e-6)
        weights = (saturation * high) ** 2
        weight_sum = float(weights.sum())

        if weight_sum < 1e-3 or float(saturation.mean()) < 0.10:
            # Grayscale content (terminal, document): dim cool grey.
            level = min(1.0, average_luma * 1.5)
            result.append((int(52 * level), int(62 * level), int(88 * level)))
            continue

        average = (block * weights[:, None]).sum(axis=0) / weight_sum
        hue, sat, value = colorsys.rgb_to_hsv(*[float(c) for c in average])
        sat = min(1.0, sat * saturation_boost)
        value = min(1.0, value * 1.35)
        red, green, blue = colorsys.hsv_to_rgb(hue, sat, value)
        result.append((int(red * 255), int(green * 255), int(blue * 255)))
    return result


class ScreenAmbilight(Mode):
    id = "screen"
    name = "Screen Ambilight"
    description = "Mirrors the colours on your display onto the keyboard."
    category = "system"
    abbr = "SC"
    accent = "#a78bfa"
    needs = ("screen",)

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self.grabber = ScreenGrabber()
        self._smooth = [[0.0, 0.0, 0.0] for _ in range(4)]
        self._boost = float(ctx.config.get("screen.saturation_boost", 1.6))
        self._threshold = float(ctx.config.get("screen.black_threshold", 0.05))
        fps = max(2, int(ctx.config.get("screen.fps", 20)))
        self.interval = 1.0 / fps

    def setup(self) -> None:
        backend = self.grabber.open()
        self.ctx.log.info("Ambilight capturing via %s", backend)

    def step(self, dt: float) -> Frame:
        image = self.grabber.grab()
        targets = compute_zone_colors(image, self._boost, self._threshold)
        rising = min(1.0, 12.0 * dt)
        falling = min(1.0, 22.0 * dt)
        for zone in range(4):
            for channel in range(3):
                current = self._smooth[zone][channel]
                target = float(targets[zone][channel])
                alpha = falling if target < current else rising
                current += (target - current) * alpha
                if current < 3.0 and target < 1.0:
                    current = 0.0
                self._smooth[zone][channel] = current
        return [tuple(int(value) for value in zone) for zone in self._smooth]

    def teardown(self) -> None:
        self.grabber.close()

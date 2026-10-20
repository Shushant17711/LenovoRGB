"""System monitoring modes."""

from __future__ import annotations

import colorsys
from typing import List

import psutil

from .base import Frame, Mode


def load_color(percent: float, brightness_floor: float = 0.35) -> tuple:
    """Blue when idle, green under normal load, red at 100%."""
    percent = max(0.0, min(100.0, percent))
    hue = (1.0 - percent / 100.0) * 0.66
    value = brightness_floor + (percent / 100.0) * (1.0 - brightness_floor)
    saturation = 0.9 + (percent / 100.0) * 0.1
    red, green, blue = colorsys.hsv_to_rgb(hue, saturation, value)
    return (int(red * 255), int(green * 255), int(blue * 255))


class CpuMonitor(Mode):
    id = "cpu"
    name = "CPU Monitor"
    description = "Each zone shows a slice of your CPU load, blue to red."
    category = "system"
    abbr = "CP"
    accent = "#34d399"
    interval = 0.25
    needs = ("psutil",)

    def setup(self) -> None:
        psutil.cpu_percent(interval=None, percpu=True)

    def step(self, dt: float) -> Frame:
        per_core = psutil.cpu_percent(interval=None, percpu=True) or [0.0]
        groups: List[float] = [0.0, 0.0, 0.0, 0.0]
        if len(per_core) >= 4:
            chunk = max(1, len(per_core) // 4)
            for zone in range(4):
                start = zone * chunk
                stop = len(per_core) if zone == 3 else (zone + 1) * chunk
                values = per_core[start:stop]
                groups[zone] = sum(values) / len(values) if values else 0.0
        else:
            average = sum(per_core) / len(per_core)
            groups = [average] * 4
        return [load_color(value) for value in groups]

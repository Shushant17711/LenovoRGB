"""Ambient, continuously animated effects."""

from __future__ import annotations

import math
import random

from .. import colors as col
from .base import Frame, Mode, ModeContext

LENOVO_BLUE = (30, 190, 255)


class Breathing(Mode):
    id = "breathing"
    name = "Breathing"
    description = "A slow, calm pulse in Lenovo blue."
    category = "ambient"
    abbr = "BR"
    accent = "#38bdf8"
    interval = 0.03

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._t = 0.0

    def step(self, dt: float) -> Frame:
        self._t += dt
        value = ((math.sin(self._t * 1.5) + 1.0) / 2.0) ** 0.8
        return self.fill(tuple(int(channel * value) for channel in LENOVO_BLUE))


class Rainbow(Mode):
    id = "rainbow"
    name = "Rainbow Wave"
    description = "A smooth rainbow flowing across the four zones."
    category = "ambient"
    abbr = "RB"
    accent = "#fb7185"
    interval = 0.03

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._hue = 0.0

    def step(self, dt: float) -> Frame:
        self._hue = (self._hue + dt * 0.16) % 1.0
        return [col.hsv(self._hue + zone * 0.22) for zone in range(4)]


class Aurora(Mode):
    id = "aurora"
    name = "Aurora"
    description = "Drifting green-blue-purple curtains, like northern lights."
    category = "ambient"
    abbr = "AR"
    accent = "#4ade80"
    interval = 0.04

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._t = 0.0

    def step(self, dt: float) -> Frame:
        self._t += dt
        t = self._t
        frame: Frame = []
        for zone in range(4):
            first = math.sin(t * 0.55 + zone * 0.9)
            second = math.sin(t * 0.83 - zone * 0.5 + 2.0)
            third = math.sin(t * 1.21 + zone * 1.3 + 4.0)
            red = int(max(25, min(190, 55 + abs(first) * 135)))
            green = int(max(90, min(255, 140 + abs(second) * 115)))
            blue = int(max(110, min(255, 165 + abs(third) * 90)))
            frame.append((red, green, blue))
        return frame


class Fire(Mode):
    id = "fire"
    name = "Fire"
    description = "Flickering flames with occasional bright flare-ups."
    category = "ambient"
    abbr = "FR"
    accent = "#f97316"
    interval = 0.045

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._heat = [0.55, 0.7, 0.5, 0.62]
        self._flare = 0.0

    def step(self, dt: float) -> Frame:
        scale = max(0.2, dt / 0.05)
        frame: Frame = []
        if random.random() < 0.05 * scale:
            self._flare = random.uniform(0.6, 1.0)
        self._flare *= math.exp(-2.4 * dt)
        for zone in range(4):
            change = random.uniform(-0.22, 0.26) * scale
            self._heat[zone] = max(0.28, min(1.0, self._heat[zone] + change))
            heat = min(1.0, self._heat[zone] + self._flare * 0.5)
            red = int(255 * heat)
            green = int(min(255, 70 + 140 * heat))
            blue = int(random.uniform(0, 18) if random.random() < 0.06 else 0)
            frame.append((red, green, blue))
        return frame


class Plasma(Mode):
    id = "plasma"
    name = "Plasma"
    description = "Organic, multi-frequency color fields that never repeat."
    category = "ambient"
    abbr = "PL"
    accent = "#e879f9"
    interval = 0.03

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._t = 0.0

    def step(self, dt: float) -> Frame:
        self._t += dt
        t = self._t
        frame: Frame = []
        for zone in range(4):
            one = math.sin(t * 1.15 + zone * 1.4)
            two = math.sin(t * 0.85 - zone * 1.7 + 2.0)
            three = math.sin(t * 1.6 + zone * 0.95 + 4.0)
            four = math.sin(t * 0.6 - zone * 2.1 + 1.5)
            hue = ((one + two + three + four) / 8.0 + 0.5 + t * 0.02) % 1.0
            saturation = 0.75 + 0.25 * ((one + two) / 2.0)
            value = 0.62 + 0.38 * ((three + four + 2.0) / 4.0)
            frame.append(col.hsv(hue, saturation, value))
        return frame


class Heartbeat(Mode):
    id = "heartbeat"
    name = "Heartbeat"
    description = "A realistic lub-dub pulse with a slowly drifting hue."
    category = "ambient"
    abbr = "HB"
    accent = "#fb7185"
    interval = 0.02

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._t = 0.0

    @staticmethod
    def _beat(phase: float) -> float:
        if phase < 0.12:
            return math.sin((phase / 0.12) * math.pi) ** 0.6 * 0.95
        if phase < 0.20:
            return max(0.0, 0.2 - (phase - 0.12) * 2.0)
        if phase < 0.32:
            return 0.7 * math.sin(((phase - 0.20) / 0.12) * math.pi) ** 0.6
        return 0.05 + 0.08 * math.sin(((phase - 0.32) / 0.68) * math.pi)

    def step(self, dt: float) -> Frame:
        self._t += dt
        hue = 0.65 - (self._t / 10.0 % 1.0) * 0.65
        frame: Frame = []
        for zone in range(4):
            phase = (self._t + zone * 0.025) % 1.0
            intensity = self._beat(phase)
            frame.append(col.hsv(hue, 0.95, intensity))
        return frame


class Dna(Mode):
    id = "dna"
    name = "DNA Helix"
    description = "Two counter-rotating strands weave across the keyboard."
    category = "ambient"
    abbr = "DN"
    accent = "#2dd4bf"
    interval = 0.025

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._t = 0.0

    def step(self, dt: float) -> Frame:
        self._t += dt
        t = self._t
        frame: Frame = []
        for zone in range(4):
            strand_a = (math.sin(t * 1.8 + zone * 1.3) + 1.0) / 2.0
            strand_b = (math.sin(-t * 1.8 + zone * 1.3 + math.pi) + 1.0) / 2.0
            red = int(255 * strand_b)
            green = int(255 * strand_a)
            blue = int(255 * max(strand_a, strand_b))
            boost = int(110 * (strand_a * strand_b) ** 1.5)
            frame.append(
                (
                    min(255, red + boost),
                    min(255, green + boost),
                    min(255, blue + boost),
                )
            )
        return frame


class Meteor(Mode):
    id = "meteor"
    name = "Meteor"
    description = "A glowing meteor bounces across the zones, leaving a tail."
    category = "ambient"
    abbr = "ME"
    accent = "#facc15"
    interval = 0.025

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._position = 0.0
        self._direction = 1.0

    def step(self, dt: float) -> Frame:
        self._position += self._direction * dt * 3.2
        if self._position >= 3.0:
            self._position = 3.0
            self._direction = -1.0
        elif self._position <= 0.0:
            self._position = 0.0
            self._direction = 1.0
        tint = (30, 220, 255) if self._direction > 0 else (255, 60, 200)
        frame: Frame = []
        for zone in range(4):
            distance = abs(zone - self._position)
            intensity = max(0.0, 1.0 - distance * 0.55) ** 1.6
            frame.append(tuple(int(channel * intensity) for channel in tint))
        return frame

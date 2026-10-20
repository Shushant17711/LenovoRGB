"""High-energy effects: matrix, disco, storm and glitch."""

from __future__ import annotations

import math
import random
from typing import Optional

from .base import Frame, Mode, ModeContext

DISCO_PALETTE = [
    (255, 0, 100),
    (0, 255, 150),
    (100, 0, 255),
    (255, 200, 0),
    (0, 180, 255),
    (255, 50, 0),
    (200, 0, 255),
    (0, 255, 50),
    (255, 100, 200),
]


class Matrix(Mode):
    id = "matrix"
    name = "Matrix Rain"
    description = "Bursts of cyber-green code rain falling across the zones."
    category = "effects"
    abbr = "MT"
    accent = "#22c55e"
    interval = 0.025

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._flash = [0.0, 0.0, 0.0, 0.0]
        self._timers = [random.uniform(0.1, 0.6) for _ in range(4)]

    def step(self, dt: float) -> Frame:
        frame: Frame = []
        for zone in range(4):
            self._timers[zone] -= dt
            if self._timers[zone] <= 0:
                self._flash[zone] = random.uniform(0.8, 1.0)
                self._timers[zone] = random.uniform(0.15, 0.85)
            else:
                self._flash[zone] *= math.exp(-5.0 * dt)
                if self._flash[zone] < 0.04:
                    self._flash[zone] = 0.0
            level = self._flash[zone]
            frame.append((int(level * 18), int(level * 255), int(level * 45)))
        return frame


class Disco(Mode):
    id = "disco"
    name = "Disco"
    description = "Beat-synced strobes at 130 BPM. Every 8th beat goes white."
    category = "effects"
    abbr = "DS"
    accent = "#f472b6"
    interval = 0.02

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._bpm = 130.0
        self._beat = 0.0
        self._count = 0
        self._strobe = 0.0
        self._current = [random.choice(DISCO_PALETTE) for _ in range(4)]

    def step(self, dt: float) -> Frame:
        self._beat += dt
        interval = 60.0 / self._bpm
        if self._beat >= interval:
            self._beat -= interval
            self._count += 1
            if self._count % 8 == 0:
                self._strobe = 0.09
            else:
                self._current = [random.choice(DISCO_PALETTE) for _ in range(4)]

        if self._strobe > 0:
            self._strobe -= dt
            if self._strobe < 0.035:
                return self.black()
            return self.fill((255, 255, 255))

        progress = self._beat / interval
        fade = max(0.18, (1.0 - progress) ** 0.7)
        return [tuple(int(channel * fade) for channel in color) for color in self._current]


class Storm(Mode):
    id = "storm"
    name = "Lightning Storm"
    description = "A dark violet ambience torn by multi-stage lightning strikes."
    category = "effects"
    abbr = "ST"
    accent = "#818cf8"
    interval = 0.025

    AMBIENT = [
        (12, 4, 25),
        (10, 3, 22),
        (11, 4, 24),
        (9, 3, 20),
    ]

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._strike_at = random.uniform(1.5, 3.5)
        self._strike_zone = 0
        self._strike_age = -1.0
        self._t = 0.0
        self._display = [tuple(float(c) for c in color) for color in self.AMBIENT]

    def step(self, dt: float) -> Frame:
        self._t += dt
        if self._strike_age < 0:
            self._strike_at -= dt
            if self._strike_at <= 0:
                self._strike_zone = random.randrange(4)
                self._strike_age = 0.0
            else:
                frame: Frame = []
                for zone in range(4):
                    flicker = 0.85 + 0.15 * math.sin(self._t * 0.6 + zone * 1.1)
                    frame.append(tuple(int(c * flicker) for c in self.AMBIENT[zone]))
                return frame

        self._strike_age += dt
        age = self._strike_age
        frame = []
        for zone in range(4):
            distance = abs(zone - self._strike_zone)
            if age < 0.08:
                if zone == self._strike_zone:
                    color = (255, 255, 255)
                else:
                    glow = 100.0 / (distance + 1)
                    color = (int(glow), int(glow), int(glow * 1.2))
            elif age < 0.14:
                color = (15, 8, 35)
            elif age < 0.28:
                brightness = 200.0 * max(0.0, 1.0 - distance * 0.3)
                color = (int(brightness * 0.75), int(brightness * 0.8), int(brightness))
            elif age < 0.85:
                glow = max(0.0, 1.0 - (age - 0.28) / 0.57) ** 1.5
                local = glow * max(0.0, 1.0 - distance * 0.2)
                color = (
                    int(min(255, self.AMBIENT[zone][0] + 120 * local)),
                    int(min(255, self.AMBIENT[zone][1] + 40 * local)),
                    int(min(255, self.AMBIENT[zone][2] + 180 * local)),
                )
            else:
                color = self.AMBIENT[zone]
            frame.append(color)

        if age >= 0.85:
            self._strike_age = -1.0
            self._strike_at = random.uniform(2.0, 4.5)
        return frame


class Glitch(Mode):
    id = "glitch"
    name = "Cyberpunk Glitch"
    description = "Neon palette with random blackouts, inversions and scrambles."
    category = "effects"
    abbr = "GL"
    accent = "#f0abfc"
    interval = 0.04

    PALETTE = [
        (0, 255, 255),
        (255, 0, 255),
        (255, 20, 147),
        (0, 191, 255),
        (255, 255, 0),
    ]

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._colors = [random.choice(self.PALETTE) for _ in range(4)]
        self._event: Optional[list] = None
        self._event_left = 0.0

    def step(self, dt: float) -> Frame:
        if self._event is not None:
            self._event_left -= dt
            if self._event_left > 0:
                return list(self._event)
            self._event = None

        if random.random() < 0.14 * max(0.25, dt / 0.04):
            kind = random.choice(["off", "white", "invert", "scramble"])
            if kind == "off":
                self._event = self.black()
            elif kind == "white":
                self._event = self.fill((255, 255, 255))
            elif kind == "invert":
                self._event = [
                    (255 - color[0], 255 - color[1], 255 - color[2]) for color in self._colors
                ]
            else:
                self._event = [random.choice(self.PALETTE) for _ in range(4)]
            self._event_left = random.uniform(0.03, 0.09)
            return list(self._event)

        for zone in range(4):
            if random.random() < 0.15:
                self._colors[zone] = random.choice(self.PALETTE)
        return list(self._colors)

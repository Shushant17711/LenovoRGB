"""Reactive modes driven by typing."""

from __future__ import annotations

import math
import random
import threading
from typing import List, Optional, Tuple

from .. import colors as col
from ..constants import ZONE_COUNT, zone_for_key
from ..inputs.keyboard import KeyboardMonitor
from .base import Frame, Mode, ModeContext

PALETTE: Tuple[Tuple[int, int, int], ...] = (
    (255, 40, 80),
    (255, 120, 30),
    (255, 214, 10),
    (60, 255, 140),
    (0, 220, 255),
    (90, 130, 255),
    (180, 90, 255),
    (255, 70, 210),
)


def vivid_color(previous: Optional[Tuple[int, int, int]] = None) -> Tuple[int, int, int]:
    """Pick a vivid color, avoiding an immediate repeat."""
    choice = random.choice(PALETTE)
    if previous is not None and choice == tuple(previous):
        choice = random.choice(PALETTE)
    return choice


def _start_keyboard(ctx: ModeContext, on_key) -> Optional[KeyboardMonitor]:
    monitor = KeyboardMonitor(on_key=on_key)
    try:
        backend = monitor.start()
        ctx.log.info("Reactive input using %s", backend)
        return monitor
    except Exception as exc:
        ctx.log.warning("Reactive input unavailable: %s", exc)
        raise


class TypeLighting(Mode):
    id = "type"
    name = "Type Lighting"
    description = "Every keypress lights its zone, then fades away."
    category = "reactive"
    abbr = "TY"
    accent = "#22d3ee"
    interval = 0.016
    needs = ("keyboard",)

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._lock = threading.Lock()
        self._colors = [(0.0, 0.0, 0.0) for _ in range(ZONE_COUNT)]
        self._level = [0.0] * ZONE_COUNT
        self._monitor: Optional[KeyboardMonitor] = None

    def setup(self) -> None:
        self._monitor = _start_keyboard(self.ctx, self._on_key)

    def _on_key(self, name: str) -> None:
        zone = zone_for_key(name)
        if zone < 0:
            zone = random.randrange(ZONE_COUNT)
        with self._lock:
            current = tuple(int(c) for c in self._colors[zone])
            self._colors[zone] = tuple(float(c) for c in vivid_color(current))
            self._level[zone] = 1.0

    def step(self, dt: float) -> Frame:
        frame: Frame = []
        decay = math.exp(-4.6 * dt)
        with self._lock:
            for zone in range(ZONE_COUNT):
                level = self._level[zone] * decay
                if level < 0.012:
                    level = 0.0
                self._level[zone] = level
                frame.append(tuple(c * level for c in self._colors[zone]))
        return frame

    def teardown(self) -> None:
        if self._monitor is not None:
            self._monitor.stop()
            self._monitor = None


class Ripple(Mode):
    id = "ripple"
    name = "Ripple"
    description = "Keypresses send colored waves across all four zones."
    category = "reactive"
    abbr = "RP"
    accent = "#8b5cf6"
    interval = 0.022
    needs = ("keyboard",)

    MAX_EVENTS = 32

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self._lock = threading.Lock()
        self._events: List[dict] = []
        self._monitor: Optional[KeyboardMonitor] = None

    def setup(self) -> None:
        self._monitor = _start_keyboard(self.ctx, self._on_key)

    def _on_key(self, name: str) -> None:
        zone = zone_for_key(name)
        if zone < 0:
            zone = random.randrange(ZONE_COUNT)
        with self._lock:
            self._events.append({"origin": zone, "age": 0.0, "color": vivid_color()})
            if len(self._events) > self.MAX_EVENTS:
                del self._events[: len(self._events) - self.MAX_EVENTS]

    def step(self, dt: float) -> Frame:
        totals = [[0.0, 0.0, 0.0] for _ in range(ZONE_COUNT)]
        with self._lock:
            alive = []
            for event in self._events:
                event["age"] += dt
                radius = event["age"] * 4.5
                width = 1.15
                fade = max(0.0, 1.0 - event["age"] / 1.15) ** 1.3
                if fade > 0:
                    alive.append(event)
                for zone in range(ZONE_COUNT):
                    distance = abs(abs(zone - event["origin"]) - radius)
                    if distance < width:
                        intensity = (1.0 - distance / width) ** 1.8
                        gain = intensity * fade
                        for channel in range(3):
                            totals[zone][channel] += event["color"][channel] * gain
            self._events = alive
        return [col.as_color(zone) for zone in totals]

    def teardown(self) -> None:
        if self._monitor is not None:
            self._monitor.stop()
            self._monitor = None

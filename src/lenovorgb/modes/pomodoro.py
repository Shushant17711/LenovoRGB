"""A silent Pomodoro timer rendered on the keyboard."""

from __future__ import annotations

import math
import time
from typing import List

from .base import Frame, Mode, ModeContext

WORK = "work"
BREAK = "break"
LONG_BREAK = "long break"

GREEN = (40, 255, 120)
AMBER = (255, 170, 40)
BLUE = (40, 130, 255)
PURPLE = (150, 90, 255)
WHITE = (255, 255, 255)


class Pomodoro(Mode):
    id = "pomodoro"
    name = "Pomodoro"
    description = "Green focus timer that turns blue when it is time for a break."
    category = "system"
    abbr = "PM"
    accent = "#fbbf24"
    interval = 0.1
    needs = ("timer",)

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        pomodoro = ctx.config.get("pomodoro", {})
        self.work = float(pomodoro.get("work_minutes", 25)) * 60
        self.short_break = float(pomodoro.get("break_minutes", 5)) * 60
        self.long_break = float(pomodoro.get("long_break_minutes", 15)) * 60
        self.cycles = int(pomodoro.get("cycles_before_long_break", 4))
        self.phase = WORK
        self.started = 0.0
        self.cycle = 1
        self._t = 0.0

    def setup(self) -> None:
        self.started = time.monotonic()
        self.ctx.log.info(
            "Pomodoro started: %.0f min work, %.0f min break",
            self.work / 60,
            self.short_break / 60,
        )

    def _duration(self) -> float:
        if self.phase == WORK:
            return self.work
        if self.phase == LONG_BREAK:
            return self.long_break
        return self.short_break

    def _advance(self) -> None:
        if self.phase == WORK:
            if self.cycle % self.cycles == 0:
                self.phase = LONG_BREAK
            else:
                self.phase = BREAK
        else:
            if self.phase == BREAK:
                self.cycle += 1
            elif self.phase == LONG_BREAK:
                self.cycle = 1
            self.phase = WORK
        self.started = time.monotonic()

    def step(self, dt: float) -> Frame:
        self._t += dt
        elapsed = time.monotonic() - self.started
        duration = self._duration()
        if elapsed >= duration:
            finished = self.phase
            self._advance()
            elapsed = 0.0
            duration = self._duration()
            self.ctx.log.info("Pomodoro phase change: %s -> %s", finished, self.phase)

        progress = max(0.0, min(1.0, elapsed / duration if duration else 0.0))
        remaining = duration - elapsed
        transition = (time.monotonic() - self.started) < 0.9

        if transition:
            pulse = 0.5 + 0.5 * math.sin(self._t * 18)
            return self.fill(tuple(int(255 * pulse) for _ in range(3)))

        if self.phase == WORK:
            color = GREEN if progress < 0.8 else AMBER
            filled = progress * 4.0
            frame: List[tuple] = []
            for zone in range(4):
                amount = max(0.0, min(1.0, filled - zone))
                if amount <= 0:
                    frame.append((0, 0, 0))
                else:
                    pulse = 0.85 + 0.15 * math.sin(self._t * 3.2 + zone)
                    frame.append(tuple(int(channel * amount * pulse) for channel in color))
            return frame

        base = BLUE if self.phase == BREAK else PURPLE
        if remaining <= 10:
            pulse = 0.6 + 0.4 * math.sin(self._t * 9)
        else:
            pulse = 0.55 + 0.45 * math.sin(self._t * 1.2)
        return self.fill(tuple(int(channel * pulse) for channel in base))

    def teardown(self) -> None:
        self.ctx.log.info("Pomodoro stopped during %s", self.phase)

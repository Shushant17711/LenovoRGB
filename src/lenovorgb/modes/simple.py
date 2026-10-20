"""Solid color and lights-off modes."""

from __future__ import annotations

from .. import colors as col
from .base import Frame, Mode, ModeContext


class Solid(Mode):
    id = "solid"
    name = "Solid Color"
    description = "One steady colour across all four zones."
    category = "ambient"
    abbr = "SL"
    accent = "#5b8cff"
    interval = 0.5

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        override = ctx.options.get("color")
        self.color = col.parse_hex(
            str(override) if override else ctx.config.get("static_color", "#5B8CFF")
        )

    def step(self, dt: float) -> Frame:
        return self.fill(self.color)


class Off(Mode):
    id = "off"
    name = "Lights Off"
    description = "Turn the keyboard illumination completely off."
    category = "utility"
    abbr = "OF"
    accent = "#64748b"
    interval = 0.5

    def step(self, dt: float) -> Frame:
        return self.black()

"""Mode plugin base class and shared helpers."""

from __future__ import annotations

import logging
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..config import Config
from ..constants import ZONE_COUNT

Color = Sequence[float]
Frame = List[Sequence[float]]

CATEGORIES: Dict[str, str] = {
    "reactive": "Reactive",
    "system": "System",
    "ambient": "Ambient",
    "effects": "Effects",
}


@dataclass
class ModeContext:
    """Everything a mode is allowed to touch."""

    config: Config
    stop: threading.Event
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("lenovorgb.mode"))
    options: Dict[str, object] = field(default_factory=dict)

    def sleep(self, seconds: float) -> bool:
        """Sleep unless/until the mode is stopped. True means 'stop now'."""
        if seconds <= 0:
            return self.stop.is_set()
        return self.stop.wait(seconds)

    @property
    def brightness(self) -> int:
        return self.config.brightness


class Mode:
    """A lighting effect.

    ``step`` is called at ``interval`` seconds and returns four RGB colors.
    Returning ``None`` keeps the previous frame (useful while waiting for
    audio or input).
    """

    id: str = ""
    name: str = ""
    description: str = ""
    category: str = "ambient"
    abbr: str = "??"
    accent: str = "#22d3ee"
    interval: float = 0.033
    needs: tuple = ()

    def __init__(self, ctx: ModeContext):
        self.ctx = ctx

    def setup(self) -> None:
        """Called once before the first ``step`` (in the mode thread)."""

    def step(self, dt: float) -> Optional[Frame]:
        raise NotImplementedError

    def teardown(self) -> None:
        """Called once when the mode stops, even after an error."""

    # ------------------------------------------------------------- utilities
    def fill(self, color: Color) -> Frame:
        return [color for _ in range(ZONE_COUNT)]

    def black(self) -> Frame:
        return [(0, 0, 0) for _ in range(ZONE_COUNT)]

    @staticmethod
    def blank() -> Frame:
        return [(0, 0, 0) for _ in range(ZONE_COUNT)]

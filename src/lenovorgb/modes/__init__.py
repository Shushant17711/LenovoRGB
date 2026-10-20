"""Mode registry."""

from __future__ import annotations

from typing import Dict, List, Type

from .ambient import Aurora, Breathing, Dna, Fire, Heartbeat, Meteor, Plasma, Rainbow
from .audio import AudioVisualizer
from .base import CATEGORIES, Mode, ModeContext
from .effects import Disco, Glitch, Matrix, Storm
from .pomodoro import Pomodoro
from .reactive import Ripple, TypeLighting
from .screen import ScreenAmbilight
from .simple import Off, Solid
from .system import CpuMonitor

CATEGORIES["utility"] = "Utility"

#: Display order used by the CLI and the UI.
MODES: List[Type[Mode]] = [
    TypeLighting,
    Ripple,
    AudioVisualizer,
    CpuMonitor,
    ScreenAmbilight,
    Pomodoro,
    Breathing,
    Rainbow,
    Aurora,
    Fire,
    Plasma,
    Heartbeat,
    Dna,
    Meteor,
    Matrix,
    Disco,
    Storm,
    Glitch,
    Solid,
    Off,
]

MODE_MAP: Dict[str, Type[Mode]] = {mode.id: mode for mode in MODES}
CATEGORY_ORDER: List[str] = ["reactive", "system", "ambient", "effects", "utility"]


def get_mode(mode_id: str) -> Type[Mode]:
    try:
        return MODE_MAP[mode_id]
    except KeyError as exc:
        choices = ", ".join(MODE_MAP)
        raise KeyError(f"Unknown mode '{mode_id}'. Available modes: {choices}") from exc


def all_ids() -> List[str]:
    return [mode.id for mode in MODES]


def by_category(category: str) -> List[Type[Mode]]:
    return [mode for mode in MODES if mode.category == category]


def grouped() -> Dict[str, List[Type[Mode]]]:
    result: Dict[str, List[Type[Mode]]] = {}
    for category in CATEGORY_ORDER:
        modes = by_category(category)
        if modes:
            result[category] = modes
    return result


__all__ = [
    "CATEGORIES",
    "CATEGORY_ORDER",
    "MODES",
    "MODE_MAP",
    "Mode",
    "ModeContext",
    "all_ids",
    "by_category",
    "get_mode",
    "grouped",
]

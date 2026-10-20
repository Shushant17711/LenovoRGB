"""Cross-platform application paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import APP_NAME


def _xdg(env_name: str, fallback: str) -> Path:
    value = os.environ.get(env_name)
    if value:
        return Path(value).expanduser()
    return Path(fallback).expanduser()


def config_dir() -> Path:
    """Directory for user configuration."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return _xdg("XDG_CONFIG_HOME", "~/.config") / "lenovorgb"


def state_dir() -> Path:
    """Directory for logs and runtime state."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / APP_NAME
    return _xdg("XDG_STATE_HOME", "~/.local/state") / "lenovorgb"


def config_file() -> Path:
    return config_dir() / "config.json"


def log_file() -> Path:
    return state_dir() / "lenovorgb.log"


def lock_file() -> Path:
    return state_dir() / "instance.lock"


def ensure_dirs() -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    state_dir().mkdir(parents=True, exist_ok=True)


def legacy_config_candidates() -> list[Path]:
    """Old versions stored config.json next to the script / exe."""
    spots: list[Path] = []
    if getattr(sys, "frozen", False):
        spots.append(Path(sys.executable).resolve().parent / "config.json")
    else:
        here = Path(__file__).resolve()
        # src/lenovorgb/paths.py -> repository root
        spots.append(here.parents[2] / "config.json")
        spots.append(Path.cwd() / "config.json")
    return [p for p in spots if p.is_file()]

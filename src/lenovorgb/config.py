"""User configuration with defaults, validation and safe writes."""

from __future__ import annotations

import copy
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from . import __version__
from .paths import config_file, ensure_dirs, legacy_config_candidates

log = logging.getLogger("lenovorgb.config")

DEFAULTS: Dict[str, Any] = {
    "schema_version": 2,
    "app_version": __version__,
    "default_mode": "type",
    "start_minimized": True,
    "launch_at_login": False,
    "hotkey": "ctrl+shift+m",
    "hotkey_enabled": True,
    "brightness": 100,
    "off_on_exit": True,
    "window": {"width": 960, "height": 660},
    "device": {"path": None, "product_id": None},
    "audio": {"device": None, "smoothing": 0.35, "samplerate": 44100},
    "screen": {"fps": 20, "saturation_boost": 1.6, "black_threshold": 0.05},
    "pomodoro": {
        "work_minutes": 25,
        "break_minutes": 5,
        "long_break_minutes": 15,
        "cycles_before_long_break": 4,
    },
    "static_color": "#5B8CFF",
    "tray": True,
}


def _deep_merge(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        elif key in result:
            result[key] = value
    return result


def _clamp(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


class Config:
    """JSON-backed settings object.

    Unknown keys from older versions are dropped, known keys are merged over
    the defaults so a half-written or outdated config never breaks startup.
    """

    def __init__(self, path: Optional[Path] = None, data: Optional[Dict[str, Any]] = None):
        self.path = Path(path) if path else config_file()
        self.data: Dict[str, Any] = copy.deepcopy(DEFAULTS)
        if data is not None:
            self.data = _deep_merge(DEFAULTS, _migrate(data))
        else:
            self.load()
        self._validate()

    # ------------------------------------------------------------------ load
    def load(self) -> None:
        loaded: Optional[Dict[str, Any]] = None
        candidates = [self.path]
        if self.path == config_file():
            candidates.extend(legacy_config_candidates())
        for candidate in candidates:
            try:
                with open(candidate, encoding="utf-8") as handle:
                    raw = json.load(handle)
                if isinstance(raw, dict):
                    loaded = _migrate(raw)
                    if candidate != self.path:
                        log.info("Migrated legacy config from %s", candidate)
                    break
            except FileNotFoundError:
                continue
            except (OSError, ValueError) as exc:
                log.warning("Ignoring unreadable config %s: %s", candidate, exc)
        if loaded:
            self.data = _deep_merge(DEFAULTS, loaded)

    def save(self) -> bool:
        """Atomically write the config. Returns False on failure."""
        self.data["app_version"] = __version__
        self._validate()
        try:
            ensure_dirs()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=".config-", suffix=".json", dir=str(self.path.parent)
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(self.data, handle, indent=2, sort_keys=True)
                    handle.write("\n")
                os.replace(tmp_name, self.path)
            except BaseException:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
            return True
        except OSError as exc:
            log.error("Could not save config to %s: %s", self.path, exc)
            return False

    # ----------------------------------------------------------------- access
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            if not isinstance(node.get(part), dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value
        self._validate()

    def update(self, values: Dict[str, Any]) -> None:
        self.data = _deep_merge(self.data, values)
        self._validate()

    def reset(self) -> None:
        self.data = copy.deepcopy(DEFAULTS)

    # --------------------------------------------------------------- helpers
    @property
    def brightness(self) -> int:
        return int(self.data["brightness"])

    @brightness.setter
    def brightness(self, value: float) -> None:
        self.data["brightness"] = int(_clamp(value, 0, 100, 100))

    def _validate(self) -> None:
        for section in ("audio", "device", "pomodoro", "screen", "window"):
            if not isinstance(self.data.get(section), dict):
                self.data[section] = copy.deepcopy(DEFAULTS[section])
        self.data["brightness"] = int(_clamp(self.data.get("brightness"), 0, 100, 100))
        self.data["screen"]["fps"] = int(_clamp(self.data["screen"].get("fps"), 2, 60, 20))
        self.data["audio"]["smoothing"] = round(
            _clamp(self.data["audio"].get("smoothing"), 0.05, 0.95, 0.35), 2
        )
        self.data["screen"]["saturation_boost"] = round(
            _clamp(self.data["screen"].get("saturation_boost"), 1.0, 3.0, 1.6), 2
        )
        self.data["screen"]["black_threshold"] = round(
            _clamp(self.data["screen"].get("black_threshold"), 0.0, 0.3, 0.05), 3
        )
        for key, low, high in (
            ("work_minutes", 1, 180),
            ("break_minutes", 1, 60),
            ("long_break_minutes", 1, 120),
            ("cycles_before_long_break", 1, 12),
        ):
            self.data["pomodoro"][key] = int(
                _clamp(self.data["pomodoro"].get(key), low, high, DEFAULTS["pomodoro"][key])
            )
        for key in ("static_color",):
            if not isinstance(self.data.get(key), str):
                self.data[key] = DEFAULTS[key]
        window = self.data.get("window") or {}
        self.data["window"] = {
            "width": int(_clamp(window.get("width"), 900, 4000, 960)),
            "height": int(_clamp(window.get("height"), 640, 3000, 660)),
        }
        hotkey = self.data.get("hotkey")
        if not isinstance(hotkey, str) or not hotkey.strip():
            self.data["hotkey"] = DEFAULTS["hotkey"]


def _migrate(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Translate the v1 config written by the old Tkinter app."""
    migrated = dict(raw)
    if "startup_minimized" in migrated and "start_minimized" not in migrated:
        migrated["start_minimized"] = bool(migrated.pop("startup_minimized"))
    if "shortcut" in migrated and "hotkey" not in migrated:
        migrated["hotkey"] = migrated.pop("shortcut")
    migrated.pop("shortcut", None)
    migrated["schema_version"] = 2
    return migrated


def load(path: Optional[Path] = None) -> Config:
    return Config(path=path)

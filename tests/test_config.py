from __future__ import annotations

import json
from pathlib import Path

from lenovorgb.config import DEFAULTS, Config


def test_defaults(config: Config):
    assert config.get("default_mode") == "type"
    assert config.brightness == 100
    assert config.get("pomodoro.work_minutes") == 25


def test_set_get_dotted(config: Config):
    config.set("audio.device", "Monitor of Speakers")
    assert config.get("audio.device") == "Monitor of Speakers"
    config.set("brand.new.key", 1)
    assert config.get("brand.new.key") == 1
    assert config.get("missing.path", "fallback") == "fallback"


def test_save_and_reload(tmp_path: Path, config: Config):
    config.set("default_mode", "aurora")
    config.set("brightness", 42)
    assert config.save()
    raw = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert raw["default_mode"] == "aurora"

    reloaded = Config(path=tmp_path / "config.json")
    assert reloaded.get("default_mode") == "aurora"
    assert reloaded.brightness == 42


def test_unknown_keys_are_dropped(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"default_mode": "fire", "obsolete": True}), encoding="utf-8")
    config = Config(path=path)
    assert config.get("default_mode") == "fire"
    assert config.get("obsolete") is None


def test_migrates_old_config(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "startup_minimized": False,
                "shortcut": "alt+shift+r",
                "default_mode": "matrix",
            }
        ),
        encoding="utf-8",
    )
    config = Config(path=path)
    assert config.get("start_minimized") is False
    assert config.get("hotkey") == "alt+shift+r"
    assert config.get("default_mode") == "matrix"


def test_invalid_values_are_clamped(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "brightness": 999,
                "hotkey": "",
                "screen": {"fps": 500},
                "pomodoro": {"work_minutes": -4},
                "window": {"width": 20, "height": 10},
            }
        ),
        encoding="utf-8",
    )
    config = Config(path=path)
    assert config.brightness == 100
    assert config.get("hotkey") == "ctrl+shift+m"
    assert config.get("screen.fps") == 60
    assert config.get("pomodoro.work_minutes") == 1
    assert config.get("window.width") == 900
    assert config.get("window.height") == 640


def test_corrupt_config_falls_back_to_defaults(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text("{ this is not json", encoding="utf-8")
    config = Config(path=path)
    assert config.get("default_mode") == DEFAULTS["default_mode"]
    assert config.brightness == 100


def test_wrong_section_types_are_repaired(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"screen": 5, "audio": "nope", "pomodoro": [], "window": None}),
        encoding="utf-8",
    )
    config = Config(path=path)
    assert config.get("screen.fps") == DEFAULTS["screen"]["fps"]
    assert config.get("audio.smoothing") == DEFAULTS["audio"]["smoothing"]
    assert config.get("pomodoro.work_minutes") == DEFAULTS["pomodoro"]["work_minutes"]
    assert config.get("window.width") == DEFAULTS["window"]["width"]


def test_save_is_atomic_and_leaves_no_temp_files(tmp_path: Path, config: Config):
    assert config.save()
    assert config.save()
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".config-")]
    assert leftovers == []

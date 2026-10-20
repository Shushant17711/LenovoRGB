from __future__ import annotations

import threading

import pytest

from lenovorgb.config import Config
from lenovorgb.modes import CATEGORIES, MODES, ModeContext, all_ids, get_mode, grouped
from lenovorgb.modes.base import Mode
from lenovorgb.modes.pomodoro import BREAK, LONG_BREAK, WORK, Pomodoro
from lenovorgb.modes.system import load_color

SAFE_MODES = [
    "breathing",
    "rainbow",
    "aurora",
    "fire",
    "plasma",
    "heartbeat",
    "dna",
    "meteor",
    "matrix",
    "disco",
    "storm",
    "glitch",
    "solid",
    "off",
    "cpu",
    "pomodoro",
]


def make_ctx(tmp_path, **overrides) -> ModeContext:
    config = Config(path=tmp_path / "config.json")
    for key, value in overrides.items():
        config.set(key, value)
    return ModeContext(config=config, stop=threading.Event())


def test_registry_is_consistent():
    ids = all_ids()
    assert len(ids) == len(set(ids))
    assert len(MODES) >= 18
    for mode in MODES:
        assert mode.id in get_mode(mode.id).id
        assert mode.name and mode.description and mode.abbr
        assert mode.category in CATEGORIES
        assert mode.accent.startswith("#") and len(mode.accent) == 7


def test_grouped_contains_every_mode():
    grouped_ids = {mode.id for modes in grouped().values() for mode in modes}
    assert grouped_ids == set(all_ids())


def test_unknown_mode_raises():
    with pytest.raises(KeyError):
        get_mode("does-not-exist")


@pytest.mark.parametrize("mode_id", SAFE_MODES)
def test_modes_produce_four_valid_colors(mode_id, tmp_path):
    ctx = make_ctx(tmp_path)
    mode: Mode = get_mode(mode_id)(ctx)
    mode.setup()
    try:
        for _ in range(3):
            frame = mode.step(0.05)
            assert frame is not None
            assert len(frame) == 4
            for color in frame:
                assert len(color) == 3
                assert all(0 <= int(channel) <= 255 for channel in color)
    finally:
        mode.teardown()


def test_solid_uses_configured_colour(tmp_path):
    ctx = make_ctx(tmp_path, static_color="#123456")
    mode = get_mode("solid")(ctx)
    assert mode.step(0.1)[0] == (0x12, 0x34, 0x56)
    assert mode.ctx.options == {}


def test_solid_option_override(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.options["color"] = "#ff0000"
    mode = get_mode("solid")(ctx)
    assert mode.step(0.1)[0] == (255, 0, 0)


def test_pomodoro_cycles(tmp_path):
    ctx = make_ctx(tmp_path, **{"pomodoro.work_minutes": 1, "pomodoro.break_minutes": 1})
    mode = Pomodoro(ctx)
    mode.setup()
    mode.phase = WORK
    mode.cycle = 1
    mode._advance()
    assert mode.phase == BREAK
    assert mode.cycle == 1

    mode.phase = BREAK
    mode._advance()
    assert mode.phase == WORK
    assert mode.cycle == 2

    mode.cycle = mode.cycles
    mode.phase = WORK
    mode._advance()
    assert mode.phase == LONG_BREAK

    mode.phase = LONG_BREAK
    mode._advance()
    assert mode.phase == WORK
    assert mode.cycle == 1
    mode._advance()
    assert mode.phase == BREAK  # a fresh cycle must not jump straight to a long break


def test_pomodoro_duration_per_phase(tmp_path):
    ctx = make_ctx(
        tmp_path,
        **{
            "pomodoro.work_minutes": 25,
            "pomodoro.break_minutes": 5,
            "pomodoro.long_break_minutes": 15,
        },
    )
    mode = Pomodoro(ctx)
    mode.phase = WORK
    assert mode._duration() == 25 * 60
    mode.phase = BREAK
    assert mode._duration() == 5 * 60
    mode.phase = LONG_BREAK
    assert mode._duration() == 15 * 60


def test_cpu_load_color_progression():
    idle = load_color(0)
    high = load_color(100)
    assert idle[2] > idle[0]  # blue
    assert high[0] > high[2]  # red
    assert load_color(300) == load_color(100)
    assert load_color(-10) == load_color(0)

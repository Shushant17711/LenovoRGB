from __future__ import annotations

import sys

import pytest

from lenovorgb.constants import ZONE_MAP, zone_for_key
from lenovorgb.inputs.keyboard import (
    InputUnavailable,
    KeyboardMonitor,
    normalize_key_name,
    parse_hotkey,
)


@pytest.mark.parametrize(
    ("key", "zone"),
    [
        ("q", 0),
        ("esc", 0),
        ("left ctrl", 0),
        ("y", 1),
        ("space", 1),
        ("p", 2),
        ("enter", 2),
        ("up", 3),
        ("numpad 4", 3),
        ("page up", 3),
    ],
)
def test_zone_for_key(key, zone):
    assert zone_for_key(key) == zone


def test_zone_for_unknown_key():
    assert zone_for_key("unknown-key") == -1
    assert zone_for_key(None) == -1


def test_zone_map_has_all_letters_and_digits():
    for letter in "abcdefghijklmnopqrstuvwxyz":
        assert letter in ZONE_MAP
    for digit in "0123456789":
        assert digit in ZONE_MAP


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("shift_l", "shift"),
        ("shift_r", "right shift"),
        ("ctrl_l", "ctrl"),
        ("cmd", "windows"),
        ("page_up", "page up"),
        ("Key.shift_r", "right shift"),
        ("Space", "space"),
    ],
)
def test_normalize_key_name(raw, expected):
    assert normalize_key_name(raw) == expected


def test_parse_hotkey():
    assert parse_hotkey("ctrl+shift+m") == ({"ctrl", "shift"}, "m")
    assert parse_hotkey("Alt + F4") == ({"alt"}, "f4")
    assert parse_hotkey("super+space") == ({"win"}, "space")
    assert parse_hotkey("") == (set(), "")


def test_hotkey_dispatch_without_devices():
    hits = []
    keys = []
    monitor = KeyboardMonitor(on_key=keys.append, on_hotkey=lambda: hits.append(1))
    monitor._dispatch("ctrl", True)
    monitor._dispatch("shift", True)
    monitor._dispatch("m", True)
    assert hits == [1]
    assert "m" in keys
    assert "ctrl" in keys

    # Key repeat is ignored, and the debounce prevents instant re-fires.
    monitor._dispatch("m", True)
    assert hits == [1]
    monitor._dispatch("m", False)
    monitor._dispatch("m", True)
    assert hits == [1]


def test_hotkey_requires_exact_modifiers():
    hits = []
    monitor = KeyboardMonitor(on_hotkey=lambda: hits.append(1), hotkey="ctrl+m")
    monitor._dispatch("ctrl", True)
    monitor._dispatch("alt", True)
    monitor._dispatch("m", True)
    assert hits == []


def test_hotkey_can_be_disabled():
    hits = []
    monitor = KeyboardMonitor(
        on_hotkey=lambda: hits.append(1), hotkey="ctrl+m", hotkey_enabled=False
    )
    monitor._dispatch("ctrl", True)
    monitor._dispatch("m", True)
    assert hits == []


def test_unknown_key_falls_through():
    monitor = KeyboardMonitor()
    # Should not raise even with no handlers.
    monitor._dispatch("some_media_key", True)
    monitor._dispatch("some_media_key", False)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux-specific")
def test_wayland_without_readable_input_raises(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monitor = KeyboardMonitor()
    monkeypatch.setattr(monitor, "_start_evdev", lambda: False)
    with pytest.raises(InputUnavailable) as excinfo:
        monitor.start()
    assert "input" in str(excinfo.value)

"""Hardware constants and the physical key -> lighting zone map."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

ZONE_COUNT = 4

VENDOR_ID = 0x048D  # Lenovo

# Product IDs of 4-zone RGB keyboards seen on LOQ / Legion / IdeaPad Gaming.
KNOWN_PIDS: List[int] = [
    0xC995, 0xC994, 0xC993,
    0xC985, 0xC984, 0xC983,
    0xC975, 0xC973,
    0xC965, 0xC963,
    0xC955,
]

# The vendor-specific HID interface used for lighting control.
RGB_USAGE_PAGE = 0xFF89
RGB_USAGE = 0x00CC

# HID feature report layout (33 bytes, first byte is the report ID).
REPORT_ID = 0xCC
CMD_STATIC = 0x16
SUB_STATIC = 0x01


def _zone_map() -> Dict[str, int]:
    """Map normalized key names to the 4 physical lighting zones.

    Zone 0 is the leftmost column (Esc / Tab / Caps / Shift) and zone 3 is
    the right-hand block (arrows / numpad / navigation cluster).
    """
    zones: Dict[str, int] = {}

    def add(zone: int, *names: str) -> None:
        for name in names:
            zones[name] = zone

    # Zone 0 - left
    add(
        0,
        "esc", "escape", "f1", "f2", "f3", "f4",
        "`", "grave", "1", "2", "3", "4",
        "tab", "q", "w", "e", "r",
        "caps lock", "caps_lock", "capslock", "a", "s", "d", "f",
        "left shift", "shift", "shift_l", "z", "x", "c", "v",
        "left ctrl", "ctrl", "ctrl_l", "control",
        "left windows", "windows", "win", "cmd", "cmd_l", "super", "meta",
        "left alt", "alt", "alt_l",
    )
    # Zone 1 - middle left
    add(
        1,
        "f5", "f6", "f7", "f8", "5", "6", "7", "8",
        "t", "y", "u", "i", "g", "h", "j", "k",
        "b", "n", "m", ",", "comma", "space",
    )
    # Zone 2 - middle right
    add(
        2,
        "f9", "f10", "f11", "f12", "9", "0", "-", "minus", "=", "equal",
        "backspace", "o", "p", "[", "left brace", "]", "right brace",
        "\\", "backslash", "l", ";", "semicolon", "'", "apostrophe",
        "enter", "return", ".", "period", "/", "slash",
        "right shift", "shift_r", "right alt", "alt_r", "alt gr", "altgr",
        "right ctrl", "ctrl_r", "print screen", "print_screen", "prtscn",
        "menu", "apps",
    )
    # Zone 3 - right (navigation / numpad)
    add(
        3,
        "insert", "ins", "delete", "del", "home", "end",
        "page up", "page_up", "pageup", "page down", "page_down", "pagedown",
        "up", "down", "left", "right",
        "num lock", "num_lock", "numlock", "divide", "multiply", "subtract",
        "add", "decimal", "clear",
        "numpad 0", "numpad 1", "numpad 2", "numpad 3", "numpad 4",
        "numpad 5", "numpad 6", "numpad 7", "numpad 8", "numpad 9",
    )
    return zones


ZONE_MAP: Dict[str, int] = _zone_map()

# Names that should never act as a "typing" event even if unmapped.
MODIFIER_NAMES = frozenset(
    {
        "ctrl", "ctrl_l", "ctrl_r", "shift", "shift_l", "shift_r",
        "alt", "alt_l", "alt_r", "alt_gr", "alt gr", "cmd", "cmd_l", "cmd_r",
        "windows", "win", "super", "meta", "caps lock", "caps_lock", "num lock",
        "num_lock",
    }
)


def zone_for_key(name: Optional[str]) -> int:
    """Return the zone for a key, or -1 when the key is unknown."""
    if not name:
        return -1
    key = name.lower().strip()
    if key in ZONE_MAP:
        return ZONE_MAP[key]
    # pynput sometimes reports "Key.shift_l" or "shift_l" style names.
    for prefix in ("key.", "keycode."):
        if key.startswith(prefix):
            key = key[len(prefix) :]
    return ZONE_MAP.get(key, -1)


def _env_override() -> Optional[int]:
    """Allow testing on machines without the RGB keyboard."""
    value = os.environ.get("LENOVORGB_FAKE_DEVICE")
    if value:
        try:
            return int(value, 0)
        except ValueError:
            return 0
    return None


def usb_product_ids() -> List[int]:
    """PIDs to look for. Honours ``LENOVORGB_FAKE_DEVICE`` for demos/tests."""
    override = _env_override()
    if override is not None:
        return [override] if override else list(KNOWN_PIDS)
    return list(KNOWN_PIDS)

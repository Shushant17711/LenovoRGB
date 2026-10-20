"""Global keyboard input for reactive modes and the mode-cycle hotkey.

Two backends are supported on Linux:

* ``evdev`` - reads ``/dev/input/event*`` directly, works on X11 *and*
  Wayland, requires the user to be in the ``input`` group.
* ``pynput`` - X11 / Windows / macOS, no special permissions on Linux but
  blind to key presses made in native Wayland windows.

The backend is picked automatically.
"""

from __future__ import annotations

import glob
import logging
import os
import select
import sys
import threading
import time
from typing import Callable, Dict, Optional, Set, Tuple

from ..constants import MODIFIER_NAMES, zone_for_key

log = logging.getLogger("lenovorgb.keyboard")

KeyHandler = Callable[[str], None]
HotkeyHandler = Callable[[], None]

MODIFIER_TOKENS = {"ctrl", "shift", "alt", "win"}


class InputUnavailable(RuntimeError):
    pass


# pynput reports e.g. "shift_l"; normalize to the names used by ZONE_MAP.
_PYNPUT_NAMES: Dict[str, str] = {
    "shift_l": "shift",
    "shift_r": "right shift",
    "ctrl_l": "ctrl",
    "ctrl_r": "right ctrl",
    "alt_l": "alt",
    "alt_r": "right alt",
    "alt_gr": "alt gr",
    "cmd": "windows",
    "cmd_l": "windows",
    "cmd_r": "right windows",
    "page_up": "page up",
    "page_down": "page down",
    "print_screen": "print screen",
    "scroll_lock": "scroll lock",
    "caps_lock": "caps lock",
    "num_lock": "num lock",
    "media_play_pause": "media play",
}

_EVDEV_NAMES: Dict[str, str] = {
    "KEY_ESC": "esc",
    "KEY_GRAVE": "`",
    "KEY_MINUS": "-",
    "KEY_EQUAL": "=",
    "KEY_BACKSPACE": "backspace",
    "KEY_TAB": "tab",
    "KEY_CAPSLOCK": "caps lock",
    "KEY_LEFTBRACE": "[",
    "KEY_RIGHTBRACE": "]",
    "KEY_BACKSLASH": "\\",
    "KEY_SEMICOLON": ";",
    "KEY_APOSTROPHE": "'",
    "KEY_ENTER": "enter",
    "KEY_KPENTER": "enter",
    "KEY_COMMA": ",",
    "KEY_DOT": ".",
    "KEY_SLASH": "/",
    "KEY_LEFTSHIFT": "shift",
    "KEY_RIGHTSHIFT": "right shift",
    "KEY_LEFTCTRL": "ctrl",
    "KEY_RIGHTCTRL": "right ctrl",
    "KEY_LEFTALT": "alt",
    "KEY_RIGHTALT": "right alt",
    "KEY_LEFTMETA": "windows",
    "KEY_RIGHTMETA": "right windows",
    "KEY_SPACE": "space",
    "KEY_PAGEUP": "page up",
    "KEY_PAGEDOWN": "page down",
    "KEY_INSERT": "insert",
    "KEY_DELETE": "delete",
    "KEY_HOME": "home",
    "KEY_END": "end",
    "KEY_NUMLOCK": "num lock",
    "KEY_KPSLASH": "divide",
    "KEY_KPASTERISK": "multiply",
    "KEY_KPMINUS": "subtract",
    "KEY_KPPLUS": "add",
    "KEY_KPDOT": "decimal",
    "KEY_UP": "up",
    "KEY_DOWN": "down",
    "KEY_LEFT": "left",
    "KEY_RIGHT": "right",
    "KEY_SYSRQ": "print screen",
    "KEY_COMPOSE": "menu",
    "KEY_KP0": "numpad 0",
    "KEY_KP1": "numpad 1",
    "KEY_KP2": "numpad 2",
    "KEY_KP3": "numpad 3",
    "KEY_KP4": "numpad 4",
    "KEY_KP5": "numpad 5",
    "KEY_KP6": "numpad 6",
    "KEY_KP7": "numpad 7",
    "KEY_KP8": "numpad 8",
    "KEY_KP9": "numpad 9",
}


def keyboard_available() -> bool:
    """Cheap check used to pick a sensible first-run mode.

    Windows and X11 always have a usable backend (pynput). On Wayland we
    need read access to /dev/input, which is exactly what the installer's
    optional input-group step grants.
    """
    if not sys.platform.startswith("linux"):
        return True
    if not (
        os.environ.get("WAYLAND_DISPLAY")
        or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
    ):
        return True
    return any(os.access(path, os.R_OK) for path in glob.glob("/dev/input/event*"))


def normalize_key_name(name: Optional[str]) -> str:
    if not name:
        return ""
    key = name.strip().lower()
    if key in _PYNPUT_NAMES:
        return _PYNPUT_NAMES[key]
    if key.startswith("key."):
        key = key[4:]
        return _PYNPUT_NAMES.get(key, key)
    return key


def _modifier_of(name: str) -> Optional[str]:
    if name.startswith("ctrl") or name == "control":
        return "ctrl"
    if name.startswith("shift"):
        return "shift"
    if name.startswith("alt"):
        return "alt"
    if name.startswith("cmd") or name.startswith("win") or name in {"super", "meta"}:
        return "win"
    return None


def parse_hotkey(spec: str) -> Tuple[Set[str], str]:
    """``"ctrl+shift+m"`` -> (``{"ctrl", "shift"}``, ``"m"``)."""
    parts = [part.strip().lower() for part in (spec or "").split("+") if part.strip()]
    if not parts:
        return set(), ""
    mods: Set[str] = set()
    key = parts[-1]
    alias = {
        "control": "ctrl",
        "ctl": "ctrl",
        "cmd": "win",
        "command": "win",
        "super": "win",
        "meta": "win",
        "windows": "win",
        "option": "alt",
    }
    for part in parts[:-1]:
        mods.add(alias.get(part, part))
    key = alias.get(key, key)
    return mods, key


class KeyboardMonitor:
    """Owns a single input backend and dispatches key events."""

    def __init__(
        self,
        on_key: Optional[KeyHandler] = None,
        on_hotkey: Optional[HotkeyHandler] = None,
        hotkey: str = "ctrl+shift+m",
        hotkey_enabled: bool = True,
    ):
        self.on_key = on_key
        self.on_hotkey = on_hotkey
        self.hotkey_mods, self.hotkey_key = parse_hotkey(hotkey)
        self.hotkey_enabled = hotkey_enabled and bool(self.hotkey_key)
        self.backend: Optional[str] = None
        self.error: Optional[str] = None

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._pressed: Set[str] = set()
        self._mods: Set[str] = set()
        self._last_hotkey = 0.0
        self._lock = threading.Lock()
        self._evdev_devices: list = []

    # ------------------------------------------------------------------ start
    def start(self) -> str:
        if self._thread is not None:
            return self.backend or "unknown"
        self._stop.clear()
        if sys.platform.startswith("linux"):
            if self._start_evdev():
                self.backend = "evdev"
                return self.backend
            if os.environ.get("WAYLAND_DISPLAY") or os.environ.get(
                "XDG_SESSION_TYPE", ""
            ).lower() == "wayland":
                message = (
                    "Global key input is not available on Wayland without read access to "
                    "/dev/input. Run: sudo usermod -aG input $USER, then log out and back in."
                )
                self.error = message
                raise InputUnavailable(message)
        if self._start_pynput():
            self.backend = "pynput"
            return self.backend
        raise InputUnavailable(self.error or "No keyboard backend available")

    def _start_evdev(self) -> bool:
        try:
            import evdev  # type: ignore
            from evdev import ecodes  # type: ignore
        except Exception as exc:
            log.debug("evdev unavailable: %s", exc)
            return False

        devices = []
        seen = set()
        try:
            paths = evdev.list_devices()
        except Exception:
            return False
        for path in paths:
            try:
                device = evdev.InputDevice(path)
                caps = device.capabilities()
                keys = caps.get(ecodes.EV_KEY, [])
                is_keyboard = (
                    ecodes.KEY_A in keys
                    and ecodes.KEY_ENTER in keys
                    and ecodes.KEY_SPACE in keys
                )
                if not is_keyboard:
                    device.close()
                    continue
                ident = getattr(device, "phys", "") or device.path
                if ident in seen:
                    device.close()
                    continue
                seen.add(ident)
                devices.append(device)
            except (PermissionError, OSError):
                continue
        if not devices:
            self.error = "No readable input devices (add your user to the 'input' group)."
            return False

        self._evdev_devices = devices
        self._thread = threading.Thread(target=self._evdev_loop, name="keyboard-evdev", daemon=True)
        self._thread.start()
        log.info("Keyboard backend: evdev (%d device(s))", len(devices))
        return True

    def _key_name_evdev(self, code: int) -> str:
        from evdev import ecodes  # type: ignore

        raw = ecodes.KEY.get(code, "")
        if raw in _EVDEV_NAMES:
            return _EVDEV_NAMES[raw]
        if raw.startswith("KEY_F") and raw[5:].isdigit():
            return raw[5:].lower()
        if len(raw) == 5 and raw.startswith("KEY_") and raw[4].isalpha():
            return raw[4].lower()
        if len(raw) == 5 and raw.startswith("KEY_") and raw[4].isdigit():
            return raw[4]
        return raw.replace("KEY_", "").lower()

    def _evdev_loop(self) -> None:
        from evdev import ecodes  # type: ignore

        devices = list(self._evdev_devices)
        try:
            while not self._stop.is_set():
                try:
                    ready, _, _ = select.select(devices, [], [], 0.25)
                except (OSError, ValueError):
                    break
                for device in ready:
                    try:
                        for event in device.read():
                            if event.type != ecodes.EV_KEY:
                                continue
                            if event.value == 2:  # autorepeat
                                continue
                            self._dispatch(
                                self._key_name_evdev(event.code), pressed=event.value == 1
                            )
                    except OSError:
                        try:
                            devices.remove(device)
                        except ValueError:
                            pass
        finally:
            for device in devices:
                try:
                    device.close()
                except Exception:
                    pass
            self._evdev_devices = []

    # ----------------------------------------------------------------- pynput
    def _start_pynput(self) -> bool:
        try:
            from pynput import keyboard  # type: ignore
        except Exception as exc:
            self.error = f"pynput is unavailable: {exc}"
            return False

        def on_press(key: object) -> None:
            self._dispatch(self._pynput_name(key), pressed=True)

        def on_release(key: object) -> None:
            self._dispatch(self._pynput_name(key), pressed=False)

        try:
            listener = keyboard.Listener(on_press=on_press, on_release=on_release)
            listener.daemon = True
            listener.start()
        except Exception as exc:
            self.error = f"Could not start the pynput listener: {exc}"
            return False
        self._pynput_listener = listener
        self._thread = listener
        log.info("Keyboard backend: pynput")
        return True

    @staticmethod
    def _pynput_name(key: object) -> str:
        try:
            char = getattr(key, "char", None)
            if char:
                return char.lower()
            name = getattr(key, "name", None)
            if name:
                return normalize_key_name(name)
            return normalize_key_name(str(key))
        except Exception:
            return ""

    # ---------------------------------------------------------------- dispatch
    def _dispatch(self, name: str, pressed: bool) -> None:
        if not name:
            return
        name = normalize_key_name(name)
        mod = _modifier_of(name)

        if mod:
            with self._lock:
                if pressed:
                    self._mods.add(mod)
                else:
                    self._mods.discard(mod)

        if pressed:
            with self._lock:
                duplicate = name in self._pressed
                self._pressed.add(name)
                mods = set(self._mods)
            if not duplicate:
                if self.on_key is not None:
                    try:
                        self.on_key(name)
                    except Exception:
                        log.exception("on_key handler failed")
                self._maybe_hotkey(name, mods)
        else:
            with self._lock:
                self._pressed.discard(name)

    def _maybe_hotkey(self, name: str, mods: Set[str]) -> None:
        if not self.hotkey_enabled or self.on_hotkey is None:
            return
        if name in MODIFIER_NAMES or _modifier_of(name):
            return
        if mods != self.hotkey_mods or name != self.hotkey_key:
            return
        now = time.monotonic()
        if now - self._last_hotkey < 0.4:
            return
        self._last_hotkey = now
        try:
            self.on_hotkey()
        except Exception:
            log.exception("hotkey handler failed")

    # ------------------------------------------------------------------- stop
    def stop(self) -> None:
        self._stop.set()
        for device in list(self._evdev_devices):
            try:
                device.close()
            except Exception:
                pass
        listener = getattr(self, "_pynput_listener", None)
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            try:
                thread.join(timeout=1.0)
            except RuntimeError:
                pass
        self._thread = None
        self._evdev_devices = []
        with self._lock:
            self._pressed.clear()
            self._mods.clear()
        self.backend = None

    @property
    def zone_of(self) -> Callable[[str], int]:
        return zone_for_key

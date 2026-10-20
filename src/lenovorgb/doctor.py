"""`lenovorgb doctor` - one command that explains why things do or do not work."""

from __future__ import annotations

import glob
import logging
import os
import platform
import sys
from pathlib import Path
from typing import List

from . import __version__
from .config import Config
from .constants import KNOWN_PIDS
from .device import enumerate_devices
from .lock import InstanceLock
from .paths import config_file, log_file

OK = "[ ok ]"
WARN = "[ !! ]"
INFO = "[ -- ]"


def _line(status: str, text: str) -> str:
    return f"  {status} {text}"


def _udev_installed() -> bool:
    patterns = [
        "/etc/udev/rules.d/*lenovorgb*",
        "/usr/lib/udev/rules.d/*lenovorgb*",
        "/run/udev/rules.d/*lenovorgb*",
    ]
    return any(glob.glob(pattern) for pattern in patterns)


def _readable_inputs() -> int:
    count = 0
    for path in glob.glob("/dev/input/event*"):
        if os.access(path, os.R_OK):
            count += 1
    return count


def _tkinter_status() -> str:
    try:
        import tkinter  # noqa: F401

        return OK + " tkinter available"
    except Exception as exc:
        return WARN + f" tkinter missing ({exc}); install python3-tk"


def _session_type() -> str:
    if os.name == "nt":
        return "Windows"
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session:
        return session.upper()
    if os.environ.get("WAYLAND_DISPLAY"):
        return "Wayland"
    if os.environ.get("DISPLAY"):
        return "X11"
    if sys.platform == "darwin":
        return "macOS"
    return "unknown"


def collect(config: Config) -> str:
    lines: List[str] = []
    lines.append(f"Lenovo RGB {__version__} diagnostics")
    lines.append("=" * 46)
    lines.append(f"OS:        {platform.platform()}")
    lines.append(f"Session:   {_session_type()}")
    lines.append(f"Python:    {sys.version.split()[0]} ({sys.executable})")
    lines.append(f"Config:    {config_file()}")
    lines.append(f"Log:       {log_file()}")
    lines.append("")

    # ------------------------------------------------------------- hardware
    lines.append("Keyboard")
    devices = enumerate_devices()
    if devices:
        for info in devices:
            lines.append(_line(OK, info.label))
        best = devices[0]
        if sys.platform.startswith("linux"):
            best_path = best.path.decode(errors="replace") if isinstance(best.path, bytes) else str(best.path)
            readable = os.access(best_path, os.R_OK | os.W_OK)
            if readable:
                lines.append(_line(OK, "HID interface is readable and writable"))
            else:
                lines.append(
                    _line(
                        WARN,
                        "HID interface is not accessible by this user "
                        "(install the udev rule or re-login)",
                    )
                )
    else:
        lines.append(
            _line(
                WARN,
                "No supported Lenovo RGB keyboard found. "
                "Check that the model has 4-zone RGB and that Vantage has not disabled it.",
            )
        )
        lines.append(
            _line(
                INFO,
                "Supported IDs: " + ", ".join(f"048d:{pid:04x}" for pid in KNOWN_PIDS),
            )
        )

    if sys.platform.startswith("linux"):
        if _udev_installed():
            lines.append(_line(OK, "udev rule is installed"))
        else:
            lines.append(
                _line(
                    WARN,
                    "udev rule missing - run ./install.sh or copy packaging/99-lenovorgb.rules",
                )
            )

    # ---------------------------------------------------------------- input
    lines.append("")
    lines.append("Input")
    if sys.platform.startswith("linux"):
        readable = _readable_inputs()
        if readable:
            lines.append(_line(OK, f"{readable} readable /dev/input device(s) (evdev)"))
        else:
            lines.append(
                _line(
                    WARN,
                    "No readable /dev/input devices. Reactive modes on Wayland need: "
                    "sudo usermod -aG input $USER (then log out)",
                )
            )
    lines.append(_tkinter_status())

    # ---------------------------------------------------------------- audio
    lines.append("")
    lines.append("Audio")
    try:
        from .inputs.audio import probe

        ok, detail = probe()
        lines.append(_line(OK if ok else WARN, detail))
    except Exception as exc:
        lines.append(_line(WARN, f"Audio probe failed: {exc}"))

    # --------------------------------------------------------------- screen
    lines.append("")
    lines.append("Screen capture")
    try:
        from .inputs.screen import probe as screen_probe

        ok, detail = screen_probe()
        lines.append(_line(OK if ok else WARN, detail))
    except Exception as exc:
        lines.append(_line(WARN, f"Screen probe failed: {exc}"))

    # ------------------------------------------------------------ instance
    lines.append("")
    lines.append("Runtime")
    probe_lock = InstanceLock()
    if probe_lock.acquire():
        probe_lock.release()
        lines.append(_line(OK, "No other LenovoRGB instance is running"))
    else:
        lines.append(_line(INFO, probe_lock.busy_message().splitlines()[0]))
    lines.append(_line(INFO, f"Configured default mode: {config.get('default_mode')}"))
    lines.append(_line(INFO, f"Brightness: {config.brightness}%"))

    # ------------------------------------------------------------------ log
    try:
        if Path(log_file()).is_file():
            tail = log_file().read_text(encoding="utf-8", errors="replace").splitlines()[-12:]
            if tail:
                lines.append("")
                lines.append("Recent log")
                lines.extend("  " + entry for entry in tail)
    except OSError:
        pass

    lines.append("")
    lines.append("If something is still broken, open an issue with this output:")
    lines.append("https://github.com/Shushant17711/LenovoRGB/issues")
    return "\n".join(lines)


def run(config: Config) -> int:
    logging.getLogger("lenovorgb").setLevel(logging.WARNING)
    print(collect(config))
    return 0

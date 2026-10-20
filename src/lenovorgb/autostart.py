"""Launch-at-login support for Linux, Windows and macOS."""

from __future__ import annotations

import os
import plistlib
import re
import sys
from pathlib import Path
from typing import List, Tuple

DESKTOP_FILE = "lenovorgb.desktop"
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOWS_VALUE = "LenovoRGB"


def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def launch_command(minimized: bool = True) -> List[str]:
    """Command that starts the tray app (no console where possible)."""
    if _frozen():
        command = [sys.executable]
        command.append("gui")
    else:
        executable = sys.executable
        if os.name == "nt":
            candidate = Path(executable).with_name("pythonw.exe")
            if candidate.is_file():
                executable = str(candidate)
        command = [executable, "-m", "lenovorgb", "gui"]
    if minimized:
        command.append("--minimized")
    return command


def _icon_path() -> str:
    try:
        from importlib.resources import files

        icon = files("lenovorgb").joinpath("assets/icon.png")
        if icon.is_file():
            return str(icon)
    except Exception:
        pass
    return ""


def _desktop_quote(argument: str) -> str:
    if argument and not re.search(r"[ \t\n\"'\\><~|&;$*?#()`]", argument):
        return argument
    escaped = (
        argument.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )
    return f'"{escaped}"'


def desktop_entry(minimized: bool = True) -> str:
    exec_line = " ".join(_desktop_quote(part) for part in launch_command(minimized))
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=Lenovo RGB",
        "GenericName=Keyboard Lighting",
        "Comment=Control the 4-zone RGB keyboard on Lenovo LOQ and Legion laptops",
        f"Exec={exec_line}",
        "Terminal=false",
        "Categories=Utility;Settings;HardwareSettings;",
        "Keywords=rgb;keyboard;lenovo;loq;legion;lighting;",
        "StartupNotify=false",
    ]
    icon = _icon_path()
    if icon:
        lines.insert(5, f"Icon={icon}")
    return "\n".join(lines) + "\n"


def _linux_autostart_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / DESKTOP_FILE


def _linux_menu_file() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "applications" / DESKTOP_FILE


def enable(minimized: bool = True) -> Tuple[bool, str]:
    if os.name == "nt":
        return _enable_windows(minimized)
    if sys.platform == "darwin":
        return _enable_macos(minimized)
    return _enable_linux(minimized)


def disable() -> Tuple[bool, str]:
    if os.name == "nt":
        return _disable_windows()
    if sys.platform == "darwin":
        return _disable_macos()
    return _disable_linux()


def is_enabled() -> bool:
    if os.name == "nt":
        return _windows_value() is not None
    if sys.platform == "darwin":
        return _macos_plist().is_file()
    return _linux_autostart_file().is_file()


def status() -> Tuple[bool, str]:
    enabled = is_enabled()
    if os.name == "nt":
        detail = _windows_value() or "registry value not set"
    elif sys.platform == "darwin":
        detail = str(_macos_plist())
    else:
        detail = str(_linux_autostart_file())
    return enabled, detail


# ------------------------------------------------------------------- Linux
def _enable_linux(minimized: bool) -> Tuple[bool, str]:
    entry = desktop_entry(minimized)
    autostart = _linux_autostart_file()
    menu = _linux_menu_file()
    try:
        autostart.parent.mkdir(parents=True, exist_ok=True)
        autostart.write_text(entry, encoding="utf-8")
        menu.parent.mkdir(parents=True, exist_ok=True)
        # Launching from the application menu should open the window, not
        # start hidden in the tray.
        menu.write_text(desktop_entry(minimized=False), encoding="utf-8")
        try:
            menu.chmod(0o755)
        except OSError:
            pass
        return True, f"Autostart enabled: {autostart}"
    except OSError as exc:
        return False, f"Could not write {autostart}: {exc}"


def write_menu_entry() -> Tuple[bool, str]:
    """Add the app to the desktop application menu (without autostart)."""
    if os.name == "nt":
        return True, "Use install.ps1 to create a Start Menu shortcut"
    if sys.platform == "darwin":
        return True, "macOS applications are launched from Python"
    menu = _linux_menu_file()
    try:
        menu.parent.mkdir(parents=True, exist_ok=True)
        menu.write_text(desktop_entry(minimized=False), encoding="utf-8")
        try:
            menu.chmod(0o755)
        except OSError:
            pass
        return True, f"Menu entry installed: {menu}"
    except OSError as exc:
        return False, f"Could not write {menu}: {exc}"


def remove_menu_entry() -> Tuple[bool, str]:
    if os.name == "nt" or sys.platform == "darwin":
        return True, "Nothing to remove"
    menu = _linux_menu_file()
    try:
        menu.unlink()
        return True, f"Menu entry removed: {menu}"
    except FileNotFoundError:
        return True, "No menu entry was installed"
    except OSError as exc:
        return False, f"Could not remove {menu}: {exc}"


def _disable_linux() -> Tuple[bool, str]:
    removed = []
    for path in (_linux_autostart_file(),):
        try:
            path.unlink()
            removed.append(str(path))
        except FileNotFoundError:
            continue
        except OSError as exc:
            return False, f"Could not remove {path}: {exc}"
    return True, "Autostart disabled" if removed else "Autostart was not enabled"


# ----------------------------------------------------------------- Windows
def _windows_command(minimized: bool) -> str:
    return subprocess_list_to_string(launch_command(minimized))


def subprocess_list_to_string(command: List[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def _enable_windows(minimized: bool) -> Tuple[bool, str]:
    import winreg

    command = _windows_command(minimized)
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, WINDOWS_VALUE, 0, winreg.REG_SZ, command)
        return True, f"Autostart enabled (HKCU Run): {command}"
    except OSError as exc:
        return False, f"Could not write the Run registry key: {exc}"


def _disable_windows() -> Tuple[bool, str]:
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, WINDOWS_VALUE)
        return True, "Autostart disabled"
    except FileNotFoundError:
        return True, "Autostart was not enabled"
    except OSError as exc:
        return False, f"Could not update the Run registry key: {exc}"


def _windows_value() -> str:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, WINDOWS_VALUE)
            return str(value)
    except OSError:
        return ""


# ------------------------------------------------------------------- macOS
def _macos_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / "com.lenovorgb.app.plist"


def _enable_macos(minimized: bool) -> Tuple[bool, str]:
    path = _macos_plist()
    payload = {
        "Label": "com.lenovorgb.app",
        "ProgramArguments": launch_command(minimized),
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": str(Path.home() / "Library" / "Logs" / "LenovoRGB" / "out.log"),
        "StandardErrorPath": str(Path.home() / "Library" / "Logs" / "LenovoRGB" / "err.log"),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(plistlib.dumps(payload))
        return True, f"Launch agent written to {path}"
    except OSError as exc:
        return False, f"Could not write {path}: {exc}"


def _disable_macos() -> Tuple[bool, str]:
    try:
        _macos_plist().unlink()
        return True, "Autostart disabled"
    except FileNotFoundError:
        return True, "Autostart was not enabled"
    except OSError as exc:
        return False, f"Could not remove the launch agent: {exc}"

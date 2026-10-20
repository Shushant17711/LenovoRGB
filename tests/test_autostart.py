from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from lenovorgb import autostart


def test_launch_command_shape():
    command = autostart.launch_command(minimized=True)
    assert "-m" in command or command[0].endswith(".exe")
    assert "gui" in command or any(part.endswith("gui") for part in command)
    assert command[-1] == "--minimized"
    assert "--minimized" not in autostart.launch_command(minimized=False)


def test_desktop_entry_contents():
    entry = autostart.desktop_entry(minimized=True)
    assert entry.startswith("[Desktop Entry]")
    assert "Name=Lenovo RGB" in entry
    assert "Exec=" in entry
    assert "Terminal=false" in entry
    assert "--minimized" in entry


def test_desktop_entry_quotes_spaces():
    assert autostart._desktop_quote("/usr/bin/python3") == "/usr/bin/python3"
    assert autostart._desktop_quote("/home/a b/python") == '"/home/a b/python"'
    assert autostart._desktop_quote('/home/a"b') == '"/home/a\\"b"'


@pytest.mark.skipif(sys.platform != "linux", reason="Linux autostart only")
def test_enable_and_disable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    ok, message = autostart.enable(minimized=True)
    assert ok, message
    autostart_file = tmp_path / "config" / "autostart" / "lenovorgb.desktop"
    menu_file = tmp_path / "data" / "applications" / "lenovorgb.desktop"
    assert autostart_file.is_file()
    assert menu_file.is_file()
    assert autostart.is_enabled()
    assert "--minimized" in autostart_file.read_text(encoding="utf-8")
    assert "--minimized" not in menu_file.read_text(encoding="utf-8")

    ok, _message = autostart.disable()
    assert ok
    assert not autostart_file.exists()
    assert not autostart.is_enabled()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux menu entry only")
def test_menu_entry_round_trip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    ok, _ = autostart.write_menu_entry()
    assert ok
    menu_file = tmp_path / "data" / "applications" / "lenovorgb.desktop"
    assert menu_file.is_file()
    assert os.access(menu_file, os.R_OK)
    ok, _ = autostart.remove_menu_entry()
    assert ok
    assert not menu_file.exists()


@pytest.mark.skipif(sys.platform == "linux", reason="Windows/macOS path")
def test_status_returns_tuple():
    enabled, detail = autostart.status()
    assert isinstance(enabled, bool)
    assert isinstance(detail, str)

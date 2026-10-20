from __future__ import annotations

import sys
from pathlib import Path

import pytest

from lenovorgb import paths


@pytest.mark.skipif(sys.platform != "linux", reason="XDG paths")
def test_config_and_state_dirs_follow_xdg(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    assert paths.config_dir() == tmp_path / "cfg" / "lenovorgb"
    assert paths.state_dir() == tmp_path / "state" / "lenovorgb"
    assert paths.config_file().parent == paths.config_dir()
    assert paths.log_file().parent == paths.state_dir()
    assert paths.lock_file().name == "instance.lock"


@pytest.mark.skipif(sys.platform != "linux", reason="XDG paths")
def test_ensure_dirs_creates_both(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    paths.ensure_dirs()
    assert paths.config_dir().is_dir()
    assert paths.state_dir().is_dir()


def test_legacy_candidates_are_files():
    for candidate in paths.legacy_config_candidates():
        assert candidate.is_file()

from __future__ import annotations

import json

import pytest

from lenovorgb.cli import _translate_legacy, build_parser, main


def test_parser_accepts_commands():
    parser = build_parser()
    assert parser.parse_args(["list"]).command == "list"
    assert parser.parse_args(["gui", "--minimized"]).minimized is True
    assert parser.parse_args(["run", "aurora", "--demo"]).mode == "aurora"
    assert parser.parse_args(["autostart", "enable"]).action == "enable"


def test_legacy_mode_argument_is_translated():
    assert _translate_legacy(["--mode", "fire"]) == ["run", "fire"]
    assert _translate_legacy(["--mode", "cpu", "--demo"]) == ["run", "cpu", "--demo"]
    assert _translate_legacy(["--list-modes"]) == ["list"]
    assert _translate_legacy(["run", "fire"]) == ["run", "fire"]


def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        build_parser().parse_args(["--version"])
    assert excinfo.value.code == 0
    assert "LenovoRGB" in capsys.readouterr().out


def test_list_json(capsys):
    assert main(["list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    ids = {item["id"] for item in payload}
    assert {"type", "audio", "screen", "solid", "off"} <= ids
    assert all(item["name"] and item["description"] for item in payload)


def test_list_human(capsys):
    assert main(["list"]) == 0
    output = capsys.readouterr().out
    assert "REACTIVE" in output
    assert "Aurora" in output
    assert "lenovorgb run" in output


def test_unknown_mode_fails_before_touching_hardware(capsys):
    assert main(["run", "definitely-not-a-mode", "--demo"]) == 2
    assert "Unknown mode" in capsys.readouterr().err


def test_unknown_command():
    with pytest.raises(SystemExit):
        main(["frobnicate"])


def test_solid_sets_and_persists_colour(capsys):
    assert main(["solid", "#ff5500", "--demo"]) == 0
    assert "ff5500" in capsys.readouterr().out
    from lenovorgb.config import Config

    assert Config().get("static_color") == "#ff5500"


def test_solid_rejects_invalid_colour(capsys):
    assert main(["solid", "not-a-colour", "--demo"]) == 2
    assert "Invalid colour" in capsys.readouterr().err


def test_run_off_exits_immediately(capsys):
    assert main(["run", "off", "--demo"]) == 0
    assert "off" in capsys.readouterr().out.lower()

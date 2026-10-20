from __future__ import annotations

import threading
import time

import pytest

import lenovorgb.engine as engine_module
from lenovorgb.engine import ERROR, IDLE, RUNNING, LightingEngine
from lenovorgb.modes.base import Mode


class FakeDevice:
    def __init__(self):
        self.info = None
        self.brightness = 100.0
        self.frames = []
        self.lock = threading.Lock()

    def set_brightness(self, percent):
        self.brightness = percent

    def set_colors(self, colors, force=False):
        with self.lock:
            self.frames.append(list(colors))

    def close(self):
        pass


def wait_for(predicate, timeout=3.0, interval=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.fixture
def engine(config):
    device = FakeDevice()
    instance = LightingEngine(device, config)
    yield instance, device
    instance.shutdown(off=True)


def test_engine_runs_a_mode(engine):
    instance, device = engine
    assert instance.set_mode("breathing")
    assert wait_for(lambda: instance.state == RUNNING)
    assert wait_for(lambda: any(max(color) > 0 for color in instance.colors))

    with device.lock:
        assert len(device.frames) > 0

    instance.stop()
    assert instance.state == IDLE


def test_engine_switches_modes(engine):
    instance, device = engine
    instance.set_mode("aurora")
    assert wait_for(lambda: instance.state == RUNNING)

    instance.set_mode("solid", {"color": "#ff0000"})
    assert wait_for(
        lambda: instance.state == RUNNING and instance.colors[0] == (255, 0, 0), timeout=3.0
    )
    assert instance.mode_id == "solid"


def test_engine_reports_errors(monkeypatch, engine):
    instance, _device = engine

    class Boom(Mode):
        id = "boom"
        name = "Boom"
        description = "always fails"
        interval = 0.01

        def setup(self):
            raise ValueError("kersplat")

    monkeypatch.setattr(engine_module, "get_mode", lambda mode_id: Boom)
    instance.set_mode("boom")
    assert wait_for(lambda: instance.state == ERROR)
    assert "kersplat" in (instance.error or "")


def test_engine_rejects_unknown_mode(engine):
    instance, _device = engine
    with pytest.raises(KeyError):
        instance.set_mode("nope")


def test_engine_brightness_is_applied(engine):
    instance, device = engine
    instance.set_mode("solid", {"color": "#ffffff"})
    assert wait_for(lambda: instance.state == RUNNING)
    instance.set_brightness(50)
    assert device.brightness == 50
    assert instance.config.brightness == 50
    assert wait_for(lambda: instance.colors[0][0] <= 128, timeout=2.0)

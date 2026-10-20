from __future__ import annotations

import threading
import time

import pytest

import lenovorgb.engine as engine_module
from lenovorgb.engine import (
    ERROR,
    IDLE,
    RUNNING,
    LightingEngine,
    _next_interval,
)
from lenovorgb.modes.base import Mode


class FakeDevice:
    def __init__(self):
        self.info = None
        self.brightness = 100.0
        self.frames = []
        self.forces = []
        self.lock = threading.Lock()

    def set_brightness(self, percent):
        self.brightness = percent

    def set_colors(self, colors, force=False):
        with self.lock:
            self.frames.append(list(colors))
            self.forces.append(bool(force))

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


def test_idle_interval_backs_off_without_making_fast_modes_slower():
    assert _next_interval(0.016, 0) == 0.016
    assert _next_interval(0.016, 5) == 0.016
    assert _next_interval(0.016, 6) == 0.1
    assert _next_interval(0.5, 6) == 0.25


def test_engine_forces_one_redraw_after_resume(monkeypatch, engine):
    instance, device = engine
    clock = [100.0]

    class FakeTime:
        @staticmethod
        def perf_counter():
            return time.perf_counter()

        @staticmethod
        def time():
            return clock[0]

    class Static(Mode):
        id = "static"
        name = "Static"
        description = "constant frame"
        interval = 0.01

        def step(self, dt):
            return [(10, 20, 30)] * 4

    monkeypatch.setattr(engine_module, "time", FakeTime)
    monkeypatch.setattr(engine_module, "get_mode", lambda mode_id: Static)
    instance.set_mode("static")
    assert wait_for(lambda: instance.state == RUNNING)
    assert wait_for(lambda: len(device.forces) >= 2)

    clock[0] += 5.0
    assert wait_for(lambda: any(device.forces[2:]), timeout=2.0)

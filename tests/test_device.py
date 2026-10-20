from __future__ import annotations

import pytest

from lenovorgb import constants
from lenovorgb.device import (
    PAYLOAD_LENGTH,
    DeviceInfo,
    DeviceNotFound,
    RGBDevice,
    build_payload,
    enumerate_devices,
    select_candidates,
)


def test_payload_layout():
    payload = build_payload([(1, 2, 3), (4, 5, 6), (7, 8, 9), (10, 11, 12)])
    assert len(payload) == PAYLOAD_LENGTH == 33
    assert payload[0] == 0xCC
    assert payload[1] == 0x16
    assert payload[2] == 0x01
    assert payload[3] == 0x01
    assert payload[4] == 1
    assert payload[5:8] == bytes([1, 2, 3])
    assert payload[8:11] == bytes([4, 5, 6])
    assert payload[14:17] == bytes([10, 11, 12])
    assert payload[17:] == bytes(16)


def test_payload_clamps_out_of_range_values():
    payload = build_payload([(-5, 300, 12), (0, 0, 0), (0, 0, 0), (0, 0, 0)])
    assert payload[5:8] == bytes([0, 255, 12])


def test_payload_handles_short_input():
    payload = build_payload([(10, 20, 30)])
    assert payload[5:8] == bytes([10, 20, 30])
    assert payload[8:17] == bytes(9)


def test_device_info_label():
    info = DeviceInfo(path=b"/dev/hidraw3", vendor_id=0x048D, product_id=0xC993, product_string="")
    assert "048d:c993" in info.label


def test_enumerate_devices_returns_list():
    assert isinstance(enumerate_devices(), list)


def test_dry_run_device_applies_brightness():
    device = RGBDevice(dry_run=True, brightness=50)
    device.set_colors([(255, 100, 10)] * 4)
    assert device.last_frame is not None
    assert device.last_frame[0] == (127, 50, 5)


def test_dry_run_off_is_black():
    device = RGBDevice(dry_run=True)
    device.set_colors([(255, 255, 255)] * 4)
    device.off()
    assert device.last_frame == [(0, 0, 0)] * 4


def test_missing_device_raises(monkeypatch):
    monkeypatch.delenv("LENOVORGB_FAKE_DEVICE", raising=False)
    with pytest.raises(DeviceNotFound):
        RGBDevice(product_id=0x0001, dry_run=False)


def test_known_pids_are_unique():
    assert len(constants.KNOWN_PIDS) == len(set(constants.KNOWN_PIDS))


def _entry(path, pid=0xC993, page=0xFF89, usage=0xCC, interface=0):
    return {
        "path": path,
        "vendor_id": 0x048D,
        "product_id": pid,
        "usage_page": page,
        "usage": usage,
        "interface_number": interface,
    }


def test_select_candidates_prefers_rgb_collection():
    entries = [
        _entry(b"/dev/hidraw0", usage=0x10),
        _entry(b"/dev/hidraw0", usage=0xCC),
        _entry(b"/dev/hidraw1", page=0xFFC2, usage=0x04),
    ]
    selected = select_candidates(entries)
    assert len(selected) == 1
    assert selected[0]["path"] == b"/dev/hidraw0"
    assert selected[0]["usage"] == 0xCC


def test_select_candidates_rejects_unrelated_devices():
    entries = [_entry(b"/dev/hidraw1", page=0xFFC2, usage=0x04)]
    assert select_candidates(entries) == []


def test_select_candidates_handles_zero_usage_backends():
    entries = [_entry(b"1-7:1.0", page=0, usage=0), _entry(b"1-7:1.1", page=0, usage=0)]
    selected = select_candidates(entries)
    assert len(selected) == 2


def test_select_candidates_ignores_unknown_pids():
    entries = [_entry(b"/dev/hidraw9", pid=0xC996)]
    assert select_candidates(entries) == []


class _FakeHandle:
    def __init__(self):
        self.payloads = []

    def send_feature_report(self, payload):
        self.payloads.append(bytes(payload))
        return len(payload)

    def close(self):
        pass


def test_unchanged_frames_do_not_touch_usb():
    """Regression test for the idle-blinking report (issue #1).

    The keyboard firmware treats every feature report as a new event, so
    repeating an identical all-black payload made idle LEDs blink faster and
    faster. set_colors must suppress duplicate payloads unless forced.
    """
    device = RGBDevice(dry_run=True)
    handle = _FakeHandle()
    device.dry_run = False
    device._device = handle
    frame = [(10, 20, 30)] * 4

    device.set_colors(frame)
    device.set_colors(frame)
    device.set_colors([(10, 20, 30.4)] * 4)  # rounds to the same bytes
    assert len(handle.payloads) == 1

    device.set_colors([(11, 20, 30)] * 4)
    assert len(handle.payloads) == 2

    device.set_colors([(11, 20, 30)] * 4, force=True)
    assert len(handle.payloads) == 3

    device.set_brightness(50)
    device.set_colors([(11, 20, 30)] * 4)
    assert len(handle.payloads) == 4

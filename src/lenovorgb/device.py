"""Low-level access to the Lenovo 4-zone RGB HID interface."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import List, Optional

from . import constants
from .colors import normalize_frame

log = logging.getLogger("lenovorgb.device")

_BACKEND = None


def _backend():
    """Return the best hidapi backend for this OS.

    On Linux the package ships two modules: ``hid`` (libusb) and ``hidraw``.
    Only ``hidraw`` reports the vendor usage page/usage needed to tell the
    RGB interface apart, and it operates on /dev/hidraw* which is what our
    udev rule targets.
    """
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    if sys.platform.startswith("linux"):
        try:
            import hidraw  # type: ignore

            _BACKEND = hidraw
            return _BACKEND
        except Exception:
            pass
    try:
        import hid  # type: ignore

        _BACKEND = hid
    except Exception:  # pragma: no cover - only on broken installs
        _BACKEND = None
    return _BACKEND


PAYLOAD_LENGTH = 33
HW_BRIGHTNESS = 1  # value understood by the EC; 1 = normal, 2 = bright


class DeviceError(RuntimeError):
    """The keyboard could not be opened or written to."""


class DeviceNotFound(DeviceError):
    pass


class PermissionDenied(DeviceError):
    pass


@dataclass(frozen=True)
class DeviceInfo:
    path: object
    vendor_id: int
    product_id: int
    usage_page: int = 0
    usage: int = 0
    interface_number: int = -1
    product_string: str = ""
    manufacturer_string: str = ""

    @property
    def name(self) -> str:
        return self.product_string or self.manufacturer_string or "Lenovo RGB keyboard"

    @property
    def label(self) -> str:
        pid = f"{self.product_id:04x}"
        return f"{self.name} ({constants.VENDOR_ID:04x}:{pid})"


def build_payload(colors: Sequence[Sequence[float]]) -> bytes:
    """Build the 33-byte feature report.

    Layout (byte indexes):
        0      report ID            0xCC
        1      command              0x16 (custom/static)
        2      submode              0x01
        3      speed                0x01
        4      hardware brightness  0x01
        5-16   zone 0..3 as RGB triplets
        17-32  unused
    """
    payload = bytearray(PAYLOAD_LENGTH)
    payload[0] = constants.REPORT_ID
    payload[1] = constants.CMD_STATIC
    payload[2] = constants.SUB_STATIC
    payload[3] = 0x01
    payload[4] = HW_BRIGHTNESS
    for zone in range(constants.ZONE_COUNT):
        color = colors[zone] if zone < len(colors) else (0, 0, 0)
        red, green, blue = (int(color[0]), int(color[1]), int(color[2]))
        base = 5 + zone * 3
        payload[base] = max(0, min(255, red))
        payload[base + 1] = max(0, min(255, green))
        payload[base + 2] = max(0, min(255, blue))
    return bytes(payload)


def _score(entry: dict) -> tuple:
    page = int(entry.get("usage_page") or 0)
    usage = int(entry.get("usage") or 0)
    interface = int(entry.get("interface_number") or -1)
    return (
        page == constants.RGB_USAGE_PAGE,
        usage == constants.RGB_USAGE,
        usage == 0x10,
        interface == 0,
    )


def select_candidates(entries: list) -> list:
    """Pick the entries that belong to the RGB interface.

    Several HID collections can share one /dev/hidraw node, so entries are
    grouped by path and the best collection wins. When the backend reports
    real usage pages (hidraw/Windows), anything that is not the vendor page
    is discarded so we never write a lighting payload to a touchpad.
    """
    pids = set(constants.usb_product_ids())
    groups: dict = {}
    for entry in entries:
        try:
            if int(entry.get("product_id") or 0) not in pids:
                continue
        except (TypeError, ValueError):
            continue
        path = entry.get("path")
        if path is None:
            continue
        if path not in groups or _score(entry) > _score(groups[path]):
            groups[path] = entry

    candidates = list(groups.values())
    if not candidates:
        return []

    if any(int(entry.get("usage_page") or 0) for entry in candidates):
        vendor = [
            entry
            for entry in candidates
            if int(entry.get("usage_page") or 0) == constants.RGB_USAGE_PAGE
        ]
        if not vendor:
            # The backend reports real usage pages, none of which is the
            # Lenovo lighting collection. Never write to an unrelated HID node.
            return []
        exact = [entry for entry in vendor if int(entry.get("usage") or 0) == constants.RGB_USAGE]
        candidates = exact or vendor

    candidates.sort(key=_score, reverse=True)
    return candidates


def enumerate_devices() -> List[DeviceInfo]:
    """Return candidate RGB interfaces, best match first."""
    backend = _backend()
    if backend is None:
        return []
    try:
        raw = list(backend.enumerate())
    except Exception as exc:  # pragma: no cover - platform backend issues
        log.debug("HID enumeration failed: %s", exc)
        return []

    devices: List[DeviceInfo] = []
    for entry in select_candidates(raw):
        devices.append(
            DeviceInfo(
                path=entry.get("path"),
                vendor_id=entry.get("vendor_id", constants.VENDOR_ID),
                product_id=entry.get("product_id", 0),
                usage_page=entry.get("usage_page", 0) or 0,
                usage=entry.get("usage", 0) or 0,
                interface_number=entry.get("interface_number", -1) or -1,
                product_string=entry.get("product_string") or "",
                manufacturer_string=entry.get("manufacturer_string") or "",
            )
        )
    return devices


class RGBDevice:
    """Thread-safe wrapper around one hidapi device.

    ``dry_run`` keeps the full code path (including payload generation) but
    only logs frames. It is used by the UI when no keyboard is attached and
    by ``lenovorgb run ... --dry-run``.
    """

    def __init__(
        self,
        path: Optional[object] = None,
        product_id: Optional[int] = None,
        dry_run: bool = False,
        brightness: float = 100.0,
    ):
        self.info: Optional[DeviceInfo] = None
        self.dry_run = dry_run
        self.brightness = float(brightness)
        self.last_frame: Optional[List[tuple]] = None
        self._device = None
        self._lock = threading.Lock()
        self._frames = 0
        self._path = path
        self._product_id = product_id
        if not dry_run:
            try:
                self.open()
            except BaseException:
                self.close()
                raise

    # ------------------------------------------------------------------ open
    def open(self) -> None:
        candidates = enumerate_devices()
        if self._path is not None:
            candidates = [c for c in candidates if c.path == self._path] or candidates
        if self._product_id is not None:
            candidates = [c for c in candidates if c.product_id == self._product_id]
        if not candidates:
            raise DeviceNotFound(self._missing_message())

        errors: List[str] = []
        backend = _backend()
        for info in candidates:
            if backend is None:
                raise DeviceError("The 'hidapi' package is not installed.")
            path_text = ""
            if isinstance(info.path, bytes):
                path_text = info.path.decode(errors="replace")
            elif isinstance(info.path, str):
                path_text = info.path
            if path_text.startswith("/dev/") and not os.access(path_text, os.R_OK | os.W_OK):
                errors.append(f"{info.label}: no read/write permission on {path_text}")
                log.debug("Permission denied for %s", path_text)
                continue
            handle = backend.device()
            try:
                handle.open_path(info.path)
            except Exception as exc:
                message = str(exc)
                errors.append(f"{info.label}: {message}")
                if "permission" in message.lower() or "access" in message.lower():
                    log.debug("Permission denied for %s", info.path)
                continue
            self._device = handle
            self.info = info
            try:
                handle.set_nonblocking(0)
            except Exception:
                pass
            try:
                # Probe with a black frame to confirm this is the lighting
                # interface before committing to it.
                self._send(
                    build_payload([(0, 0, 0)] * constants.ZONE_COUNT),
                    allow_reopen=False,
                )
            except DeviceError as exc:
                errors.append(f"{info.label}: {exc}")
                self.close()
                continue
            # Force the next frame to be written after a reconnect; the probe
            # above left the keyboard black.
            self.last_frame = None
            log.info("Connected to %s", info.label)
            return

        if errors and all(
            "permission" in error.lower()
            or "read/write" in error.lower()
            or "access" in error.lower()
            for error in errors
        ):
            raise PermissionDenied(self._permission_message(errors))
        raise DeviceNotFound(self._missing_message(errors))

    def _missing_message(self, errors: Optional[List[str]] = None) -> str:
        hint = (
            "No Lenovo 4-zone RGB keyboard was found.\n"
            f"Supported USB IDs: {constants.VENDOR_ID:04x}:<pid> where pid is one of "
            + ", ".join(f"{pid:04x}" for pid in constants.KNOWN_PIDS)
            + ".\n"
        )
        if errors:
            hint += "Interfaces reported errors:\n  " + "\n  ".join(errors) + "\n"
        hint += "Run 'lenovorgb doctor' for diagnostics."
        return hint

    @staticmethod
    def _permission_message(errors: List[str]) -> str:
        return (
            "The RGB interface was found but could not be opened (permission denied).\n"
            "On Linux install the bundled udev rule, then re-plug the keyboard or reboot:\n"
            "  sudo install -m644 packaging/99-lenovorgb.rules /etc/udev/rules.d/\n"
            "  sudo udevadm control --reload-rules && sudo udevadm trigger\n"
            f"Details: {'; '.join(errors)}"
        )

    # ----------------------------------------------------------------- write
    def set_brightness(self, percent: float) -> None:
        self.brightness = max(0.0, min(100.0, float(percent)))

    def set_colors(self, colors: Iterable[Sequence[float]], force: bool = False) -> None:
        frame = normalize_frame(colors, self.brightness)
        if not force and frame == self.last_frame:
            return
        if self.dry_run or self._device is None:
            self.last_frame = frame
            self._frames += 1
            if self._frames == 1 or self._frames % 600 == 0:
                log.debug("Dry-run frame %s: %s", self._frames, frame)
            return
        self._send(build_payload(frame))
        self.last_frame = frame
        self._frames += 1

    def _send(self, payload: bytes, allow_reopen: bool = True) -> None:
        with self._lock:
            try:
                written = self._device.send_feature_report(payload)
                if written is not None and written < 0:
                    raise OSError(f"hidapi write returned {written}")
            except OSError as exc:
                log.warning("RGB write failed: %s", exc)
                if allow_reopen and self.reopen():
                    self._device.send_feature_report(payload)
                else:
                    raise DeviceError(f"Lost connection to the keyboard: {exc}") from exc
            except Exception as exc:  # pragma: no cover - defensive
                raise DeviceError(f"RGB write failed: {exc}") from exc

    def reopen(self) -> bool:
        """Best-effort recovery after suspend or a transient USB error."""
        log.info("Attempting to reopen the RGB interface...")
        self.close()
        for delay in (0.2, 0.6, 1.2):
            time.sleep(delay)
            try:
                self.open()
                return True
            except DeviceError:
                continue
        return False

    def off(self) -> None:
        self.last_frame = None
        try:
            self.set_colors([(0, 0, 0)] * constants.ZONE_COUNT, force=True)
        except DeviceError:
            pass

    def close(self) -> None:
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None

    def __enter__(self) -> RGBDevice:
        return self

    def __exit__(self, *exc: object) -> None:
        self.off()
        self.close()

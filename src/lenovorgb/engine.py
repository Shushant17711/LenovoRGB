"""Runs one lighting mode at a time on a background thread."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from typing import Callable, Dict, List, Optional

from .colors import BLACK, normalize_frame
from .config import Config
from .device import DeviceError, RGBDevice
from .modes import Mode, ModeContext, get_mode

log = logging.getLogger("lenovorgb.engine")

StateCallback = Callable[[Dict[str, object]], None]
ColorsCallback = Callable[[List[tuple]], None]

IDLE = "idle"
STARTING = "starting"
RUNNING = "running"
ERROR = "error"

# After this many identical frames a mode is considered idle. Polling slower
# saves CPU/battery; USB writes are already skipped by RGBDevice.set_colors.
IDLE_AFTER_FRAMES = 6
IDLE_INTERVAL_SECONDS = 0.1
# A wall-clock jump this large means the machine probably resumed from sleep.
RESUME_GAP_SECONDS = 2.0


def _same_frame(first: Sequence[Sequence[float]], second: Sequence[Sequence[float]]) -> bool:
    return len(first) == len(second) and all(
        tuple(a) == tuple(b) for a, b in zip(first, second)
    )


def _next_interval(base: float, idle_frames: int) -> float:
    interval = max(0.004, min(float(base), 0.25))
    if idle_frames >= IDLE_AFTER_FRAMES:
        interval = max(interval, IDLE_INTERVAL_SECONDS)
    return interval


class LightingEngine:
    def __init__(
        self,
        device: RGBDevice,
        config: Config,
        on_state: Optional[StateCallback] = None,
        on_colors: Optional[ColorsCallback] = None,
    ):
        self.device = device
        self.config = config
        self._on_state = on_state
        self._on_colors = on_colors
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._state = IDLE
        self._mode_id: Optional[str] = None
        self._error: Optional[str] = None
        self._colors = [(0, 0, 0)] * 4
        self._raw_frame: List[Sequence[float]] = [(0, 0, 0)] * 4
        self._generation = 0

    # ------------------------------------------------------------------ state
    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def mode_id(self) -> Optional[str]:
        with self._lock:
            return self._mode_id

    @property
    def error(self) -> Optional[str]:
        with self._lock:
            return self._error

    @property
    def active(self) -> bool:
        return self.state in (STARTING, RUNNING)

    @property
    def colors(self) -> List[tuple]:
        with self._lock:
            return list(self._colors)

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "state": self._state,
                "mode": self._mode_id,
                "error": self._error,
                "device": self.device.info.label if self.device.info else "demo",
            }

    def _set_state(self, state: str, generation: int, error: Optional[str] = None) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._state = state
            self._error = error
            snapshot = {
                "state": state,
                "mode": self._mode_id,
                "error": error,
                "device": self.device.info.label if self.device.info else "demo",
            }
        callback = self._on_state
        if callback is not None:
            try:
                callback(snapshot)
            except Exception:
                log.exception("State callback failed")

    def _publish(self, frame: Sequence[Sequence[float]]) -> None:
        colors = normalize_frame(frame, self.device.brightness)
        with self._lock:
            self._colors = colors
            self._raw_frame = [tuple(color) for color in frame]
        callback = self._on_colors
        if callback is not None:
            try:
                callback(colors)
            except Exception:
                log.exception("Colors callback failed")

    def set_brightness(self, percent: float) -> None:
        """Apply a new brightness immediately, even for slow modes."""
        self.config.brightness = percent
        self.device.set_brightness(percent)
        with self._lock:
            raw = list(self._raw_frame)
        try:
            self.device.set_colors(raw, force=True)
        except DeviceError:
            pass
        self._publish(raw)

    # -------------------------------------------------------------- lifecycle
    def set_mode(self, mode_id: str, options: Optional[Dict[str, object]] = None) -> bool:
        """Start ``mode_id``, stopping whatever was running before."""
        mode_class = get_mode(mode_id)  # raises KeyError for typos
        self.stop()

        with self._lock:
            self._generation += 1
            generation = self._generation
            self._stop = threading.Event()
            stop = self._stop
            self._mode_id = mode_id
            self._error = None
            self._state = STARTING
        thread = threading.Thread(
            target=self._run,
            args=(mode_class, stop, generation, options or {}),
            name=f"mode-{mode_id}",
            daemon=True,
        )
        with self._lock:
            self._thread = thread
        self._set_state(STARTING, generation)
        thread.start()
        return True

    def _run(
        self,
        mode_class: type,
        stop: threading.Event,
        generation: int,
        options: Dict[str, object],
    ) -> None:
        ctx = ModeContext(
            config=self.config,
            stop=stop,
            log=logging.getLogger(f"lenovorgb.mode.{mode_class.id}"),
            options=options,
        )
        mode: Optional[Mode] = None
        try:
            mode = mode_class(ctx)
            mode.setup()
            if stop.is_set():
                return
            self._set_state(RUNNING, generation)
            last = time.perf_counter()
            last_wall = time.time()
            previous: Optional[tuple] = None
            idle_frames = 0
            while not stop.is_set():
                now = time.perf_counter()
                wall = time.time()
                # perf_counter may stop during suspend; wall time does not.
                resumed = (wall - last_wall) > RESUME_GAP_SECONDS
                last_wall = wall
                dt = now - last
                last = now
                frame = mode.step(dt)
                if frame is not None:
                    snapshot = tuple(tuple(color) for color in frame)
                    if previous is not None and _same_frame(snapshot, previous):
                        idle_frames += 1
                    else:
                        idle_frames = 0
                    previous = snapshot
                    # Re-assert the frame after a resume; the keyboard may
                    # have reset while the machine was asleep.
                    self.device.set_colors(frame, force=resumed)
                    self._publish(frame)
                interval = _next_interval(mode.interval, idle_frames)
                if stop.wait(interval):
                    break
        except DeviceError as exc:
            log.error("%s", exc)
            self._set_state(ERROR, generation, str(exc))
        except Exception as exc:
            message = _friendly_error(exc)
            if type(exc).__name__ in _EXPECTED_ENVIRONMENT_ERRORS:
                log.warning("Mode %s needs a capability this system lacks: %s", mode_class.id, message)
            else:
                log.exception("Mode %s crashed", mode_class.id)
            self._set_state(ERROR, generation, message)
            try:
                self.device.set_colors([(0, 0, 0)] * 4, force=True)
            except Exception:
                pass
        finally:
            if mode is not None:
                try:
                    mode.teardown()
                except Exception:
                    log.exception("Mode %s teardown failed", mode_class.id)
            with self._lock:
                if generation == self._generation and self._state in (STARTING, RUNNING):
                    self._state = IDLE

    def stop(self, timeout: float = 2.0) -> None:
        with self._lock:
            stop = self._stop
            thread = self._thread
        stop.set()
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)
            if thread.is_alive():
                log.warning("Mode thread is taking longer than %.1fs to stop", timeout)
        with self._lock:
            if self._state in (STARTING, RUNNING):
                self._state = IDLE
        self._thread = None

    def shutdown(self, off: Optional[bool] = None) -> None:
        """Stop the mode and optionally turn the lights off."""
        self.stop()
        if off is None:
            off = bool(self.config.get("off_on_exit", True))
        if off:
            try:
                self.device.set_colors([BLACK] * 4, force=True)
            except DeviceError:
                pass


_EXPECTED_ENVIRONMENT_ERRORS = {
    "AudioUnavailable",
    "ScreenUnavailable",
    "InputUnavailable",
    "DeviceNotFound",
    "PermissionDenied",
}


def _friendly_error(exc: Exception) -> str:
    name = type(exc).__name__
    if name in {"AudioUnavailable", "ScreenUnavailable", "InputUnavailable"}:
        return str(exc)
    if isinstance(exc, ImportError):
        return f"A required package is missing: {exc}"
    return f"{name}: {exc}"

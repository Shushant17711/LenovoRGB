"""Loopback audio capture (what you hear, not the microphone)."""

from __future__ import annotations

import logging
import sys
from typing import List, Optional, Tuple

import numpy as np

log = logging.getLogger("lenovorgb.audio")


class AudioUnavailable(RuntimeError):
    pass


def _import_soundcard():
    """Import soundcard without tripping its sys.argv[1] assumption.

    soundcard 0.4.6 reads ``sys.argv[1]`` at import time to name its
    PulseAudio client. A frozen GUI has no arguments, so give it a dummy
    value just for the import.
    """
    saved = sys.argv
    try:
        if len(sys.argv) < 2:
            sys.argv = [sys.argv[0] if sys.argv else "lenovorgb", "lenovorgb"]
        import soundcard  # type: ignore
    finally:
        sys.argv = saved
    return soundcard


class LoopbackCapture:
    def __init__(
        self,
        device_hint: Optional[str] = None,
        samplerate: int = 44100,
        blocksize: int = 2048,
    ):
        self.device_hint = device_hint
        self.samplerate = int(samplerate)
        self.blocksize = int(blocksize)
        self.device_name = ""
        self._recorder = None
        self._mic = None

    # ------------------------------------------------------------------ open
    def open(self) -> None:
        try:
            sc = _import_soundcard()
        except Exception as exc:  # pragma: no cover - depends on libpulse
            hint = ""
            if "libpulse" in str(exc).lower() or "cannot load" in str(exc).lower():
                hint = (
                    " The PulseAudio client library is missing: "
                    "Arch: sudo pacman -S libpulse; Debian/Ubuntu: sudo apt install libpulse0."
                )
            raise AudioUnavailable(
                f"Audio capture is unavailable ({exc}). Install with: "
                f"pip install 'lenovorgb[audio]'.{hint}"
            ) from exc

        try:
            microphones = list(sc.all_microphones(include_loopback=True))
        except Exception as exc:
            raise AudioUnavailable(f"Could not query audio devices: {exc}") from exc
        if not microphones:
            raise AudioUnavailable("No audio devices were found.")

        candidates = [m for m in microphones if getattr(m, "isloopback", False)]
        if not candidates:
            # PipeWire / PulseAudio expose monitors as regular inputs.
            candidates = [m for m in microphones if "monitor" in m.name.lower()]
        if not candidates:
            log.warning("No loopback device found; falling back to default input.")
            candidates = microphones

        chosen = self._choose(candidates)
        self._mic = chosen
        self.device_name = chosen.name
        log.info("Capturing audio from: %s", chosen.name)

        try:
            recorder = chosen.recorder(samplerate=self.samplerate)
            recorder.__enter__()
        except Exception as exc:
            raise AudioUnavailable(f"Could not open '{chosen.name}': {exc}") from exc
        self._recorder = recorder

    def _choose(self, candidates: List[object]) -> object:
        if self.device_hint:
            hint = self.device_hint.lower()
            for mic in candidates:
                if hint in mic.name.lower():
                    return mic
            log.warning("Configured audio device %r not found; auto-detecting.", self.device_hint)
        if len(candidates) == 1:
            return candidates[0]

        # Prefer a device that is currently producing sound.
        best = None
        best_rms = 0.0
        for mic in candidates:
            recorder = None
            try:
                recorder = mic.recorder(samplerate=self.samplerate)
                recorder.__enter__()
                rms = 0.0
                for _ in range(2):
                    data = recorder.record(numframes=self.blocksize)
                    if data is not None and len(data):
                        rms = max(rms, float(np.sqrt(np.mean(np.mean(data, axis=1) ** 2))))
                if rms > best_rms:
                    best, best_rms = mic, rms
            except Exception:
                continue
            finally:
                if recorder is not None:
                    try:
                        recorder.__exit__(None, None, None)
                    except Exception:
                        pass
        if best is not None and best_rms > 0.0001:
            return best
        for mic in candidates:
            if any(word in mic.name.lower() for word in ("monitor", "stereo mix", "loopback")):
                return mic
        return candidates[0]

    # ------------------------------------------------------------------ read
    def read(self) -> np.ndarray:
        if self._recorder is None:
            return np.zeros(self.blocksize, dtype=np.float32)
        try:
            data = self._recorder.record(numframes=self.blocksize)
        except Exception as exc:
            log.debug("Audio read failed: %s", exc)
            return np.zeros(self.blocksize, dtype=np.float32)
        if data is None or len(data) == 0:
            return np.zeros(self.blocksize, dtype=np.float32)
        array = np.asarray(data, dtype=np.float32)
        if array.ndim == 2:
            array = array.mean(axis=1)
        return array

    def close(self) -> None:
        if self._recorder is not None:
            try:
                self._recorder.__exit__(None, None, None)
            except Exception:
                pass
            self._recorder = None
        self._mic = None

    def __enter__(self) -> LoopbackCapture:
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def probe() -> Tuple[bool, str]:
    """Used by ``lenovorgb doctor``."""
    try:
        sc = _import_soundcard()

        mics = list(sc.all_microphones(include_loopback=True))
        loopbacks = [m.name for m in mics if getattr(m, "isloopback", False)]
        if loopbacks:
            return True, f"{len(loopbacks)} loopback device(s), e.g. {loopbacks[0]}"
        monitors = [m.name for m in mics if "monitor" in m.name.lower()]
        if monitors:
            return True, f"{len(monitors)} monitor device(s), e.g. {monitors[0]}"
        return False, "Audio devices found but none expose loopback capture."
    except Exception as exc:
        return False, str(exc)

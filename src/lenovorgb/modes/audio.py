"""Audio visualizer: turns what you are playing into light."""

from __future__ import annotations

import math
from typing import List, Optional

import numpy as np

from ..inputs.audio import LoopbackCapture
from .base import Frame, Mode, ModeContext

BANDS = (
    (30.0, 300.0),     # bass   -> zone 0 (red)
    (300.0, 2500.0),   # mids   -> zone 1 (green)
    (2500.0, 10000.0),  # treble -> zone 2 (blue)
)


class AudioVisualizer(Mode):
    id = "audio"
    name = "Audio Visualizer"
    description = "Bass, mids and treble pulse the zones in sync with your music."
    category = "system"
    abbr = "AU"
    accent = "#f472b6"
    interval = 0.021
    needs = ("audio",)

    def __init__(self, ctx: ModeContext):
        super().__init__(ctx)
        self.capture: Optional[LoopbackCapture] = None
        self.sample_rate = int(ctx.config.get("audio.samplerate", 44100))
        self.blocksize = 2048
        self._window: Optional[np.ndarray] = None
        self._peaks: List[float] = [0.01, 0.01, 0.01, 0.01]
        self._display = [[0.0, 0.0, 0.0] for _ in range(4)]
        self._smoothing = float(ctx.config.get("audio.smoothing", 0.35))

    def setup(self) -> None:
        self.capture = LoopbackCapture(
            device_hint=self.ctx.config.get("audio.device"),
            samplerate=self.sample_rate,
            blocksize=self.blocksize,
        )
        self.capture.open()
        self._window = np.hanning(self.blocksize).astype(np.float32)
        self.ctx.log.info("Audio visualizer listening to %s", self.capture.device_name)

    def step(self, dt: float) -> Optional[Frame]:
        if self.capture is None:
            return None
        mono = self.capture.read()
        if mono.size < 64:
            return None

        windowed = mono[: self.blocksize] * self._window[: mono.size]
        rms_raw = float(np.sqrt(np.mean(mono**2)))

        if rms_raw < 0.0003:
            return self._fade_out()

        spectrum = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(len(windowed), 1.0 / self.sample_rate)
        values = []
        for low, high in BANDS:
            mask = (freqs >= low) & (freqs < high)
            values.append(float(np.sqrt(np.mean(spectrum[mask] ** 2))) if np.any(mask) else 0.0)
        values.append(rms_raw)

        for index, value in enumerate(values):
            if value > self._peaks[index]:
                self._peaks[index] = value
            else:
                self._peaks[index] *= math.exp(-0.18 * dt)
            self._peaks[index] = max(self._peaks[index], 0.004)

        levels = [min(1.0, values[i] / self._peaks[i]) ** 0.85 for i in range(4)]
        targets = [
            (levels[0] * 255.0, 0.0, 0.0),
            (0.0, levels[1] * 255.0, 0.0),
            (0.0, 0.0, levels[2] * 255.0),
            (levels[3] * 190.0, levels[3] * 255.0, levels[3] * 255.0),
        ]

        attack = min(1.0, 0.75 * (dt / 0.02))
        decay = min(1.0, 0.35 * (dt / 0.02))
        for zone in range(4):
            for channel in range(3):
                current = self._display[zone][channel]
                target = targets[zone][channel]
                alpha = attack if target > current else decay
                current += (target - current) * alpha
                if current < 2.0 and target < 1.0:
                    current = 0.0
                self._display[zone][channel] = current
        return [tuple(int(min(255.0, value)) for value in zone) for zone in self._display]

    def _fade_out(self) -> Frame:
        for zone in range(4):
            for channel in range(3):
                self._display[zone][channel] *= 0.72
                if self._display[zone][channel] < 1.5:
                    self._display[zone][channel] = 0.0
        return [tuple(int(value) for value in zone) for zone in self._display]

    def teardown(self) -> None:
        if self.capture is not None:
            self.capture.close()
            self.capture = None

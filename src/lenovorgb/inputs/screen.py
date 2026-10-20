"""Screen capture with X11, Wayland and Windows support."""

from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple

import numpy as np

log = logging.getLogger("lenovorgb.screen")


class ScreenUnavailable(RuntimeError):
    pass


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def is_wayland() -> bool:
    return bool(os.environ.get("WAYLAND_DISPLAY")) and os.environ.get(
        "XDG_SESSION_TYPE", ""
    ).lower() != "x11"


class ScreenGrabber:
    """Grabs the primary screen as an RGB numpy array."""

    def __init__(self, backend: Optional[str] = None):
        self.backend = backend
        self.error: Optional[str] = None
        self._mss = None
        self._monitor = None
        self._tmpfiles: List[str] = []

    # ------------------------------------------------------------------ open
    def open(self) -> str:
        attempts = [self.backend] if self.backend else self._backend_order()
        for name in attempts:
            if not name:
                continue
            try:
                self._setup(name)
                self.backend = name
                log.info("Screen capture backend: %s", name)
                return name
            except Exception as exc:
                self.error = str(exc)
                log.debug("Screen backend %s failed: %s", name, exc)
        raise ScreenUnavailable(
            self.error
            or "No screen capture method is available. "
            "Install mss (X11) or grim (Wayland)."
        )

    @staticmethod
    def _backend_order() -> List[str]:
        if sys.platform.startswith("linux"):
            if is_wayland():
                order = ["grim", "spectacle", "gnome-screenshot", "mss"]
            else:
                order = ["mss", "grim"]
        else:
            order = ["mss"]
        return order

    def _setup(self, name: str) -> None:
        if name == "mss":
            import mss  # type: ignore

            factory = getattr(mss, "MSS", None) or mss.mss
            self._mss = factory()
            monitors = self._mss.monitors
            self._monitor = monitors[1] if len(monitors) > 1 else monitors[0]
            return
        if name in {"grim", "spectacle", "gnome-screenshot"}:
            if not _which(name):
                raise ScreenUnavailable(f"'{name}' is not installed")
            return
        raise ScreenUnavailable(f"Unknown capture backend: {name}")

    # ------------------------------------------------------------------ grab
    def grab(self) -> np.ndarray:
        if self.backend == "mss":
            return self._grab_mss()
        if self.backend == "grim":
            return self._grab_grim()
        if self.backend == "spectacle":
            return self._grab_file(
                [_which("spectacle") or "spectacle", "-b", "-n", "-o", "{file}"]
            )
        if self.backend == "gnome-screenshot":
            return self._grab_file(
                [_which("gnome-screenshot") or "gnome-screenshot", "-f", "{file}"]
            )
        raise ScreenUnavailable("Screen capture was not initialised")

    def _grab_mss(self) -> np.ndarray:
        raw = self._mss.grab(self._monitor)
        frame = np.asarray(raw, dtype=np.uint8)
        if frame.shape[2] == 4:
            frame = frame[:, :, :3]
        return frame[:, :, ::-1]  # BGRA -> RGB

    def _grab_grim(self) -> np.ndarray:
        try:
            result = subprocess.run(
                [_which("grim") or "grim", "-t", "png", "-"],
                capture_output=True,
                timeout=5,
                check=True,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise ScreenUnavailable(f"grim failed: {exc}") from exc
        return _decode_image(result.stdout)

    def _grab_file(self, template: List[str]) -> np.ndarray:
        fd, path = tempfile.mkstemp(prefix="lenovorgb-", suffix=".png")
        os.close(fd)
        self._tmpfiles.append(path)
        args = [part.replace("{file}", path) for part in template]
        try:
            subprocess.run(args, capture_output=True, timeout=8, check=True)
            with open(path, "rb") as handle:
                data = handle.read()
        except (subprocess.SubprocessError, OSError) as exc:
            raise ScreenUnavailable(f"{args[0]} failed: {exc}") from exc
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
            if path in self._tmpfiles:
                self._tmpfiles.remove(path)
        return _decode_image(data)

    def close(self) -> None:
        if self._mss is not None:
            try:
                self._mss.close()
            except Exception:
                pass
            self._mss = None
        for path in list(self._tmpfiles):
            try:
                os.unlink(path)
            except OSError:
                pass
        self._tmpfiles.clear()


def _decode_image(data: bytes) -> np.ndarray:
    try:
        from PIL import Image  # type: ignore
    except Exception as exc:
        raise ScreenUnavailable(
            "Pillow is required to decode Wayland screenshots: pip install Pillow"
        ) from exc
    with Image.open(io.BytesIO(data)) as image:
        return np.asarray(image.convert("RGB"), dtype=np.uint8)


def probe() -> Tuple[bool, str]:
    grabber = ScreenGrabber()
    try:
        backend = grabber.open()
        frame = grabber.grab()
        return True, f"{backend} ({frame.shape[1]}x{frame.shape[0]})"
    except Exception as exc:
        return False, str(exc)
    finally:
        grabber.close()

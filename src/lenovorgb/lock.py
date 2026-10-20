"""Single-instance lock so two engines never fight over the HID device."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from .paths import lock_file

log = logging.getLogger("lenovorgb.lock")


class InstanceLock:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else lock_file()
        # Keep the holder details out of the locked file itself: Windows can
        # deny reading a file while another handle has a byte-range lock on it.
        self.meta_path = self.path.with_name(self.path.name + ".meta")
        self._handle = None
        self.holder_pid: Optional[int] = None
        self.holder_label = ""

    def acquire(self, label: str = "cli") -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = open(self.path, "a+", encoding="utf-8")  # noqa: SIM115 - held while locked
        except OSError as exc:
            log.warning("Could not open lock file %s: %s", self.path, exc)
            return True  # do not block the app because of a read-only home

        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(" ")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._read_holder()
            handle.close()
            return False

        self._handle = handle
        self._write_holder(label)
        return True

    def _write_holder(self, label: str) -> None:
        try:
            temporary = self.meta_path.with_name(
                f"{self.meta_path.name}.{os.getpid()}.tmp"
            )
            temporary.write_text(f"{os.getpid()}\t{label}", encoding="utf-8")
            os.replace(temporary, self.meta_path)
        except OSError as exc:
            log.debug("Could not write lock metadata %s: %s", self.meta_path, exc)

    def _read_holder(self) -> None:
        for candidate in (self.meta_path, self.path):
            try:
                text = candidate.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeError):
                continue
            if not text:
                continue
            parts = text.split("\t")
            try:
                self.holder_pid = int(parts[0]) if parts[0] else None
            except ValueError:
                self.holder_pid = None
            self.holder_label = parts[1] if len(parts) > 1 else ""
            return

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                try:
                    msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            try:
                self._handle.close()
            except OSError:
                pass
            self._handle = None
        try:
            self.meta_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass

    @property
    def held(self) -> bool:
        return self._handle is not None

    def __enter__(self) -> InstanceLock:
        if not self.acquire():
            raise RuntimeError(self.busy_message())
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()

    def busy_message(self) -> str:
        pid = self.holder_pid
        who = f" (PID {pid})" if pid else ""
        return (
            f"LenovoRGB is already running{who}.\n"
            "Close it from the tray, or run 'lenovorgb doctor' if you think this is stale."
        )

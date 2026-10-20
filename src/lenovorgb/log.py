"""Logging setup that works in both console and windowed builds."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from .paths import ensure_dirs, log_file

_CONFIGURED = False


def setup(verbose: bool = False, log_to_file: bool = True) -> logging.Logger:
    """Configure the root ``lenovorgb`` logger once.

    PyInstaller ``--windowed`` builds have ``sys.stdout is None``; we never
    crash trying to write to a missing console.
    """
    global _CONFIGURED
    logger = logging.getLogger("lenovorgb")
    if _CONFIGURED:
        if verbose:
            logger.setLevel(logging.DEBUG)
        return logger

    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")

    if sys.stderr is not None:
        stream = logging.StreamHandler(sys.stderr)
        stream.setLevel(logging.DEBUG if verbose else logging.INFO)
        stream.setFormatter(fmt)
        logger.addHandler(stream)

    if log_to_file:
        try:
            ensure_dirs()
            file_handler = logging.handlers.RotatingFileHandler(
                log_file(), maxBytes=1_000_000, backupCount=2, encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
            )
            logger.addHandler(file_handler)
        except OSError:
            pass

    _CONFIGURED = True
    return logger


def get(name: str) -> logging.Logger:
    return logging.getLogger("lenovorgb." + name)


def tail_log(lines: int = 40) -> str:
    """Return the last log lines, used by ``lenovorgb doctor``."""
    try:
        path = Path(log_file())
        if not path.is_file():
            return ""
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
    except OSError:
        return ""

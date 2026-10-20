"""Optional system tray integration."""

from __future__ import annotations

import logging
import os
import sys
import threading
from pathlib import Path

from ..modes import CATEGORIES, grouped

log = logging.getLogger("lenovorgb.tray")


class _DockNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "dock icon" not in record.getMessage().lower()


def _silence_dock_noise() -> None:
    """pystray logs a traceback when no tray manager exists; it is harmless."""
    logger = logging.getLogger("pystray")
    if not any(isinstance(existing, _DockNoiseFilter) for existing in logger.filters):
        logger.addFilter(_DockNoiseFilter())


def x11_tray_available() -> bool:
    """True when an X11 system tray manager owns the tray selection."""
    if not sys.platform.startswith("linux"):
        return True
    if not os.environ.get("DISPLAY"):
        return False
    try:
        from Xlib import X, display  # type: ignore

        connection = display.Display()
        try:
            atom = connection.intern_atom(
                f"_NET_SYSTEM_TRAY_S{connection.get_default_screen()}"
            )
            owner = connection.get_selection_owner(atom)
            return owner is not None and getattr(owner, "id", 0) != X.NONE
        finally:
            connection.close()
    except Exception as exc:
        log.debug("Could not query the X11 tray manager: %s", exc)
        return True  # let pystray try rather than silently disabling the tray


def _fallback_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 124, 124), radius=26, fill=(12, 16, 24, 255))
    colors = [(34, 211, 238), (96, 165, 250), (139, 92, 246), (244, 114, 182)]
    for index, color in enumerate(colors):
        x1 = 20 + index * 23
        draw.rounded_rectangle((x1, 34, x1 + 15, 94), radius=7, fill=color + (255,))
    return image


def load_icon_image():
    try:
        from PIL import Image

        asset = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
        if asset.is_file():
            return Image.open(asset).convert("RGBA")
    except Exception:
        pass
    return _fallback_image()


class TrayController:
    def __init__(self, app: object):
        self.app = app
        self.icon = None
        self.available = False

    def start(self) -> bool:
        _silence_dock_noise()
        if not x11_tray_available():
            log.info("No system tray manager detected; the window will stay visible.")
            return False
        try:
            import pystray
        except Exception as exc:
            log.info("Tray unavailable (pystray): %s", exc)
            return False
        try:
            image = load_icon_image()
            menu = self._build_menu(pystray)
            self.icon = pystray.Icon("LenovoRGB", image, "Lenovo RGB", menu)
            self.icon.run_detached()
            self.available = True
            log.info("Tray icon started")
            return True
        except Exception:
            log.exception("Could not start the tray icon")
            self.icon = None
            self.available = False
            return False

    def _build_menu(self, pystray):
        menu_items = [
            pystray.MenuItem("Open Lenovo RGB", self._open, default=True),
            pystray.MenuItem("Settings", self._settings),
            pystray.Menu.SEPARATOR,
        ]

        def mode_item(mode):
            return pystray.MenuItem(
                mode.name,
                self._mode_callback(mode.id),
                checked=(lambda item, mode_id=mode.id: self.app.current_mode == mode_id),
                radio=True,
            )

        for category, modes in grouped().items():
            submenu = pystray.Menu(*[mode_item(mode) for mode in modes])
            menu_items.append(pystray.MenuItem(CATEGORIES.get(category, category), submenu))

        menu_items.extend(
            [
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Turn lights off", self._off),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            ]
        )
        return pystray.Menu(*menu_items)

    # Callbacks run on the tray thread; always hop back to Tk's thread.
    def _open(self, icon: object = None, item: object = None) -> None:
        self.app.post(self.app.show_window)

    def _settings(self, icon: object = None, item: object = None) -> None:
        self.app.post(self.app.show_settings)

    def _off(self, icon: object = None, item: object = None) -> None:
        self.app.post(self.app.apply_mode, "off")

    def _quit(self, icon: object = None, item: object = None) -> None:
        self.app.post(self.app.quit_app)

    def _mode_callback(self, mode_id: str):
        def callback(icon: object = None, item: object = None) -> None:
            self.app.post(self.app.apply_mode, mode_id)

        return callback

    def stop(self) -> None:
        icon, self.icon = self.icon, None
        self.available = False
        if icon is None:
            return

        def _stop() -> None:
            try:
                icon.stop()
            except Exception:
                log.exception("Failed to stop tray icon")

        # pystray joins its setup thread for up to 5 seconds; never block
        # the Tk shutdown path (or the user's logout).
        threading.Thread(target=_stop, name="tray-stop", daemon=True).start()

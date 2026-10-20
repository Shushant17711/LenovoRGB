"""The Lenovo RGB desktop application."""

from __future__ import annotations

import ctypes
import logging
import os
import queue
import signal
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Dict, Optional

from .. import __version__, autostart
from ..config import Config
from ..device import DeviceError, RGBDevice
from ..engine import ERROR, IDLE, RUNNING, LightingEngine
from ..inputs.keyboard import KeyboardMonitor, keyboard_available, parse_hotkey
from ..lock import InstanceLock
from ..modes import CATEGORIES, CATEGORY_ORDER, MODES, by_category, get_mode
from . import theme
from .theme import Fonts, apply_ttk_theme
from .tray import TrayController
from .widgets import (
    FlatButton,
    ModeCard,
    Pill,
    ScrollFrame,
    SidebarButton,
    Switch,
    ZonePreview,
    rounded_rect,
    separator,
)

log = logging.getLogger("lenovorgb.ui")

CATEGORY_ALL = "all"


def launch(config: Config, minimized: bool = False, no_tray: bool = False, demo: bool = False) -> int:
    """Open the app. Returns a process exit code."""
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    lock = InstanceLock()
    if not lock.acquire(label="gui"):
        if lock.holder_label == "gui" and lock.holder_pid:
            sig = getattr(signal, "SIGUSR1", None)
            if sig is not None:
                try:
                    os.kill(lock.holder_pid, sig)
                except OSError:
                    pass
                else:
                    if sys.stdout is not None:
                        print("Lenovo RGB is already running; asked it to show its window.")
                    return 0
        message = lock.busy_message()
        if sys.stderr is not None:
            print(message, file=sys.stderr)
        return 1

    device: Optional[RGBDevice] = None
    app: Optional[RGBApp] = None
    root: Optional[tk.Tk] = None
    try:
        device_error: Optional[str] = None
        if demo:
            device = RGBDevice(dry_run=True, brightness=config.brightness)
        else:
            try:
                device = RGBDevice(
                    path=config.get("device.path"),
                    product_id=config.get("device.product_id"),
                    brightness=config.brightness,
                )
            except DeviceError as exc:
                device_error = str(exc)
                device = RGBDevice(dry_run=True, brightness=config.brightness)

        try:
            root = tk.Tk()
        except tk.TclError as exc:
            if sys.stderr is not None:
                print(f"Could not open a window: {exc}", file=sys.stderr)
                print("Start a desktop session, or use 'lenovorgb run <mode>' from a terminal.", file=sys.stderr)
            return 1
        try:
            app = RGBApp(
                root,
                config,
                device,
                device_error=device_error,
                no_tray=no_tray,
            )
        except Exception as exc:
            log.exception("Could not build the interface")
            if sys.stderr is not None:
                print(f"Could not start the interface: {exc}", file=sys.stderr)
                print("See the log for details, or use 'lenovorgb run <mode>'.", file=sys.stderr)
            return 1
        if minimized and app.has_tray:
            root.withdraw()
        else:
            root.deiconify()
            root.lift()
        root.mainloop()
        return 0
    finally:
        if app is not None:
            app.cleanup()
        if device is not None:
            device.close()
        if root is not None:
            try:
                root.destroy()
            except (tk.TclError, ValueError):
                pass
        lock.release()
        if app is not None and app.has_tray:
            # pystray keeps non-daemon threads around on some desktops; the
            # app is fully shut down at this point, so do not wait for them.
            os._exit(0)


class RGBApp:
    def __init__(
        self,
        root: tk.Tk,
        config: Config,
        device: RGBDevice,
        device_error: Optional[str] = None,
        no_tray: bool = False,
    ):
        self.root = root
        self.config = config
        self.device = device
        self.device_error = device_error
        self.demo = device.info is None
        self.current_mode = ""
        self._category = CATEGORY_ALL
        self._cards: Dict[str, ModeCard] = {}
        self._filter_buttons: Dict[str, SidebarButton] = {}
        self._settings_window: Optional[tk.Toplevel] = None
        self._hotkey_monitor: Optional[KeyboardMonitor] = None
        self._closing = False
        self._cleaned = False
        self._last_error = device_error or ""
        self._save_job: Optional[str] = None
        self._icon_image = None
        self._show_requested = False
        self._capability_warning: Optional[str] = None
        self._events: queue.Queue = queue.Queue()

        root.title("Lenovo RGB")
        root.configure(bg=theme.BG)
        self._enable_dark_titlebar(root)
        root.minsize(900, 640)
        self.fonts = Fonts(root)
        apply_ttk_theme(root, self.fonts)
        self._set_window_geometry()
        self._set_icon()

        self.engine = LightingEngine(
            device,
            config,
            on_state=self._on_engine_state,
            on_colors=None,
        )
        self.tray = TrayController(self)
        self.has_tray = False
        if not no_tray and bool(config.get("tray", True)):
            self.has_tray = self.tray.start()

        self._build()
        self._start_hotkey()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Control-q>", lambda _event: self.quit_app())
        self.root.bind("<Control-comma>", lambda _event: self.show_settings())
        self._install_show_signal()
        self._install_shutdown_signals()
        self.root.after(80, self._tick)
        self.root.after(250, self._start_default_mode)

        if self.demo:
            self._set_status(
                "No keyboard found - running in demo mode. Click for details.", theme.WARNING
            )
        else:
            self._set_status("Ready", theme.MUTED)

    # ------------------------------------------------------------------ setup
    def _install_show_signal(self) -> None:
        sig = getattr(signal, "SIGUSR1", None)
        if sig is None:
            return

        def handler(signum: int, frame: object) -> None:
            self._show_requested = True

        try:
            signal.signal(sig, handler)
        except (ValueError, OSError):
            pass

    def _install_shutdown_signals(self) -> None:
        """Let logout / kill / Ctrl+C close cleanly and turn the LEDs off."""
        for name in ("SIGINT", "SIGTERM", "SIGHUP"):
            sig = getattr(signal, name, None)
            if sig is None:
                continue

            def handler(signum: int, frame: object) -> None:
                self.post(self.quit_app)

            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass

    @staticmethod
    def _enable_dark_titlebar(window: tk.Misc) -> None:
        """Ask the Windows compositor for a dark title bar (best effort)."""
        if os.name != "nt":
            return
        try:
            window.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
            enabled = ctypes.c_int(1)
            for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE, pre-20H1
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(enabled), ctypes.sizeof(enabled)
                )
                if result == 0:
                    break
        except Exception:
            pass

    def _set_window_geometry(self) -> None:
        width = int(self.config.get("window.width", 940))
        height = int(self.config.get("window.height", 640))
        self.root.geometry(f"{width}x{height}")
        try:
            screen_w = self.root.winfo_screenwidth()
            screen_h = self.root.winfo_screenheight()
            x = max(0, (screen_w - width) // 2)
            y = max(0, (screen_h - height) // 3)
            self.root.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def _set_icon(self) -> None:
        asset = Path(__file__).resolve().parent.parent / "assets" / "icon.png"
        if not asset.is_file():
            return
        try:
            image = tk.PhotoImage(file=str(asset))
            self.root.iconphoto(True, image)
            self._icon_image = image
        except tk.TclError:
            pass

    # -------------------------------------------------------------------- ui
    def _build(self) -> None:
        self._build_header()

        footer = tk.Frame(self.root, bg=theme.BG_ELEVATED, height=70)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)
        self._build_footer(footer)

        body = tk.Frame(self.root, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=26, pady=(20, 0))

        sidebar = tk.Frame(body, bg=theme.BG, width=216)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        content = tk.Frame(body, bg=theme.BG)
        content.pack(side="left", fill="both", expand=True, padx=(24, 0))
        self._build_content(content)

        tk.Frame(self.root, bg=theme.BG, height=14).pack(side="bottom", fill="x")

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=theme.BG, height=62)
        header.pack(fill="x", padx=26, pady=(20, 0))
        header.pack_propagate(False)

        logo = tk.Canvas(header, width=44, height=44, bg=theme.BG, highlightthickness=0, bd=0)
        logo.pack(side="left", pady=4)
        rounded_rect(logo, 1, 1, 43, 43, 12, fill=theme.SURFACE, outline=theme.BORDER)
        colors = ("#22D3EE", "#60A5FA", "#8B5CF6", "#F472B6")
        for index, color in enumerate(colors):
            x = 9 + index * 7
            rounded_rect(logo, x, 13, x + 4, 31, 2, fill=color, outline="")

        titles = tk.Frame(header, bg=theme.BG)
        titles.pack(side="left", padx=(12, 0))
        tk.Label(
            titles,
            text="Lenovo RGB",
            font=self.fonts.title,
            bg=theme.BG,
            fg=theme.TEXT,
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            titles,
            text="4-zone keyboard control",
            font=self.fonts.subtitle,
            bg=theme.BG,
            fg=theme.MUTED,
            anchor="w",
        ).pack(anchor="w")

        right = tk.Frame(header, bg=theme.BG)
        right.pack(side="right")
        settings_button = FlatButton(
            right,
            text="Settings",
            command=self.show_settings,
            font=self.fonts.button,
            variant="ghost",
            padx=16,
            pady=8,
        )
        settings_button.pack(side="right", padx=(10, 0))
        if self.device.info is not None:
            label, color = "Connected", theme.SUCCESS
        elif self.device_error:
            label, color = "No device", theme.DANGER
        else:
            label, color = "Demo", theme.WARNING
        self.device_pill = Pill(right, label, color, self.fonts.small, bg=theme.BG)
        self.device_pill.pack(side="right", pady=2)

    def _build_sidebar(self, parent: tk.Frame) -> None:
        tk.Label(
            parent,
            text="LIBRARY",
            font=self.fonts.section,
            bg=theme.BG,
            fg=theme.MUTED,
            anchor="w",
        ).pack(fill="x", padx=4, pady=(2, 8))

        labels = {CATEGORY_ALL: "All modes"}
        labels.update({key: CATEGORIES[key] for key in CATEGORY_ORDER})
        for key, label in labels.items():
            count = len(MODES) if key == CATEGORY_ALL else len(by_category(key))
            button = SidebarButton(
                parent,
                text=label,
                command=lambda category=key: self.filter_category(category),
                font=self.fonts.body,
                count=count,
            )
            button.pack(fill="x", pady=1)
            self._filter_buttons[key] = button
        self._filter_buttons[CATEGORY_ALL].set_selected(True)

        separator(parent, theme.BORDER).pack(fill="x", pady=(18, 16))

        tk.Label(
            parent,
            text="NOW PLAYING",
            font=self.fonts.section,
            bg=theme.BG,
            fg=theme.MUTED,
            anchor="w",
        ).pack(fill="x", padx=4, pady=(0, 8))

        self.preview_title = tk.Label(
            parent,
            text="Nothing yet",
            font=self.fonts.heading,
            bg=theme.BG,
            fg=theme.TEXT,
            anchor="w",
        )
        self.preview_title.pack(fill="x", padx=4)
        self.preview_desc = tk.Label(
            parent,
            text="Pick a mode from the library.",
            font=self.fonts.small,
            bg=theme.BG,
            fg=theme.MUTED,
            anchor="w",
            justify="left",
            wraplength=196,
        )
        self.preview_desc.pack(fill="x", padx=4, pady=(4, 10))

        self.preview = ZonePreview(parent, width=204, height=36)
        self.preview.pack(anchor="w", padx=4)

        if self.demo:
            tk.Label(
                parent,
                text="Demo preview\nno hardware attached",
                font=self.fonts.small,
                bg=theme.BG,
                fg=theme.WARNING,
                anchor="w",
                justify="left",
            ).pack(fill="x", padx=4, pady=(10, 0))

        spacer = tk.Frame(parent, bg=theme.BG)
        spacer.pack(fill="both", expand=True)

    def _build_content(self, parent: tk.Frame) -> None:
        heading = tk.Frame(parent, bg=theme.BG)
        heading.pack(fill="x", pady=(0, 12))
        self.heading_label = tk.Label(
            heading,
            text="All modes",
            font=self.fonts.heading,
            bg=theme.BG,
            fg=theme.TEXT,
            anchor="w",
        )
        self.heading_label.pack(side="left")
        self.count_label = tk.Label(
            heading,
            text=f"{len(MODES)} effects",
            font=self.fonts.small,
            bg=theme.BG,
            fg=theme.MUTED,
            anchor="w",
        )
        self.count_label.pack(side="left", padx=(10, 0), pady=(3, 0))

        self.scroll = ScrollFrame(parent, bg=theme.BG)
        self.scroll.pack(fill="both", expand=True)
        self.grid_frame = self.scroll.inner
        self.grid_frame.columnconfigure(0, weight=1, uniform="cards")
        self.grid_frame.columnconfigure(1, weight=1, uniform="cards")
        self._populate()

    def _build_footer(self, footer: tk.Frame) -> None:
        tk.Frame(footer, bg=theme.BORDER, height=1).pack(fill="x")
        inner = tk.Frame(footer, bg=theme.BG_ELEVATED)
        inner.pack(fill="both", expand=True, padx=26, pady=14)

        brightness = tk.Frame(inner, bg=theme.BG_ELEVATED)
        brightness.pack(side="left")
        tk.Label(
            brightness,
            text="BRIGHTNESS",
            font=self.fonts.section,
            bg=theme.BG_ELEVATED,
            fg=theme.MUTED,
        ).pack(side="left", padx=(0, 12))

        self.brightness_var = tk.DoubleVar(value=self.config.brightness)
        scale = ttk.Scale(
            brightness,
            from_=0,
            to=100,
            variable=self.brightness_var,
            command=self._on_brightness,
            style="RGB.Horizontal.TScale",
            length=170,
        )
        scale.pack(side="left")
        scale.bind("<ButtonRelease-1>", lambda _event: self._save_config_later(delay=0))
        self.brightness_value = tk.Label(
            brightness,
            text=f"{self.config.brightness}%",
            font=self.fonts.small,
            bg=theme.BG_ELEVATED,
            fg=theme.TEXT_SECONDARY,
            width=5,
            anchor="e",
        )
        self.brightness_value.pack(side="left", padx=(8, 0))

        self.off_button = FlatButton(
            inner,
            text="Lights off",
            command=lambda: self.apply_mode("off"),
            font=self.fonts.button,
            variant="danger",
            padx=16,
            pady=8,
        )
        self.off_button.pack(side="right")

        self.status_label = tk.Label(
            inner,
            text="Ready",
            font=self.fonts.small,
            bg=theme.BG_ELEVATED,
            fg=theme.MUTED,
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True, padx=(26, 16))
        self.status_label.bind("<Button-1>", self._status_clicked)

    # --------------------------------------------------------------- library
    def _populate(self) -> None:
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self._cards = {}

        modes = MODES if self._category == CATEGORY_ALL else by_category(self._category)
        for index, mode in enumerate(modes):
            card = ModeCard(
                self.grid_frame,
                mode,
                self.apply_mode,
                self.fonts,
                selected=mode.id == self.current_mode,
            )
            row, column = divmod(index, 2)
            card.grid(
                row=row,
                column=column,
                sticky="nsew",
                padx=(0, 7) if column == 0 else (7, 0),
                pady=(0, 12),
            )
            self._cards[mode.id] = card

    def filter_category(self, category: str) -> None:
        self._category = category
        for key, button in self._filter_buttons.items():
            button.set_selected(key == category)
        if category == CATEGORY_ALL:
            self.heading_label.configure(text="All modes")
            count = len(MODES)
        else:
            self.heading_label.configure(text=CATEGORIES.get(category, category))
            count = len(by_category(category))
        self.count_label.configure(text=f"{count} effect{'s' if count != 1 else ''}")
        self._populate()
        self.scroll.scroll_to_top()

    # ------------------------------------------------------------------ modes
    def apply_mode(self, mode_id: str) -> None:
        if self._closing:
            return
        try:
            mode = get_mode(mode_id)
        except KeyError as exc:
            self._set_status(str(exc), theme.DANGER)
            return
        try:
            self.engine.set_mode(mode_id)
        except Exception as exc:
            log.exception("Could not start mode %s", mode_id)
            self._set_status(f"Could not start {mode.name}: {exc}", theme.DANGER)
            return

        self.current_mode = mode_id
        self._capability_warning = None
        self.preview_title.configure(text=mode.name)
        self.preview_desc.configure(text=mode.description)
        for card_id, card in self._cards.items():
            card.set_selected(card_id == mode_id)
        self._set_status(f"Starting {mode.name}...", theme.MUTED)

    def cycle_mode(self) -> None:
        ids = [mode.id for mode in MODES]
        try:
            index = ids.index(self.current_mode)
        except ValueError:
            index = -1
        self.apply_mode(ids[(index + 1) % len(ids)])

    def _start_default_mode(self) -> None:
        if self._closing:
            return
        mode_id = str(self.config.get("default_mode", "type"))
        if mode_id not in {mode.id for mode in MODES}:
            return
        try:
            mode = get_mode(mode_id)
        except KeyError:
            return
        if "keyboard" in mode.needs and not keyboard_available():
            detail = (
                "Key-reactive modes need read access to /dev/input.\n"
                "Run: sudo usermod -aG input $USER\n"
                "then log out and back in (or switch the session to X11).\n\n"
                "Every other mode works without this."
            )
            self.apply_mode("breathing")
            self._capability_warning = "keyboard effects need input access"
            self._last_error = detail
            self._set_status(
                f"{mode.name} needs input access; showing Breathing. Click for details.",
                theme.WARNING,
                detail=detail,
            )
            return
        self.apply_mode(mode_id)

    # ------------------------------------------------------------ engine glue
    def post(self, callback, *args) -> None:
        """Queue work from a non-Tk thread (engine, tray, hotkey listener)."""
        if not self._closing:
            self._events.put((callback, args))

    def _drain_events(self) -> None:
        while True:
            try:
                callback, args = self._events.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except Exception:
                log.exception("UI event failed")

    def _on_engine_state(self, snapshot: Dict[str, object]) -> None:
        self.post(self._apply_snapshot, snapshot)

    def _apply_snapshot(self, snapshot: Dict[str, object]) -> None:
        if self._closing:
            return
        state = str(snapshot.get("state", IDLE))
        mode_id = str(snapshot.get("mode") or self.current_mode)
        try:
            name = get_mode(mode_id).name
        except KeyError:
            name = mode_id
        if state == RUNNING:
            notes = []
            if self.demo:
                notes.append("demo mode")
            if self._capability_warning:
                notes.append(self._capability_warning)
            if notes:
                self._set_status(f"{name} is running · {' · '.join(notes)}", theme.WARNING)
            else:
                self._last_error = ""
                self._set_status(f"{name} is running", theme.SUCCESS)
        elif state == ERROR:
            error = str(snapshot.get("error") or "Unknown error")
            self._last_error = error
            self._set_status(f"{name} stopped: {error}", theme.DANGER, detail=error)
        elif state == IDLE and mode_id == self.current_mode:
            self._set_status("Stopped", theme.MUTED)

    def _tick(self) -> None:
        if self._closing:
            return
        try:
            self._drain_events()
            if self._show_requested:
                self._show_requested = False
                self.show_window()
            self.preview.set_colors(self.engine.colors)
            self.root.after(80, self._tick)
        except tk.TclError:
            pass

    # ---------------------------------------------------------------- status
    def _set_status(self, text: str, color: str, detail: Optional[str] = None) -> None:
        message = " ".join(str(text).split())
        if len(message) > 140:
            message = message[:137] + "..."
        self.status_label.configure(text=message, fg=color)
        if detail is not None:
            self._last_error = detail
        elif color == theme.DANGER:
            self._last_error = str(text)

    def _status_clicked(self, _event: object = None) -> None:
        if self._last_error:
            self._show_details("Something needs attention", self._last_error)
        else:
            self._show_details("Diagnostics", self._diagnostic_text())

    def _diagnostic_text(self) -> str:
        device_line = (
            self.device.info.label
            if self.device.info is not None
            else "No hardware connected (demo mode)"
        )
        lines = [
            f"Lenovo RGB v{__version__}",
            f"Device: {device_line}",
            f"Mode: {self.current_mode or 'none'}",
            f"Engine: {self.engine.state}",
            "Input backend: "
            + (self._hotkey_monitor.backend if self._hotkey_monitor else "disabled"),
            f"Config: {self.config.path}",
            "",
            "If the lights do not react, run: lenovorgb doctor",
        ]
        return "\n".join(lines)

    def _show_details(self, title: str, body: str) -> None:
        window = tk.Toplevel(self.root)
        window.title(title)
        window.configure(bg=theme.BG)
        self._enable_dark_titlebar(window)
        window.transient(self.root)
        window.minsize(460, 300)

        header = tk.Frame(window, bg=theme.BG)
        header.pack(fill="x", padx=20, pady=(18, 8))
        tk.Label(
            header,
            text=title,
            font=self.fonts.heading,
            bg=theme.BG,
            fg=theme.TEXT,
            anchor="w",
        ).pack(side="left")

        frame = tk.Frame(window, bg=theme.SURFACE, highlightthickness=1, highlightbackground=theme.BORDER)
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        text = tk.Text(
            frame,
            bg=theme.SURFACE,
            fg=theme.TEXT_SECONDARY,
            font=self.fonts.mono,
            wrap="word",
            relief="flat",
            bd=0,
            padx=14,
            pady=12,
            insertbackground=theme.TEXT,
            height=14,
        )
        text.pack(fill="both", expand=True)
        text.insert("1.0", body)
        text.configure(state="disabled")

        footer = tk.Frame(window, bg=theme.BG)
        footer.pack(fill="x", padx=20, pady=(0, 18))
        FlatButton(
            footer,
            text="Close",
            command=window.destroy,
            font=self.fonts.button,
            variant="solid",
            padx=20,
        ).pack(side="right")

        window.bind("<Escape>", lambda _event: window.destroy())
        window.update_idletasks()
        width = 560
        height = min(520, max(320, text.winfo_reqheight() + 150))
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 3
        window.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

    # -------------------------------------------------------------- settings
    def show_settings(self) -> None:
        if self._settings_window is not None:
            try:
                if self._settings_window.winfo_exists():
                    self._settings_window.lift()
                    self._settings_window.focus_force()
                    return
            except tk.TclError:
                pass
            self._settings_window = None

        window = tk.Toplevel(self.root)
        self._settings_window = window
        window.title("Settings")
        window.configure(bg=theme.BG)
        self._enable_dark_titlebar(window)
        window.transient(self.root)
        window.resizable(False, False)

        header = tk.Frame(window, bg=theme.BG)
        header.pack(fill="x", padx=24, pady=(20, 4))
        tk.Label(
            header,
            text="Settings",
            font=self.fonts.heading,
            bg=theme.BG,
            fg=theme.TEXT,
            anchor="w",
        ).pack(side="left")
        tk.Label(
            header,
            text="Changes are saved to your config file",
            font=self.fonts.small,
            bg=theme.BG,
            fg=theme.MUTED,
            anchor="w",
        ).pack(side="left", padx=(10, 0), pady=(3, 0))

        form = tk.Frame(window, bg=theme.BG)
        form.pack(fill="both", expand=True, padx=24, pady=(10, 0))

        minimize_var = tk.BooleanVar(value=bool(self.config.get("start_minimized", True)))
        row = self._settings_row(form, "Start minimized", "Open straight to the system tray")
        Switch(row, minimize_var, bg=theme.BG).pack(side="right")

        login_var = tk.BooleanVar(value=autostart.is_enabled())
        row = self._settings_row(form, "Launch at login", "Start automatically when you sign in")
        Switch(row, login_var, bg=theme.BG).pack(side="right")

        hotkey_var = tk.BooleanVar(value=bool(self.config.get("hotkey_enabled", True)))
        row = self._settings_row(form, "Cycle mode hotkey", "Switch to the next effect from anywhere")
        Switch(row, hotkey_var, bg=theme.BG).pack(side="right")

        mode_names = [mode.name for mode in MODES]
        name_to_id = {mode.name: mode.id for mode in MODES}
        current_default = str(self.config.get("default_mode", "type"))
        try:
            default_name = get_mode(current_default).name
        except KeyError:
            default_name = mode_names[0]
        default_var = tk.StringVar(value=default_name)
        row = self._settings_row(form, "Default mode", "Applied when the app starts")
        combo = ttk.Combobox(
            row,
            textvariable=default_var,
            values=mode_names,
            state="readonly",
            width=20,
            style="RGB.TCombobox",
        )
        combo.pack(side="right")

        hotkey_value = tk.StringVar(value=str(self.config.get("hotkey", "ctrl+shift+m")))
        row = self._settings_row(form, "Shortcut", "e.g. ctrl+shift+m")
        entry = tk.Entry(
            row,
            textvariable=hotkey_value,
            font=self.fonts.body,
            bg=theme.SURFACE,
            fg=theme.TEXT,
            insertbackground=theme.TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            highlightcolor=theme.ACCENT,
            width=18,
        )
        entry.pack(side="right", ipady=5, padx=(0, 2))

        separator(form, theme.BORDER).pack(fill="x", pady=(14, 10))

        pomodoro = self.config.get("pomodoro", {})
        work_var = tk.IntVar(value=int(pomodoro.get("work_minutes", 25)))
        break_var = tk.IntVar(value=int(pomodoro.get("break_minutes", 5)))
        row = self._settings_row(form, "Pomodoro", "Focus and break length in minutes")
        break_spin = self._spinbox(row, break_var, 1, 60)
        break_spin.pack(side="right")
        tk.Label(
            row, text="break", font=self.fonts.small, bg=theme.BG, fg=theme.MUTED
        ).pack(side="right", padx=6)
        work_spin = self._spinbox(row, work_var, 1, 180)
        work_spin.pack(side="right")
        tk.Label(
            row, text="work", font=self.fonts.small, bg=theme.BG, fg=theme.MUTED
        ).pack(side="right", padx=6)

        hint = tk.Label(
            form,
            text="The cycle hotkey needs at least one modifier (Ctrl, Alt, Shift or Super).",
            font=self.fonts.small,
            bg=theme.BG,
            fg=theme.MUTED,
            anchor="w",
            justify="left",
            wraplength=420,
        )
        hint.pack(fill="x", pady=(12, 0))

        buttons = tk.Frame(window, bg=theme.BG)
        buttons.pack(fill="x", padx=24, pady=(16, 20))
        FlatButton(
            buttons,
            text="Cancel",
            command=window.destroy,
            font=self.fonts.button,
            variant="ghost",
            padx=18,
        ).pack(side="right", padx=(8, 0))
        FlatButton(
            buttons,
            text="Save changes",
            command=lambda: self._save_settings(
                window,
                minimize_var,
                login_var,
                hotkey_var,
                default_var,
                hotkey_value,
                work_var,
                break_var,
                name_to_id,
            ),
            font=self.fonts.button,
            variant="solid",
            padx=18,
        ).pack(side="right")

        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.bind("<Escape>", lambda _event: window.destroy())
        window.update_idletasks()
        width = 520
        height = window.winfo_reqheight()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + max(20, (self.root.winfo_height() - height) // 3)
        window.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        window.grab_set()
        window.focus_force()

    def _settings_row(self, parent: tk.Frame, title: str, hint: str) -> tk.Frame:
        container = tk.Frame(parent, bg=theme.BG)
        container.pack(fill="x", pady=7)
        text = tk.Frame(container, bg=theme.BG)
        text.pack(side="left", anchor="w")
        tk.Label(
            text,
            text=title,
            font=self.fonts.body,
            bg=theme.BG,
            fg=theme.TEXT,
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            text,
            text=hint,
            font=self.fonts.small,
            bg=theme.BG,
            fg=theme.MUTED,
            anchor="w",
        ).pack(anchor="w", pady=(1, 0))
        return container

    def _spinbox(self, parent: tk.Frame, variable: tk.IntVar, low: int, high: int) -> tk.Spinbox:
        return tk.Spinbox(
            parent,
            from_=low,
            to=high,
            textvariable=variable,
            width=5,
            font=self.fonts.body,
            bg=theme.SURFACE,
            fg=theme.TEXT,
            buttonbackground=theme.SURFACE_ACTIVE,
            insertbackground=theme.TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground=theme.BORDER,
            highlightcolor=theme.ACCENT,
            justify="center",
        )

    def _save_settings(
        self,
        window: tk.Toplevel,
        minimize_var: tk.BooleanVar,
        login_var: tk.BooleanVar,
        hotkey_var: tk.BooleanVar,
        default_var: tk.StringVar,
        hotkey_value: tk.StringVar,
        work_var: tk.IntVar,
        break_var: tk.IntVar,
        name_to_id: Dict[str, str],
    ) -> None:
        hotkey = (hotkey_value.get() or "").strip().lower()
        modifiers, key = parse_hotkey(hotkey)
        if not key or not modifiers:
            self._set_status(
                "Shortcut must be a key combined with a modifier, e.g. ctrl+shift+m",
                theme.DANGER,
            )
            hotkey_value.set(str(self.config.get("hotkey", "ctrl+shift+m")))
            return

        try:
            work = max(1, min(180, int(work_var.get())))
            rest = max(1, min(60, int(break_var.get())))
        except (ValueError, tk.TclError):
            self._set_status("Pomodoro values must be whole minutes", theme.DANGER)
            return

        mode_id = name_to_id.get(default_var.get(), str(self.config.get("default_mode", "type")))
        previous_login = autostart.is_enabled()

        self.config.set("start_minimized", bool(minimize_var.get()))
        self.config.set("launch_at_login", bool(login_var.get()))
        self.config.set("hotkey_enabled", bool(hotkey_var.get()))
        self.config.set("hotkey", hotkey)
        self.config.set("default_mode", mode_id)
        self.config.set("pomodoro.work_minutes", work)
        self.config.set("pomodoro.break_minutes", rest)
        saved = self.config.save()

        if bool(login_var.get()) != previous_login:
            if login_var.get():
                ok, message = autostart.enable(minimized=bool(minimize_var.get()))
            else:
                ok, message = autostart.disable()
            log.info("Autostart: %s", message)
            if not ok:
                self.config.set("launch_at_login", previous_login)
                self.config.save()
                self._set_status(message, theme.DANGER)
                window.destroy()
                return

        self._start_hotkey()
        window.destroy()
        self._set_status(
            "Settings saved" if saved else "Settings applied, but the config could not be written",
            theme.SUCCESS if saved else theme.WARNING,
        )

    # ----------------------------------------------------------------- hotkey
    def _start_hotkey(self) -> None:
        if self._hotkey_monitor is not None:
            self._hotkey_monitor.stop()
            self._hotkey_monitor = None
        if not bool(self.config.get("hotkey_enabled", True)):
            return
        spec = str(self.config.get("hotkey", "ctrl+shift+m"))
        monitor = KeyboardMonitor(on_hotkey=self._hotkey_triggered, hotkey=spec)
        try:
            monitor.start()
            self._hotkey_monitor = monitor
            log.info("Cycle hotkey bound to %s via %s", spec, monitor.backend)
        except Exception as exc:
            log.info("Cycle hotkey unavailable: %s", exc)

    def _hotkey_triggered(self) -> None:
        self.post(self.cycle_mode)

    # -------------------------------------------------------- window control
    def _persist_window_size(self) -> None:
        try:
            if self.root.state() == "normal":
                width = self.root.winfo_width()
                height = self.root.winfo_height()
                if width > 200 and height > 200:
                    self.config.set("window.width", width)
                    self.config.set("window.height", height)
        except tk.TclError:
            pass

    def _save_config_later(self, delay: int = 600) -> None:
        if self._save_job is not None:
            try:
                self.root.after_cancel(self._save_job)
            except (tk.TclError, ValueError):
                pass
        self._save_job = self.root.after(delay, self._flush_config)

    def _flush_config(self) -> None:
        self._save_job = None
        self.config.save()

    def _on_brightness(self, value: str) -> None:
        percent = max(0, min(100, int(float(value))))
        self.brightness_value.configure(text=f"{percent}%")
        if self.engine is not None:
            self.engine.set_brightness(percent)
        if not self._closing:
            self._save_config_later()

    def show_window(self) -> None:
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError:
            pass

    def hide_window(self) -> None:
        try:
            self.root.withdraw()
        except tk.TclError:
            pass

    def on_close(self) -> None:
        if self.has_tray:
            self.hide_window()
            self._set_status("Still running in the tray. Click the tray icon to reopen.", theme.MUTED)
        else:
            self.quit_app()

    def _arm_exit_watchdog(self) -> None:
        """Never let a stuck tray/driver thread keep the process alive."""

        def watchdog() -> None:
            time.sleep(3.0)
            os._exit(0)

        threading.Thread(target=watchdog, name="exit-watchdog", daemon=True).start()

    def quit_app(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._arm_exit_watchdog()
        self._persist_window_size()
        self.config.save()
        if self._hotkey_monitor is not None:
            self._hotkey_monitor.stop()
            self._hotkey_monitor = None
        self.tray.stop()
        off = bool(self.config.get("off_on_exit", True))
        self.engine.shutdown(off=off)
        try:
            self.root.quit()
        except tk.TclError:
            pass

    def cleanup(self) -> None:
        if self._cleaned:
            return
        self._cleaned = True
        self._closing = True
        try:
            if self._hotkey_monitor is not None:
                self._hotkey_monitor.stop()
                self._hotkey_monitor = None
            self.tray.stop()
            self._persist_window_size()
            self.config.save()
            self.engine.shutdown()
        except Exception:
            log.exception("Error during shutdown")

"""Command line interface and application entry point."""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import List, Optional

from . import __version__, autostart
from .colors import parse_hex, to_hex
from .config import Config
from .device import DeviceError, RGBDevice
from .engine import ERROR, LightingEngine
from .lock import InstanceLock
from .log import get, setup
from .modes import CATEGORIES, CATEGORY_ORDER, MODES, get_mode

log = get("cli")


def _echo(message: str = "", error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    if stream is None:
        log.info("%s", message)
        return
    try:
        print(message, file=stream)
    except OSError:
        log.info("%s", message)


def _common_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--config",
        metavar="FILE",
        type=Path,
        default=argparse.SUPPRESS,
        help="use an alternative config file",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", default=argparse.SUPPRESS, help="debug logging"
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    common = _common_parser()
    parser = argparse.ArgumentParser(
        prog="lenovorgb",
        description="Control the 4-zone RGB keyboard on Lenovo LOQ and Legion laptops.",
        parents=[common],
        epilog="Run 'lenovorgb doctor' if something is not working.",
    )
    parser.add_argument("--version", action="version", version=f"LenovoRGB {__version__}")
    sub = parser.add_subparsers(dest="command")

    gui = sub.add_parser("gui", parents=[common], help="open the desktop app (default)")
    gui.add_argument("--minimized", action="store_true", help="start hidden in the tray")
    gui.add_argument("--show", action="store_true", help="force the window to open")
    gui.add_argument("--no-tray", action="store_true", help="disable the tray icon")
    gui.add_argument("--demo", action="store_true", help="preview without a keyboard attached")

    run = sub.add_parser("run", parents=[common], help="run one lighting mode")
    run.add_argument("mode", nargs="?", help="mode id (default: configured mode)")
    run.add_argument("--demo", "--dry-run", dest="demo", action="store_true", help="do not write to hardware")
    run.add_argument("--brightness", type=int, metavar="0-100", help="override brightness")
    run.add_argument("--color", metavar="RRGGBB", help="colour for the solid mode")

    off = sub.add_parser("off", parents=[common], help="turn the keyboard lighting off")
    off.add_argument("--demo", action="store_true")

    solid = sub.add_parser("solid", parents=[common], help="set a solid colour")
    solid.add_argument("color", nargs="?", default=None, metavar="RRGGBB")
    solid.add_argument("--demo", action="store_true")

    listing = sub.add_parser("list", parents=[common], help="list all modes")
    listing.add_argument("--json", action="store_true", help="machine-readable output")

    sub.add_parser("doctor", parents=[common], help="diagnose hardware and permissions")

    auto = sub.add_parser("autostart", parents=[common], help="start the tray app at login")
    auto.add_argument("action", choices=["enable", "disable", "status"])
    auto.add_argument("--show", action="store_true", help="open the window at login instead of the tray")

    shortcut = sub.add_parser(
        "shortcut", parents=[common], help="install or remove the application menu entry"
    )
    shortcut.add_argument("action", choices=["install", "remove"])

    return parser


def _translate_legacy(argv: List[str]) -> List[str]:
    """Accept the old ``python loq_rgb.py --mode fire`` invocation."""
    if "--list-modes" in argv:
        argv = [part for part in argv if part != "--list-modes"] + ["list"]
    if "--mode" in argv:
        index = argv.index("--mode")
        try:
            mode = argv[index + 1]
        except IndexError:
            return argv
        rest = argv[:index] + argv[index + 2 :]
        argv = ["run", mode, *rest]
    return argv


def _make_config(args: argparse.Namespace) -> Config:
    path = getattr(args, "config", None)
    return Config(path=Path(path) if path else None)


def _open_device(config: Config, demo: bool, required: bool = True) -> Optional[RGBDevice]:
    try:
        device = RGBDevice(
            path=config.get("device.path"),
            product_id=config.get("device.product_id"),
            dry_run=demo,
            brightness=config.brightness,
        )
    except DeviceError as exc:
        if not required:
            return None
        _echo(str(exc), error=True)
        _echo("", error=True)
        _echo("Tips:", error=True)
        _echo("  * Linux: run sudo ./install.sh (installs the udev rule)", error=True)
        _echo("  * Windows: open Lenovo Vantage once and set the lighting profile to Static", error=True)
        _echo("  * Try any mode without hardware using --demo", error=True)
        return None
    if demo:
        _echo("Demo mode: no data is being sent to the keyboard.")
    elif device.info is not None:
        log.info("Using %s", device.info.label)
    return device


def _install_signal_handlers(stop: threading.Event) -> None:
    def handler(signum: int, frame: object) -> None:
        log.debug("Received signal %s", signum)
        stop.set()

    for name in ("SIGINT", "SIGTERM", "SIGHUP"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass


def _install_windows_cleanup(engine: LightingEngine) -> object:
    if os.name != "nt":
        return None
    import ctypes

    handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

    def handler(ctrl_type: int) -> bool:
        if ctrl_type in (0, 1, 2, 5, 6):  # Ctrl-C, break, close, logoff, shutdown
            try:
                engine.shutdown(off=True)
                engine.device.close()
            finally:
                os._exit(0)
        return False

    reference = handler_type(handler)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(reference, True)
    return reference


def _run_mode(
    config: Config,
    mode: str,
    demo: bool,
    brightness: Optional[int],
    color: Optional[str] = None,
) -> int:
    try:
        get_mode(mode)
    except KeyError as exc:
        _echo(str(exc), error=True)
        return 2

    if brightness is not None:
        config.brightness = brightness
        if not 0 <= brightness <= 100:
            _echo("Brightness must be between 0 and 100.", error=True)
            return 2

    lock = InstanceLock()
    if not lock.acquire():
        _echo(lock.busy_message(), error=True)
        return 1

    engine: Optional[LightingEngine] = None
    device: Optional[RGBDevice] = None
    stop = threading.Event()
    try:
        device = _open_device(config, demo=demo, required=True)
        if device is None:
            return 3
        engine = LightingEngine(device, config)
        _install_signal_handlers(stop)
        engine.win_handler = _install_windows_cleanup(engine)  # keep the callback alive
        options = {"color": color} if color else {}
        engine.set_mode(mode, options)
        mode_class = get_mode(mode)
        _echo(f"Mode: {mode_class.name} - {mode_class.description}")
        _echo("Press Ctrl+C to stop.")

        while not stop.is_set() and engine.active:
            time.sleep(0.2)
        if engine.state == ERROR:
            _echo("", error=True)
            _echo(f"Stopped with an error: {engine.error}", error=True)
            return 1
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        stop.set()
        if engine is not None:
            engine.shutdown()
        elif device is not None:
            device.off()
        if device is not None:
            device.close()
        lock.release()


def _cmd_off(config: Config, demo: bool) -> int:
    lock = InstanceLock()
    if not lock.acquire():
        _echo(lock.busy_message(), error=True)
        return 1
    device: Optional[RGBDevice] = None
    try:
        device = _open_device(config, demo=demo)
        if device is None:
            return 3
        device.off()
        _echo("Keyboard lighting is off.")
        return 0
    finally:
        if device is not None:
            device.close()
        lock.release()


def _cmd_solid(config: Config, color: Optional[str], demo: bool) -> int:
    raw = color or str(config.get("static_color", "#5B8CFF"))
    parsed = parse_hex(raw, default=None)  # type: ignore[arg-type]
    if parsed is None:
        _echo(f"Invalid colour '{raw}'. Use a hex value such as #ff5500.", error=True)
        return 2

    lock = InstanceLock()
    if not lock.acquire():
        _echo(lock.busy_message(), error=True)
        return 1
    device: Optional[RGBDevice] = None
    try:
        device = _open_device(config, demo=demo)
        if device is None:
            return 3
        device.set_colors([parsed] * 4, force=True)
        config.set("static_color", to_hex(parsed))
        config.save()
        _echo(f"Solid colour set to {to_hex(parsed)}.")
        return 0
    finally:
        if device is not None:
            device.close()
        lock.release()


def _cmd_list(as_json: bool) -> int:
    if as_json:
        payload = [
            {
                "id": mode.id,
                "name": mode.name,
                "category": mode.category,
                "description": mode.description,
                "needs": list(mode.needs),
            }
            for mode in MODES
        ]
        _echo(json.dumps(payload, indent=2))
        return 0

    _echo(f"LenovoRGB {__version__} - {len(MODES)} modes")
    _echo("")
    for category in CATEGORY_ORDER:
        modes = [mode for mode in MODES if mode.category == category]
        if not modes:
            continue
        _echo(f"{CATEGORIES.get(category, category).upper()}")
        for mode in modes:
            _echo(f"  {mode.id:<10} {mode.name:<18} {mode.description}")
        _echo("")
    _echo("Run one with: lenovorgb run <id>")
    _echo("See all commands: lenovorgb --help")
    return 0


def _cmd_autostart(action: str, minimized: bool, config: Config) -> int:
    if action == "status":
        enabled, detail = autostart.status()
        _echo(f"Launch at login: {'enabled' if enabled else 'disabled'}")
        _echo(f"  {detail}")
        return 0
    if action == "enable":
        ok, detail = autostart.enable(minimized=minimized)
        _echo(detail, error=not ok)
        if ok:
            config.set("launch_at_login", True)
            config.save()
        return 0 if ok else 1
    ok, detail = autostart.disable()
    _echo(detail, error=not ok)
    if ok:
        config.set("launch_at_login", False)
        config.save()
    return 0 if ok else 1


def _cmd_gui(args: argparse.Namespace, config: Config) -> int:
    try:
        from .ui.app import launch
    except ImportError as exc:
        message = str(exc)
        _echo(f"The graphical interface could not start: {message}", error=True)
        lowered = message.lower()
        if "tkinter" in lowered or "libtk" in lowered or "_tkinter" in lowered:
            _echo(
                "Install Tk for your distribution "
                "(Arch: sudo pacman -S tk, Debian/Ubuntu: sudo apt install python3-tk, "
                "Fedora: sudo dnf install python3-tkinter).",
                error=True,
            )
        else:
            _echo("Reinstall the optional packages: pip install -e '.[all]'", error=True)
        _echo("You can still use 'lenovorgb run <mode>' without the window.", error=True)
        return 1
    minimized = bool(config.get("start_minimized", True))
    if getattr(args, "show", False):
        minimized = False
    elif getattr(args, "minimized", False):
        minimized = True
    no_tray = bool(getattr(args, "no_tray", False))
    demo = bool(getattr(args, "demo", False))
    return launch(config, minimized=minimized, no_tray=no_tray, demo=demo)


def main(argv: Optional[List[str]] = None) -> int:
    multiprocessing.freeze_support()
    raw = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(_translate_legacy(raw))
    setup(verbose=bool(getattr(args, "verbose", False)))
    config = _make_config(args)

    try:
        command = args.command
        if command in (None, "gui"):
            return _cmd_gui(args, config)
        if command == "run":
            mode = args.mode or str(config.get("default_mode", "type"))
            if mode == "off":
                return _cmd_off(config, demo=args.demo)
            return _run_mode(
                config,
                mode,
                demo=args.demo,
                brightness=args.brightness,
                color=args.color,
            )
        if command == "solid":
            return _cmd_solid(config, args.color, demo=args.demo)
        if command == "off":
            return _cmd_off(config, demo=args.demo)
        if command == "list":
            return _cmd_list(args.json)
        if command == "doctor":
            from . import doctor

            return doctor.run(config)
        if command == "autostart":
            return _cmd_autostart(args.action, minimized=not args.show, config=config)
        if command == "shortcut":
            if args.action == "install":
                ok, detail = autostart.write_menu_entry()
            else:
                ok, detail = autostart.remove_menu_entry()
            _echo(detail, error=not ok)
            return 0 if ok else 1
        _echo(f"Unknown command: {command}", error=True)
        return 2
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0


def gui_entry() -> None:
    argv = sys.argv[1:]
    if not argv:
        argv = ["gui"]
    sys.exit(main(argv))


if __name__ == "__main__":
    sys.exit(main())

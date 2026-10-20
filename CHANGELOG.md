# Changelog

## 2.0.0 — 2026-10-21

A ground-up rewrite of the Windows-only script into a cross-platform app.

### Added

- **Linux support.** The app uses the `hidraw` backend, so it finds the vendor lighting collection (`0xff89:0x00cc`) and writes to `/dev/hidraw*`. A udev rule grants the active user access without root.
- **One-command installers.** `install.sh` creates a venv, installs dependencies, adds the udev rule, menu entry, `lenovorgb` command and login autostart. `install.ps1` does the Windows equivalent with a Start Menu shortcut and login entry.
- **New desktop UI.** Dark, card-based library with categories, live four-zone preview, brightness slider, search-free filtering, settings dialog, and a status bar that explains failures.
- **Tray menu and global hotkey** (`Ctrl+Shift+M` by default) to cycle modes.
- **`lenovorgb doctor`** reports hardware, permissions, input, audio, screen capture, lock state and recent logs.
- **Demo mode** (`--demo`) renders every effect without hardware.
- **Automatic fallback**: on a Wayland session without input permissions the app starts a safe ambient mode instead of showing a broken reactive mode.
- **Reconnect logic** after suspend or a transient USB error.
- **Shutdown cleanup** on Ctrl+C, SIGTERM, SIGHUP, Windows logoff/shutdown, and normal window close.
- **Config migration** from the old `config.json` (`shortcut`, `startup_minimized`).
- **Tests and CI** for Linux, Windows and macOS on Python 3.10 and 3.13, plus tagged release builds.

### Changed

- Configuration lives in the platform config directory instead of next to the script:
  - Linux: `~/.config/lenovorgb/config.json`
  - Windows: `%APPDATA%\LenovoRGB\config.json`
- Effects are now small classes in `modes/` with a shared engine and a single device owner.
- Audio/screen/keyboard capabilities are optional extras; failures are reported per mode.
- Tray support is skipped automatically when the desktop has no system tray, instead of trapping the window in a hidden state.

### Fixed

- Linux could not identify the RGB interface because the libusb HID backend reports zeroed usage pages; the Linux build now uses `hidraw`.
- Multiple instances could fight over the LEDs; a cross-platform single-instance lock prevents it.
- Config writes are atomic and no longer corrupt on a crash.
- The keyboard is no longer left lit after a crash or logout.
- Screen Ambilight no longer outputs white for dark/grayscale content.
- Reactive modes no longer silently do nothing when global input is unavailable.
- Lights are turned off even when a mode raises during setup.

### Breaking

- `loq_rgb.py`, `ui.py` and the per-mode `.bat` files were removed. Use `lenovorgb run <mode>`, `lenovorgb`, and the installers. The old `--mode` flag is still translated for compatibility.
- The default global shortcut is now configurable in Settings and stored as `hotkey` (the old `shortcut` key is migrated).

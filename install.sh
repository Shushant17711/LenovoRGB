#!/usr/bin/env bash
# Lenovo RGB - Linux installer
# Usage: ./install.sh [--no-udev] [--no-autostart] [--with-input] [--cli-only] [--dev] [-y]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

NO_UDEV=0
NO_AUTOSTART=0
WITH_INPUT=0
NO_INPUT=0
CLI_ONLY=0
DEV=0
ASSUME_YES=0

for arg in "$@"; do
  case "$arg" in
    --no-udev) NO_UDEV=1 ;;
    --no-autostart) NO_AUTOSTART=1 ;;
    --with-input) WITH_INPUT=1 ;;
    --no-input) NO_INPUT=1 ;;
    --cli-only) CLI_ONLY=1 ;;
    --dev) DEV=1 ;;
    -y|--yes) ASSUME_YES=1 ;;
    -h|--help)
      cat <<'EOF'
Lenovo RGB installer

  --no-udev        do not install /etc/udev/rules.d/99-lenovorgb.rules
  --no-autostart   do not start the tray app at login
  --with-input     add your user to the 'input' group (needed for key-reactive
                   modes on Wayland; requires a logout)
  --no-input       never touch the 'input' group
  --cli-only       install without checking for tkinter (no desktop app)
  --dev            also install pytest, ruff and pyinstaller
  -y, --yes        do not ask anything
EOF
      exit 0
      ;;
    *) echo "Unknown option: $arg (use --help)" >&2; exit 2 ;;
  esac
done

say() { printf '%s\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
ok() { printf '\033[32m%s\033[0m\n' "$*"; }
die() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

if [ "$(uname -s)" != "Linux" ]; then
  die "This installer is for Linux. On Windows run: powershell -ExecutionPolicy Bypass -File install.ps1"
fi

if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ]; then
  die "Run ./install.sh as your normal user, without sudo. It asks for sudo only when needed."
fi

PYTHON="${PYTHON:-python3}"
USER_NAME="${SUDO_USER:-${USER:-$(id -un)}}"
command -v "$PYTHON" >/dev/null 2>&1 || die "python3 was not found. Install Python 3.9 or newer."

"$PYTHON" - <<'PY' || die "Python 3.9 or newer is required."
import sys
if sys.version_info < (3, 9):
    print(f"Found Python {sys.version.split()[0]}, need 3.9+")
    raise SystemExit(1)
PY

run_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

if ! command -v sudo >/dev/null 2>&1 && [ "$(id -u)" -ne 0 ]; then
  warn "sudo was not found. System packages, udev and input-group steps will be skipped."
  NO_UDEV=1
  WITH_INPUT=0
  NO_INPUT=1
fi

install_tk() {
  if command -v pacman >/dev/null 2>&1; then
    run_root pacman -S --needed --noconfirm tk
  elif command -v apt-get >/dev/null 2>&1; then
    run_root apt-get install -y python3-tk
  elif command -v dnf >/dev/null 2>&1; then
    run_root dnf install -y python3-tkinter
  elif command -v zypper >/dev/null 2>&1; then
    run_root zypper install -y python3-tk
  elif command -v apk >/dev/null 2>&1; then
    run_root apk add tk
  elif command -v xbps-install >/dev/null 2>&1; then
    run_root xbps-install -y tk
  else
    return 1
  fi
}

if [ "$CLI_ONLY" -eq 0 ]; then
  if ! "$PYTHON" -c "import tkinter" >/dev/null 2>&1; then
    warn "Python's tkinter module is missing, so the desktop app cannot start."
    INSTALL_TK=0
    if [ "$(id -u)" -eq 0 ] || command -v sudo >/dev/null 2>&1; then
      if [ "$ASSUME_YES" -eq 1 ]; then
        INSTALL_TK=1
      elif [ -t 0 ]; then
        printf 'Install the system Tk package now? [Y/n] '
        read -r reply || reply="n"
        case "$reply" in ""|y|Y|yes|YES) INSTALL_TK=1 ;; esac
      fi
    fi
    if [ "$INSTALL_TK" -eq 1 ]; then
      say "Installing Tk (this may ask for your password) ..."
      if install_tk && "$PYTHON" -c "import tkinter" >/dev/null 2>&1; then
        ok "Tk installed."
      else
        warn "Automatic Tk installation failed."
      fi
    fi
    if ! "$PYTHON" -c "import tkinter" >/dev/null 2>&1; then
      warn "Install it manually, then re-run ./install.sh:"
      warn "  Arch: sudo pacman -S tk"
      warn "  Debian/Ubuntu: sudo apt install python3-tk"
      warn "  Fedora: sudo dnf install python3-tkinter"
      warn "  openSUSE: sudo zypper install python3-tk"
      warn "Or re-run with --cli-only to install just the command line tool."
      exit 1
    fi
  fi
fi

say ""
say "Lenovo RGB installer"
say "===================="
say "Project: $ROOT"
say ""

# ---------------------------------------------------------------- venv + pip
if [ -d "$ROOT/.venv" ] && [ ! -x "$ROOT/.venv/bin/python" ]; then
  warn "Removing an incomplete .venv ..."
  rm -rf "$ROOT/.venv"
fi
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  say "Creating virtual environment in .venv ..."
  if ! "$PYTHON" -m venv "$ROOT/.venv"; then
    die "Could not create the virtual environment. On Debian/Ubuntu install python3-venv."
  fi
fi
VENV_PY="$ROOT/.venv/bin/python"
say "Installing Python packages (this can take a minute) ..."
"$VENV_PY" -m pip install --upgrade pip wheel >/dev/null
EXTRAS="all"
if [ "$DEV" -eq 1 ]; then EXTRAS="all,dev"; fi
if ! "$VENV_PY" -m pip install -e ".[${EXTRAS}]"; then
  die "pip install failed. Install build tools first: Arch: sudo pacman -S --needed base-devel; Debian/Ubuntu: sudo apt install build-essential python3-dev"
fi
ok "Python packages installed."

if ! "$VENV_PY" -c "import sys; sys.argv.append('check'); import soundcard" >/dev/null 2>&1; then
  warn "Audio visualizer could not load the PulseAudio library (libpulse)."
  warn "  Arch: sudo pacman -S libpulse    Debian/Ubuntu: sudo apt install libpulse0"
fi

# ---------------------------------------------------------------- launcher
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
if [ -e "$BIN_DIR/lenovorgb" ] && [ ! -L "$BIN_DIR/lenovorgb" ]; then
  mv "$BIN_DIR/lenovorgb" "$BIN_DIR/lenovorgb.backup.$(date +%s)"
fi
ln -sfn "$ROOT/.venv/bin/lenovorgb" "$BIN_DIR/lenovorgb"
ok "Command installed: $BIN_DIR/lenovorgb"

# ---------------------------------------------------------------- udev rule
if [ "$NO_UDEV" -eq 0 ]; then
  RULE_SRC="$ROOT/packaging/99-lenovorgb.rules"
  RULE_DST="/etc/udev/rules.d/99-lenovorgb.rules"
  if [ -f "$RULE_SRC" ]; then
    say "Installing udev rule so the keyboard can be controlled without root ..."
    if run_root install -m 644 "$RULE_SRC" "$RULE_DST" 2>/dev/null; then
      run_root udevadm control --reload-rules >/dev/null 2>&1 || true
      run_root udevadm trigger --subsystem-match=hidraw >/dev/null 2>&1 || true
      ok "udev rule installed."
    else
      warn "Could not install the udev rule (no permission)."
      warn "Run later: sudo install -m644 packaging/99-lenovorgb.rules /etc/udev/rules.d/"
    fi
  fi
else
  say "Skipping udev rule (--no-udev)."
fi

# ---------------------------------------------------------------- menu entry
if [ "$CLI_ONLY" -eq 0 ]; then
  "$VENV_PY" -m lenovorgb shortcut install >/dev/null 2>&1 || warn "Could not add the application menu entry."
fi

# ---------------------------------------------------------------- autostart
if [ "$NO_AUTOSTART" -eq 0 ] && [ "$CLI_ONLY" -eq 0 ]; then
  if "$VENV_PY" -m lenovorgb autostart enable >/dev/null 2>&1; then
    ok "Launch at login enabled (system tray)."
    say "  Disable later with: lenovorgb autostart disable"
  else
    warn "Could not enable launch at login. Try: lenovorgb autostart enable"
  fi
else
  say "Skipping launch at login."
fi

# ------------------------------------------------------------- input group
WAYLAND=0
if [ -n "${WAYLAND_DISPLAY:-}" ] || [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
  WAYLAND=1
fi
ADD_INPUT=$WITH_INPUT
ALREADY_INPUT=0
if id -nG "$USER_NAME" | tr ' ' '\n' | grep -qx input; then
  ALREADY_INPUT=1
fi
if [ "$ALREADY_INPUT" -eq 0 ] && [ "$ADD_INPUT" -eq 0 ] && [ "$NO_INPUT" -eq 0 ] && [ "$WAYLAND" -eq 1 ]; then
  if [ -t 0 ] && [ "$ASSUME_YES" -eq 0 ]; then
    printf 'Key-reactive modes (Type Lighting, Ripple) need read access to /dev/input.\n'
    printf 'Add %s to the input group? A logout is required. [Y/n] ' "$USER_NAME"
    read -r reply || reply="n"
    case "$reply" in ""|y|Y|yes|YES) ADD_INPUT=1 ;; esac
  else
    say "Wayland detected. For key-reactive modes run: sudo usermod -aG input $USER_NAME (then log out)."
  fi
fi
if [ "$ALREADY_INPUT" -eq 1 ]; then
  ok "Your user is already in the 'input' group."
elif [ "$ADD_INPUT" -eq 1 ]; then
  say "Adding $USER_NAME to the 'input' group for keyboard effects on Wayland ..."
  if run_root usermod -aG input "$USER_NAME"; then
    warn "Log out and back in for the group change to take effect."
  else
    warn "Could not update the input group."
  fi
fi

# --------------------------------------------------------------- ambilight
if [ "$CLI_ONLY" -eq 0 ] && [ "$WAYLAND" -eq 1 ]; then
  if ! command -v grim >/dev/null 2>&1 && ! command -v spectacle >/dev/null 2>&1 && ! command -v gnome-screenshot >/dev/null 2>&1; then
    warn "Screen Ambilight needs grim (Hyprland/sway), spectacle (KDE) or gnome-screenshot."
  fi
fi

# --------------------------------------------------------------------- done
say ""
ok "Installation complete."
say ""
say "  Open the app        lenovorgb"
say "  List modes          lenovorgb list"
say "  Run a mode          lenovorgb run aurora"
say "  Turn lights off     lenovorgb off"
say "  Troubleshoot        lenovorgb doctor"
say ""
if ! printf '%s' ":$PATH:" | grep -q ":$BIN_DIR:"; then
  warn "$BIN_DIR is not in your PATH. Add this line to ~/.bashrc or ~/.zshrc:"
  warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  say "  Or run the app directly: $ROOT/.venv/bin/lenovorgb"
fi
say "If the keyboard is not detected, unplug and re-plug it once."
say ""

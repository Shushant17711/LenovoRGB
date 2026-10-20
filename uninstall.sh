#!/usr/bin/env bash
# Lenovo RGB - Linux uninstaller
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PURGE=0
ASSUME_YES=0

for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    --keep-venv) KEEP_VENV=1 ;;
    -y|--yes) ASSUME_YES=1 ;;
    -h|--help)
      cat <<'EOF'
Remove Lenovo RGB from this machine.

  --purge      also delete your settings and logs
  --keep-venv  keep the .venv directory
  -y, --yes    do not ask
EOF
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

KEEP_VENV="${KEEP_VENV:-0}"
say() { printf '%s\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
ok() { printf '\033[32m%s\033[0m\n' "$*"; }

if [ "$ASSUME_YES" -eq 0 ] && [ -t 0 ]; then
  printf 'Remove Lenovo RGB and its command/menu entries? [y/N] '
  read -r answer || answer="n"
  case "$answer" in
    y|Y|yes|YES) ;;
    *) say "Cancelled."; exit 0 ;;
  esac
fi

VENV_PY="$ROOT/.venv/bin/python"

if [ -x "$VENV_PY" ]; then
  "$VENV_PY" -m lenovorgb autostart disable >/dev/null 2>&1 || true
  "$VENV_PY" -m lenovorgb shortcut remove >/dev/null 2>&1 || true
fi

rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/lenovorgb.desktop"
rm -f "${XDG_DATA_HOME:-$HOME/.local/share}/applications/lenovorgb.desktop"
rm -f "$HOME/.local/bin/lenovorgb"
ok "Removed command and menu entries."

RULE=/etc/udev/rules.d/99-lenovorgb.rules
if [ ! -e "$RULE" ]; then
  say "No udev rule installed."
elif [ "$(id -u)" -eq 0 ]; then
  rm -f "$RULE"
  udevadm control --reload-rules >/dev/null 2>&1 || true
  ok "Removed udev rule."
elif command -v sudo >/dev/null 2>&1; then
  if sudo -n rm -f "$RULE" 2>/dev/null; then
    sudo udevadm control --reload-rules >/dev/null 2>&1 || true
    ok "Removed udev rule."
  else
    warn "Run this to remove the udev rule:"
    warn "  sudo rm -f $RULE"
  fi
fi

if [ "$PURGE" -eq 1 ]; then
  rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/lenovorgb"
  rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/lenovorgb"
  ok "Removed settings and logs."
fi

if [ "$KEEP_VENV" -eq 0 ]; then
  rm -rf "$ROOT/.venv"
  ok "Removed .venv."
fi

say ""
ok "Lenovo RGB was uninstalled."
say "The keyboard keeps its current lighting until you change it or reboot."

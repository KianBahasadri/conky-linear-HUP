#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/linear-conky-overlay.desktop"
START_SCRIPT="$ROOT/scripts/start_conky_overlays.sh"

mkdir -p "$AUTOSTART_DIR"

printf '%s\n' \
  '[Desktop Entry]' \
  'Type=Application' \
  'Name=Linear Conky Overlay' \
  'Comment=Starts Linear task overlay' \
  "Exec=bash -lc 'sleep 5 && exec \"$START_SCRIPT\"'" \
  'Terminal=false' \
  'X-GNOME-Autostart-enabled=true' \
  > "$DESKTOP_FILE"

printf 'Installed GNOME autostart entry: %s\n' "$DESKTOP_FILE"

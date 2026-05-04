#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LOG_PATH="$ROOT/conky-linear.log"

log() {
  printf '[%s] stop_conky_overlays: %s\n' "$(date --iso-8601=seconds)" "$*" >> "$LOG_PATH"
}

log "stopping matching Conky processes"

pkill -f "$ROOT/conky/generated/linear-overlay-" 2>/dev/null || true
pkill -f "$ROOT/conky/linear-overlay.conkyrc" 2>/dev/null || true
log "stop command completed"

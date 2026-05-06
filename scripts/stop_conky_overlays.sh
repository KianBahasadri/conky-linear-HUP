#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
CACHE_DIR="$ROOT/cache"
LOG_PATH="$CACHE_DIR/conky-linear.log"

mkdir -p "$CACHE_DIR"

log() {
  printf '[%s] stop_conky_overlays: %s\n' "$(date --iso-8601=seconds)" "$*" >> "$LOG_PATH"
}

log "stopping matching Conky processes"

pkill -f "$ROOT/conky/generated/linear-overlay-" 2>/dev/null || true
pkill -f "$ROOT/conky/generated/codex-overlay-" 2>/dev/null || true
pkill -f "$ROOT/conky/linear-overlay.conkyrc" 2>/dev/null || true
pkill -f "$ROOT/conky/codex-overlay.conkyrc" 2>/dev/null || true
log "stop command completed"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
CACHE_DIR="$ROOT/cache"
LINEAR_LOG_PATH="$CACHE_DIR/conky-linear.log"
CODEX_LOG_PATH="$CACHE_DIR/conky-codex.log"
MINECRAFT_LOG_PATH="$CACHE_DIR/conky-minecraft.log"
GITHUB_LOG_PATH="$CACHE_DIR/conky-github.log"
LINEAR_FETCH_PID="$CACHE_DIR/linear-fetch-loop.pid"
CODEX_FETCH_PID="$CACHE_DIR/codex-fetch-loop.pid"
MINECRAFT_FETCH_PID="$CACHE_DIR/minecraft-fetch-loop.pid"
GITHUB_FETCH_PID="$CACHE_DIR/github-fetch-loop.pid"

mkdir -p "$CACHE_DIR"

log() {
  printf '[%s] stop_conky_overlays: %s\n' "$(date --iso-8601=seconds)" "$*" >> "$LINEAR_LOG_PATH"
}

log_codex() {
  printf '[%s] stop_conky_overlays: %s\n' "$(date --iso-8601=seconds)" "$*" >> "$CODEX_LOG_PATH"
}

log_minecraft() {
  printf '[%s] stop_conky_overlays: %s\n' "$(date --iso-8601=seconds)" "$*" >> "$MINECRAFT_LOG_PATH"
}

log_github() {
  printf '[%s] stop_conky_overlays: %s\n' "$(date --iso-8601=seconds)" "$*" >> "$GITHUB_LOG_PATH"
}

stop_fetch_loop() {
  local pid_file="$1"
  local label="$2"

  if [[ ! -f "$pid_file" ]]; then
    return
  fi

  local pid
  pid="$(<"$pid_file")"
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    if [[ "$label" == "Codex" ]]; then
      log_codex "stopped $label fetch loop pid=$pid"
    elif [[ "$label" == "Minecraft" ]]; then
      log_minecraft "stopped $label fetch loop pid=$pid"
    elif [[ "$label" == "GitHub" ]]; then
      log_github "stopped $label fetch loop pid=$pid"
    else
      log "stopped $label fetch loop pid=$pid"
    fi
  fi
  rm -f "$pid_file"
}

log "stopping matching Conky processes"

pkill -f "$ROOT/conky/generated/linear-overlay-" 2>/dev/null || true
pkill -f "$ROOT/conky/generated/codex-overlay-" 2>/dev/null || true
pkill -f "$ROOT/conky/generated/minecraft-overlay-" 2>/dev/null || true
pkill -f "$ROOT/conky/generated/github-overlay-" 2>/dev/null || true
pkill -f "$ROOT/conky/linear-overlay.conkyrc" 2>/dev/null || true
pkill -f "$ROOT/conky/codex-overlay.conkyrc" 2>/dev/null || true
pkill -f "$ROOT/conky/minecraft-overlay.conkyrc" 2>/dev/null || true
pkill -f "$ROOT/conky/github-overlay.conkyrc" 2>/dev/null || true
stop_fetch_loop "$LINEAR_FETCH_PID" "Linear"
stop_fetch_loop "$CODEX_FETCH_PID" "Codex"
stop_fetch_loop "$MINECRAFT_FETCH_PID" "Minecraft"
stop_fetch_loop "$GITHUB_FETCH_PID" "GitHub"
log "stop command completed"

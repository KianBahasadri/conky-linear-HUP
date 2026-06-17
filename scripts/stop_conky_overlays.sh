#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
CACHE_DIR="$ROOT/cache"
LINEAR_LOG_PATH="$CACHE_DIR/conky-linear.log"
RATE_LIMIT_PANEL_LOG_PATH="$CACHE_DIR/conky-rate-limit-panel.log"
MINECRAFT_LOG_PATH="$CACHE_DIR/conky-minecraft.log"
GITHUB_LOG_PATH="$CACHE_DIR/conky-github.log"
LINEAR_FETCH_PID="$CACHE_DIR/linear-fetch-loop.pid"
CODEX_FETCH_PID="$CACHE_DIR/codex-fetch-loop.pid"
CLAUDE_FETCH_PID="$CACHE_DIR/claude-fetch-loop.pid"
CURSOR_FETCH_PID="$CACHE_DIR/cursor-fetch-loop.pid"
GEMINI_FETCH_PID="$CACHE_DIR/gemini-fetch-loop.pid"
GROK_FETCH_PID="$CACHE_DIR/grok-fetch-loop.pid"
PIONEER_FETCH_PID="$CACHE_DIR/pioneer-fetch-loop.pid"
MINECRAFT_FETCH_PID="$CACHE_DIR/minecraft-fetch-loop.pid"
GITHUB_FETCH_PID="$CACHE_DIR/github-fetch-loop.pid"

mkdir -p "$CACHE_DIR"

overlay_keys=(linear rate-limit-panel minecraft github)
fetch_keys=(linear codex claude cursor gemini grok pioneer minecraft github)

declare -A overlay_config=(
  [linear]="$ROOT/conky/linear-overlay.conkyrc"
  [rate-limit-panel]="$ROOT/conky/rate-limit-panel-overlay.conkyrc"
  [minecraft]="$ROOT/conky/minecraft-overlay.conkyrc"
  [github]="$ROOT/conky/github-overlay.conkyrc"
)
declare -A overlay_log_path=(
  [linear]="$LINEAR_LOG_PATH"
  [rate-limit-panel]="$RATE_LIMIT_PANEL_LOG_PATH"
  [minecraft]="$MINECRAFT_LOG_PATH"
  [github]="$GITHUB_LOG_PATH"
)
declare -A fetch_label=(
  [linear]="Linear"
  [codex]="Codex"
  [claude]="Claude"
  [cursor]="Cursor"
  [gemini]="Gemini"
  [grok]="Grok"
  [pioneer]="Pioneer"
  [minecraft]="Minecraft"
  [github]="GitHub"
)
declare -A fetch_overlay_key=(
  [linear]="linear"
  [codex]="rate-limit-panel"
  [claude]="rate-limit-panel"
  [cursor]="rate-limit-panel"
  [gemini]="rate-limit-panel"
  [grok]="rate-limit-panel"
  [pioneer]="rate-limit-panel"
  [minecraft]="minecraft"
  [github]="github"
)
declare -A fetch_pid_file=(
  [linear]="$LINEAR_FETCH_PID"
  [codex]="$CODEX_FETCH_PID"
  [claude]="$CLAUDE_FETCH_PID"
  [cursor]="$CURSOR_FETCH_PID"
  [gemini]="$GEMINI_FETCH_PID"
  [grok]="$GROK_FETCH_PID"
  [pioneer]="$PIONEER_FETCH_PID"
  [minecraft]="$MINECRAFT_FETCH_PID"
  [github]="$GITHUB_FETCH_PID"
)

log_to() {
  local log_path="$1"
  shift
  printf '[%s] stop_conky_overlays: %s\n' "$(date --iso-8601=seconds)" "$*" >> "$log_path"
}

log_overlay() {
  local key="$1"
  shift
  log_to "${overlay_log_path[$key]}" "$*"
}

stop_fetch_loop() {
  local fetch_key="$1"
  local pid_file="${fetch_pid_file[$fetch_key]}"
  local label="${fetch_label[$fetch_key]}"
  local log_key="${fetch_overlay_key[$fetch_key]}"

  if [[ ! -f "$pid_file" ]]; then
    return
  fi

  local pid
  pid="$(<"$pid_file")"
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    log_overlay "$log_key" "stopped $label fetch loop pid=$pid"
  fi
  rm -f "$pid_file"
}

log_overlay linear "stopping matching Conky processes"

for key in "${overlay_keys[@]}"; do
  pkill -f "$ROOT/conky/generated/$key-overlay-" 2>/dev/null || true
done
pkill -f "$ROOT/conky/generated/codex-overlay-" 2>/dev/null || true
for key in "${overlay_keys[@]}"; do
  pkill -f "${overlay_config[$key]}" 2>/dev/null || true
done
pkill -f "$ROOT/conky/codex-overlay.conkyrc" 2>/dev/null || true
for fetch_key in "${fetch_keys[@]}"; do
  stop_fetch_loop "$fetch_key"
done
log_overlay linear "stop command completed"

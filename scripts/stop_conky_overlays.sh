#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
CACHE_DIR="$ROOT/cache"
LIFECYCLE_LOCK_PATH="$CACHE_DIR/conky-lifecycle.lock"

if (( $# != 0 )); then
  printf 'usage: %s\n' "$0" >&2
  exit 2
fi

# Resolved from this script's absolute directory.
# shellcheck disable=SC1091
source "$SCRIPT_DIR/conky_lifecycle.sh"

mkdir -p "$CACHE_DIR"
if [[ "${CONKY_LIFECYCLE_LOCKED:-0}" != "1" ]]; then
  if ! command -v flock >/dev/null 2>&1; then
    printf 'flock is not installed (provided by util-linux)\n' >&2
    exit 1
  fi
  exec flock --exclusive --close "$LIFECYCLE_LOCK_PATH" \
    env CONKY_LIFECYCLE_LOCKED=1 "$SCRIPT_DIR/stop_conky_overlays.sh" "$@"
fi

LINEAR_LOG_PATH="$CACHE_DIR/conky-linear.log"
RATE_LIMIT_PANEL_LOG_PATH="$CACHE_DIR/conky-rate-limit-panel.log"
MINECRAFT_LOG_PATH="$CACHE_DIR/conky-minecraft.log"
GITHUB_LOG_PATH="$CACHE_DIR/conky-github.log"
WEATHER_LOG_PATH="$CACHE_DIR/conky-weather.log"
RESOURCE_MONITOR_LOG_PATH="$CACHE_DIR/conky-resource-monitor.log"
BILLING_LOG_PATH="$CACHE_DIR/conky-billing.log"
GIT_LOG_PATH="$CACHE_DIR/conky-git.log"
SESSIONS_LOG_PATH="$CACHE_DIR/conky-sessions.log"
LINEAR_FETCH_PID="$CACHE_DIR/linear-fetch-loop.pid"
CODEX_FETCH_PID="$CACHE_DIR/codex-fetch-loop.pid"
CLAUDE_FETCH_PID="$CACHE_DIR/claude-fetch-loop.pid"
CURSOR_FETCH_PID="$CACHE_DIR/cursor-fetch-loop.pid"
GEMINI_FETCH_PID="$CACHE_DIR/gemini-fetch-loop.pid"
GROK_FETCH_PID="$CACHE_DIR/grok-fetch-loop.pid"
OPENCODE_FETCH_PID="$CACHE_DIR/opencode-fetch-loop.pid"
COMMANDCODE_FETCH_PID="$CACHE_DIR/commandcode-fetch-loop.pid"
MINECRAFT_FETCH_PID="$CACHE_DIR/minecraft-fetch-loop.pid"
GITHUB_FETCH_PID="$CACHE_DIR/github-fetch-loop.pid"
WEATHER_FETCH_PID="$CACHE_DIR/weather-fetch-loop.pid"
WORKOUTS_FETCH_PID="$CACHE_DIR/workouts-fetch-loop.pid"
BILLING_FETCH_PID="$CACHE_DIR/billing-fetch-loop.pid"
GIT_FETCH_PID="$CACHE_DIR/git-fetch-loop.pid"
SESSIONS_FETCH_PID="$CACHE_DIR/sessions-fetch-loop.pid"

overlay_keys=(linear rate-limit-panel minecraft github weather resource-monitor billing git sessions)
fetch_keys=(linear codex claude cursor gemini grok opencode commandcode minecraft github weather workouts billing git sessions)

declare -A overlay_config=(
  [linear]="$ROOT/conky/linear-overlay.conkyrc"
  [rate-limit-panel]="$ROOT/conky/rate-limit-panel-overlay.conkyrc"
  [minecraft]="$ROOT/conky/minecraft-overlay.conkyrc"
  [github]="$ROOT/conky/github-overlay.conkyrc"
  [weather]="$ROOT/conky/weather-overlay.conkyrc"
  [resource-monitor]="$ROOT/conky/resource-monitor-overlay.conkyrc"
  [billing]="$ROOT/conky/billing-overlay.conkyrc"
  [git]="$ROOT/conky/git-overlay.conkyrc"
  [sessions]="$ROOT/conky/sessions-overlay.conkyrc"
)
declare -A overlay_log_path=(
  [linear]="$LINEAR_LOG_PATH"
  [rate-limit-panel]="$RATE_LIMIT_PANEL_LOG_PATH"
  [minecraft]="$MINECRAFT_LOG_PATH"
  [github]="$GITHUB_LOG_PATH"
  [weather]="$WEATHER_LOG_PATH"
  [resource-monitor]="$RESOURCE_MONITOR_LOG_PATH"
  [billing]="$BILLING_LOG_PATH"
  [git]="$GIT_LOG_PATH"
  [sessions]="$SESSIONS_LOG_PATH"
)
declare -A fetch_label=(
  [linear]="Linear"
  [codex]="Codex"
  [claude]="Claude"
  [cursor]="Cursor"
  [gemini]="Gemini"
  [grok]="Grok"
  [opencode]="OpenCode Go"
  [commandcode]="Command Code"
  [minecraft]="Minecraft"
  [github]="GitHub"
  [weather]="Weather"
  [workouts]="Workouts"
  [billing]="Billing"
  [git]="Git"
  [sessions]="Sessions"
)
declare -A fetch_overlay_key=(
  [linear]="linear"
  [codex]="rate-limit-panel"
  [claude]="rate-limit-panel"
  [cursor]="rate-limit-panel"
  [gemini]="rate-limit-panel"
  [grok]="rate-limit-panel"
  [opencode]="rate-limit-panel"
  [commandcode]="rate-limit-panel"
  [minecraft]="minecraft"
  [github]="github"
  [weather]="weather"
  [workouts]="weather"
  [billing]="billing"
  [git]="git"
  [sessions]="sessions"
)
declare -A fetch_pid_file=(
  [linear]="$LINEAR_FETCH_PID"
  [codex]="$CODEX_FETCH_PID"
  [claude]="$CLAUDE_FETCH_PID"
  [cursor]="$CURSOR_FETCH_PID"
  [gemini]="$GEMINI_FETCH_PID"
  [grok]="$GROK_FETCH_PID"
  [opencode]="$OPENCODE_FETCH_PID"
  [commandcode]="$COMMANDCODE_FETCH_PID"
  [minecraft]="$MINECRAFT_FETCH_PID"
  [github]="$GITHUB_FETCH_PID"
  [weather]="$WEATHER_FETCH_PID"
  [workouts]="$WORKOUTS_FETCH_PID"
  [billing]="$BILLING_FETCH_PID"
  [git]="$GIT_FETCH_PID"
  [sessions]="$SESSIONS_FETCH_PID"
)
declare -A fetch_script=(
  [linear]="$ROOT/scripts/fetch_linear_tasks.py"
  [codex]="$ROOT/scripts/fetch_codex_usage.py"
  [claude]="$ROOT/scripts/fetch_claude_usage.py"
  [cursor]="$ROOT/scripts/fetch_cursor_usage.py"
  [gemini]="$ROOT/scripts/fetch_gemini_usage.py"
  [grok]="$ROOT/scripts/fetch_grok_usage.py"
  [opencode]="$ROOT/scripts/fetch_opencode_usage.py"
  [commandcode]="$ROOT/scripts/fetch_commandcode_usage.py"
  [minecraft]="$ROOT/scripts/fetch_minecraft_status.py"
  [github]="$ROOT/scripts/fetch_github_contributions.py"
  [weather]="$ROOT/scripts/fetch_weather.py"
  [workouts]="$ROOT/scripts/fetch_workouts.py"
  [billing]="$ROOT/scripts/fetch_billing_usage.py"
  [git]="$ROOT/scripts/fetch_git_status.py"
  [sessions]="$ROOT/scripts/fetch_sessions.py"
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
  local script_path="${fetch_script[$fetch_key]}"
  local label="${fetch_label[$fetch_key]}"
  local log_key="${fetch_overlay_key[$fetch_key]}"
  local pid_status
  local pid_from_file
  local pid
  local -a owned_pids=()

  classify_fetch_loop_pid "$pid_file" "$script_path" "$ROOT"
  pid_status="$FETCH_LOOP_PID_STATUS"
  pid_from_file="$FETCH_LOOP_PID"
  case "$pid_status" in
    missing|owned) ;;
    invalid)
      log_overlay "$log_key" "removed invalid $label fetch-loop pid file: $pid_file"
      ;;
    dead)
      log_overlay "$log_key" "removed stale $label fetch-loop pid file: pid=$pid_from_file"
      ;;
    foreign)
      log_overlay "$log_key" "removed foreign $label fetch-loop pid file without signaling pid=$pid_from_file"
      ;;
  esac

  mapfile -t owned_pids < <(matching_fetch_loop_pids "$script_path" "$ROOT")
  for pid in "${owned_pids[@]}"; do
    terminate_fetch_loop_pid "$pid" "$script_path" "$ROOT"
    log_overlay "$log_key" "stopped $label fetch loop pid=$pid"
    if [[ "$FETCH_LOOP_FORCED_KILL" -eq 1 ]]; then
      log_overlay "$log_key" "force-killed unresponsive $label fetch loop pid=$pid"
    fi
  done
  rm -f "$pid_file"
}

log_overlay linear "stopping matching Conky processes"

for key in "${overlay_keys[@]}"; do
  terminate_matching_conky_processes "$ROOT/conky/generated/$key-overlay-" prefix
done
terminate_matching_conky_processes "$ROOT/conky/generated/codex-overlay-" prefix
for key in "${overlay_keys[@]}"; do
  terminate_matching_conky_processes "${overlay_config[$key]}" exact
done
terminate_matching_conky_processes "$ROOT/conky/codex-overlay.conkyrc" exact
for fetch_key in "${fetch_keys[@]}"; do
  stop_fetch_loop "$fetch_key"
done
log_overlay linear "stop command completed"

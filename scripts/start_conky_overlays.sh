#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
ENV_PATH="$ROOT/.env"
CACHE_DIR="$ROOT/cache"
LIFECYCLE_LOCK_PATH="$CACHE_DIR/conky-lifecycle.lock"

if (( $# > 1 )) || { (( $# == 1 )) && [[ "$1" != "--generate-only" ]]; }; then
  printf 'usage: %s [--generate-only]\n' "$0" >&2
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
    env CONKY_LIFECYCLE_LOCKED=1 "$SCRIPT_DIR/start_conky_overlays.sh" "$@"
fi

if [[ -f "$ENV_PATH" ]]; then
  while IFS= read -r env_line || [[ -n "$env_line" ]]; do
    [[ "$env_line" =~ ^[[:space:]]*$ || "$env_line" =~ ^[[:space:]]*# ]] && continue
    [[ "$env_line" == *"="* ]] || continue

    env_key="${env_line%%=*}"
    env_value="${env_line#*=}"
    env_key="${env_key//[[:space:]]/}"
    [[ "$env_key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    [[ -v "$env_key" ]] && continue

    env_value="${env_value#"${env_value%%[![:space:]]*}"}"
    env_value="${env_value%"${env_value##*[![:space:]]}"}"

    if [[ "$env_value" == \"*\" && "$env_value" == *\" ]]; then
      env_value="${env_value:1:${#env_value}-2}"
    elif [[ "$env_value" == \'*\' && "$env_value" == *\' ]]; then
      env_value="${env_value:1:${#env_value}-2}"
    fi

    export "$env_key=$env_value"
  done < "$ENV_PATH"
fi

if ! command -v uv >/dev/null 2>&1; then
  printf 'uv is not installed\n' >&2
  exit 1
fi

run_python() {
  uv --project "$ROOT" run --no-dev python "$@"
}

BASE_CONFIG="$ROOT/conky/linear-overlay.conkyrc"
RATE_LIMIT_PANEL_CONFIG="$ROOT/conky/rate-limit-panel-overlay.conkyrc"
MINECRAFT_CONFIG="$ROOT/conky/minecraft-overlay.conkyrc"
GITHUB_CONFIG="$ROOT/conky/github-overlay.conkyrc"
WEATHER_CONFIG="$ROOT/conky/weather-overlay.conkyrc"
RESOURCE_MONITOR_CONFIG="$ROOT/conky/resource-monitor-overlay.conkyrc"
BILLING_CONFIG="$ROOT/conky/billing-overlay.conkyrc"
GIT_CONFIG="$ROOT/conky/git-overlay.conkyrc"
SESSIONS_CONFIG="$ROOT/conky/sessions-overlay.conkyrc"
GENERATED_DIR="$ROOT/conky/generated"
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
OVERLAY_WIDTH=1540
LINEAR_GAP_Y=4
LINEAR_PRIMARY_GAP_Y=34
LINEAR_PRIMARY_MONITOR_INDEX="${LINEAR_PRIMARY_MONITOR_INDEX:-0}"
LINEAR_OVERLAY_ENABLED="${LINEAR_OVERLAY_ENABLED:-1}"
PRIMARY_WAIT_SECONDS="${PRIMARY_WAIT_SECONDS:-20}"
RATE_LIMIT_PANEL_GAP_Y="${RATE_LIMIT_PANEL_GAP_Y:-6}"
RATE_LIMIT_PANEL_ENABLED="${RATE_LIMIT_PANEL_ENABLED:-1}"
MINECRAFT_GAP_X="${MINECRAFT_GAP_X:-4}"
MINECRAFT_GAP_Y="${MINECRAFT_GAP_Y:-6}"
MINECRAFT_REFRESH_SECONDS="${MINECRAFT_REFRESH_SECONDS:-60}"
MINECRAFT_OVERLAY_ENABLED="${MINECRAFT_OVERLAY_ENABLED:-1}"
# Both empty = auto placement, which lands the contribution skyline on the rate
# limit panel's top edge as its roof. Set either to pin that axis instead.
GITHUB_GAP_X="${GITHUB_GAP_X-}"
GITHUB_GAP_Y="${GITHUB_GAP_Y-}"
GITHUB_REFRESH_SECONDS="${GITHUB_REFRESH_SECONDS:-1800}"
GITHUB_OVERLAY_ENABLED="${GITHUB_OVERLAY_ENABLED:-1}"
# Window height for the skyline: the plinth, the day-axis depth and the tallest
# tower all share it, and the renderer scales the extrusion to whatever is left
# over.
GITHUB_SKYLINE_HEIGHT="${GITHUB_SKYLINE_HEIGHT:-200}"
# Floor for that height once the Linear clearance below has been taken out.
GITHUB_SKYLINE_MIN_HEIGHT="${GITHUB_SKYLINE_MIN_HEIGHT:-180}"
# Gap kept between the bottom of the Linear cards and the skyline's top.
GITHUB_LINEAR_CLEARANCE="${GITHUB_LINEAR_CLEARANCE:-14}"
# Clearance between the roof line and the panel's top edge. The provider title
# chips straddle that edge, riding 9px above it.
GITHUB_ROOF_CLEARANCE="${GITHUB_ROOF_CLEARANCE:-11}"
# The tall bay owns the lower-left column rather than sharing the skyline seam.
SESSIONS_GAP_X="${SESSIONS_GAP_X:-4}"
SESSIONS_GAP_Y="${SESSIONS_GAP_Y:-6}"
SESSIONS_REFRESH_SECONDS="${SESSIONS_REFRESH_SECONDS:-20}"
SESSIONS_OVERLAY_ENABLED="${SESSIONS_OVERLAY_ENABLED:-1}"
SESSIONS_PANEL_WIDTH=440
WEATHER_GAP_X="${WEATHER_GAP_X:-6}"
WEATHER_GAP_Y="${WEATHER_GAP_Y:-6}"
WEATHER_REFRESH_SECONDS="${WEATHER_REFRESH_SECONDS:-600}"
WEATHER_OVERLAY_ENABLED="${WEATHER_OVERLAY_ENABLED:-1}"
WORKOUTS_REFRESH_SECONDS="${WORKOUTS_REFRESH_SECONDS:-20}"
RESOURCE_MONITOR_GAP_X="${RESOURCE_MONITOR_GAP_X:-0}"
# Empty means follow Linear's per-monitor gap_y so gauge tops stay flush with cards.
RESOURCE_MONITOR_GAP_Y="${RESOURCE_MONITOR_GAP_Y:-}"
RESOURCE_MONITOR_OVERLAY_ENABLED="${RESOURCE_MONITOR_OVERLAY_ENABLED:-1}"
# Empty = center on the weather panel; otherwise an explicit right-edge gap.
BILLING_GAP_X="${BILLING_GAP_X-}"
# Empty = sit just above the weather panel; otherwise an explicit top offset.
BILLING_GAP_Y="${BILLING_GAP_Y-}"
BILLING_REFRESH_SECONDS="${BILLING_REFRESH_SECONDS:-900}"
BILLING_OVERLAY_ENABLED="${BILLING_OVERLAY_ENABLED:-1}"
GIT_GAP_X="${GIT_GAP_X:-1}"
# Empty means follow Linear's per-monitor gap_y (primary clears the GNOME top bar).
GIT_GAP_Y="${GIT_GAP_Y-1}"
GIT_REFRESH_SECONDS="${GIT_REFRESH_SECONDS:-30}"
GIT_OVERLAY_ENABLED="${GIT_OVERLAY_ENABLED:-1}"
# Adaptive rate-limit polling: repoll quickly for a while after any usage change,
# then back off when idle. Applied to all rate-limit-panel fetchers
# (codex/claude/cursor/gemini/grok/opencode/commandcode).
RATE_LIMIT_CHANGED_INTERVAL="${RATE_LIMIT_CHANGED_INTERVAL:-60}"
RATE_LIMIT_UNCHANGED_INTERVAL="${RATE_LIMIT_UNCHANGED_INTERVAL:-300}"
# Keep using the short interval for this many seconds after any detected change.
RATE_LIMIT_RECENT_CHANGE_WINDOW="${RATE_LIMIT_RECENT_CHANGE_WINDOW:-600}"
CONKY_LOG_MAX_BYTES="${CONKY_LOG_MAX_BYTES:-5242880}"
CONKY_LOG_ROTATIONS="${CONKY_LOG_ROTATIONS:-2}"
GENERATE_ONLY=0
MONITOR_HAS_PRIMARY=0
GENERATED_CONFIG_COUNT=0
GENERATION_STAGE_DIR=""

overlay_keys=(linear rate-limit-panel minecraft github weather resource-monitor billing git sessions)
fetch_keys=(linear codex claude cursor gemini grok opencode commandcode minecraft github weather workouts billing git sessions)

declare -A overlay_disabled_name=(
  [linear]="linear"
  [rate-limit-panel]="rate limit panel"
  [minecraft]="minecraft"
  [github]="github"
  [weather]="weather"
  [resource-monitor]="resource monitor"
  [billing]="billing"
  [git]="git status"
  [sessions]="sessions"
)
declare -A overlay_config=(
  [linear]="$BASE_CONFIG"
  [rate-limit-panel]="$RATE_LIMIT_PANEL_CONFIG"
  [minecraft]="$MINECRAFT_CONFIG"
  [github]="$GITHUB_CONFIG"
  [weather]="$WEATHER_CONFIG"
  [resource-monitor]="$RESOURCE_MONITOR_CONFIG"
  [billing]="$BILLING_CONFIG"
  [git]="$GIT_CONFIG"
  [sessions]="$SESSIONS_CONFIG"
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
declare -A overlay_enabled_var=(
  [linear]="LINEAR_OVERLAY_ENABLED"
  [rate-limit-panel]="RATE_LIMIT_PANEL_ENABLED"
  [minecraft]="MINECRAFT_OVERLAY_ENABLED"
  [github]="GITHUB_OVERLAY_ENABLED"
  [weather]="WEATHER_OVERLAY_ENABLED"
  [resource-monitor]="RESOURCE_MONITOR_OVERLAY_ENABLED"
  [billing]="BILLING_OVERLAY_ENABLED"
  [git]="GIT_OVERLAY_ENABLED"
  [sessions]="SESSIONS_OVERLAY_ENABLED"
)
declare -A generated_config_expected=()
declare -A generated_config_staged=()
declare -a generated_config_targets=()
declare -a queued_launch_keys=()
declare -a queued_launch_configs=()
declare -a queued_launch_notes=()

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
# Interval for non-adaptive fetchers. Rate-limit keys (codex/claude/cursor/
# gemini/grok/opencode/commandcode) use adaptive polling via fetch_render_path; their
# fetch_interval values are unused fallbacks only.
declare -A fetch_interval=(
  [linear]="60"
  [codex]="$RATE_LIMIT_UNCHANGED_INTERVAL"
  [claude]="$RATE_LIMIT_UNCHANGED_INTERVAL"
  [cursor]="$RATE_LIMIT_UNCHANGED_INTERVAL"
  [gemini]="$RATE_LIMIT_UNCHANGED_INTERVAL"
  [grok]="$RATE_LIMIT_UNCHANGED_INTERVAL"
  [opencode]="$RATE_LIMIT_UNCHANGED_INTERVAL"
  [commandcode]="$RATE_LIMIT_UNCHANGED_INTERVAL"
  [minecraft]="$MINECRAFT_REFRESH_SECONDS"
  [github]="$GITHUB_REFRESH_SECONDS"
  [weather]="$WEATHER_REFRESH_SECONDS"
  [workouts]="$WORKOUTS_REFRESH_SECONDS"
  [billing]="$BILLING_REFRESH_SECONDS"
  [git]="$GIT_REFRESH_SECONDS"
  [sessions]="$SESSIONS_REFRESH_SECONDS"
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
# Render TSV paths for rate-limit-panel fetchers that support adaptive polling.
# Keys with an empty render path use the static fetch_interval instead.
declare -A fetch_render_path=(
  [linear]=""
  [codex]="$CACHE_DIR/codex-usage-render.tsv"
  [claude]="$CACHE_DIR/claude-usage-render.tsv"
  [cursor]="$CACHE_DIR/cursor-usage-render.tsv"
  [gemini]="$CACHE_DIR/gemini-usage-render.tsv"
  [grok]="$CACHE_DIR/grok-usage-render.tsv"
  [opencode]="$CACHE_DIR/opencode-usage-render.tsv"
  [commandcode]="$CACHE_DIR/commandcode-usage-render.tsv"
  [minecraft]=""
  [github]=""
  [weather]=""
  [billing]=""
  [git]=""
  [sessions]=""
)

env_flag_disabled() {
  case "${1,,}" in
    0|false|no|off|disabled) return 0 ;;
    *) return 1 ;;
  esac
}

overlay_enabled() {
  local key="$1"
  local enabled_var="${overlay_enabled_var[$key]}"
  ! env_flag_disabled "${!enabled_var}"
}

log_to() {
  local log_path="$1"
  shift
  printf '[%s] start_conky_overlays: %s\n' "$(date --iso-8601=seconds)" "$*" >> "$log_path"
}

log_overlay() {
  local key="$1"
  shift
  log_to "${overlay_log_path[$key]}" "$*"
}

rotate_oversized_logs() {
  local log_path

  for log_path in "$CACHE_DIR"/conky-*.log; do
    if rotate_log_file "$log_path" "$CONKY_LOG_MAX_BYTES" "$CONKY_LOG_ROTATIONS"; then
      log_to "$log_path" "rotated oversized log to $log_path.1 (limit=${CONKY_LOG_MAX_BYTES}B retained=$CONKY_LOG_ROTATIONS)"
    fi
  done
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
    log_overlay "$log_key" "stopped existing $label fetch loop pid=$pid"
    if [[ "$FETCH_LOOP_FORCED_KILL" -eq 1 ]]; then
      log_overlay "$log_key" "force-killed unresponsive $label fetch loop pid=$pid"
    fi
  done
  rm -f "$pid_file"
}

start_fetch_loop() {
  local fetch_key="$1"
  local label="${fetch_label[$fetch_key]}"
  local interval_seconds="${fetch_interval[$fetch_key]}"
  local script_path="${fetch_script[$fetch_key]}"
  local pid_file="${fetch_pid_file[$fetch_key]}"
  local log_key="${fetch_overlay_key[$fetch_key]}"
  local log_path="${overlay_log_path[$log_key]}"
  local render_path="${fetch_render_path[$fetch_key]:-}"

  stop_fetch_loop "$fetch_key"

  # The loop body runs in the child shell with paths passed as positional args,
  # so it must stay single-quoted (no expansion in this parent shell).
  # Adaptive rate-limit fetchers (render_path set) fingerprint the meaningful
  # usage data in their render TSV. After any change they keep the short interval
  # for RATE_LIMIT_RECENT_CHANGE_WINDOW seconds, then back off. Other fetchers
  # use the static interval.
  # shellcheck disable=SC2016
  setsid bash -c '
    script_path="$1"
    log_path="$2"
    interval_seconds="$3"
    render_path="$4"
    changed_interval="$5"
    unchanged_interval="$6"
    recent_change_window="$7"
    project_root="$8"
    fingerprint_path=""
    last_change_path=""
    [[ -n "$render_path" ]] && fingerprint_path="${render_path}.fingerprint"
    [[ -n "$render_path" ]] && last_change_path="${render_path}.last_change"

    compute_fingerprint() {
      [[ -n "$render_path" && -f "$render_path" ]] || return 0
      # Drop the volatile "meta" line (updatedAt changes every poll) and blank
      # time-derived bar columns (resetsAt, resetAtEpoch, resetAfterSeconds) so
      # only meaningful usage / structure contributes to the fingerprint.
      awk -F"\t" -v OFS="\t" "
        \$1 != \"meta\" {
          if (\$1 == \"bar\") { \$8 = \"\"; \$9 = \"\"; \$10 = \"\" }
          print
        }
      " "$render_path" | sha256sum | cut -d" " -f1
    }

    while true; do
      prev_fp=""
      last_change_epoch=""
      [[ -n "$fingerprint_path" && -f "$fingerprint_path" ]] && prev_fp="$(<"$fingerprint_path")"
      [[ -n "$last_change_path" && -f "$last_change_path" ]] && last_change_epoch="$(<"$last_change_path")"
      uv --project "$project_root" run --no-dev python "$script_path" >/dev/null 2>>"$log_path" || true
      if [[ -n "$render_path" ]]; then
        new_fp="$(compute_fingerprint)"
        now_epoch="$(date +%s)"
        if [[ -z "$prev_fp" || "$new_fp" != "$prev_fp" ]]; then
          printf "%s\n" "$new_fp" > "$fingerprint_path"
          printf "%s\n" "$now_epoch" > "$last_change_path"
          sleep "$changed_interval"
        elif [[ "$last_change_epoch" =~ ^[0-9]+$ ]] \
            && (( now_epoch - last_change_epoch < recent_change_window )); then
          sleep "$changed_interval"
        else
          sleep "$unchanged_interval"
        fi
      else
        sleep "$interval_seconds"
      fi
    done
  ' bash "$script_path" "$log_path" "$interval_seconds" "$render_path" \
    "$RATE_LIMIT_CHANGED_INTERVAL" "$RATE_LIMIT_UNCHANGED_INTERVAL" \
    "$RATE_LIMIT_RECENT_CHANGE_WINDOW" "$ROOT" </dev/null >/dev/null 2>&1 &
  printf '%s\n' "$!" > "$pid_file"
  if [[ -n "$render_path" ]]; then
    log_overlay "$log_key" "started $label fetch loop adaptive (changed=${RATE_LIMIT_CHANGED_INTERVAL}s unchanged=${RATE_LIMIT_UNCHANGED_INTERVAL}s recent_window=${RATE_LIMIT_RECENT_CHANGE_WINDOW}s) pid=$!"
  else
    log_overlay "$log_key" "started $label fetch loop interval=${interval_seconds}s pid=$!"
  fi
}

if [[ "${1:-}" == "--generate-only" ]]; then
  GENERATE_ONLY=1
fi

mkdir -p "$GENERATED_DIR"
mkdir -p "$CACHE_DIR"

cleanup_generation_stage() {
  local stage_dir="${GENERATION_STAGE_DIR:-}"
  local -a staged_files=()

  [[ -n "$stage_dir" && "${stage_dir%/*}" == "$GENERATED_DIR" \
    && "${stage_dir##*/}" == .generation.* && -d "$stage_dir" ]] || return 0
  shopt -s nullglob
  staged_files=("$stage_dir"/* "$stage_dir"/.[!.]* "$stage_dir"/..?*)
  shopt -u nullglob
  if (( ${#staged_files[@]} > 0 )); then
    rm -f -- "${staged_files[@]}"
  fi
  rmdir -- "$stage_dir"
  GENERATION_STAGE_DIR=""
}

GENERATION_STAGE_DIR="$(mktemp -d "$GENERATED_DIR/.generation.XXXXXX")"
trap cleanup_generation_stage EXIT

validate_positive_integer() {
  local variable_name="$1"
  local fallback="$2"
  local log_key="$3"
  local value="${!variable_name}"

  if [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
    return
  fi
  log_overlay "$log_key" "invalid $variable_name=$value; using $fallback"
  printf -v "$variable_name" '%s' "$fallback"
}

validate_nonnegative_integer() {
  local variable_name="$1"
  local fallback="$2"
  local log_key="$3"
  local value="${!variable_name}"

  if [[ "$value" =~ ^(0|[1-9][0-9]*)$ ]]; then
    return
  fi
  log_overlay "$log_key" "invalid $variable_name=$value; using $fallback"
  printf -v "$variable_name" '%s' "$fallback"
}

validate_integer() {
  local variable_name="$1"
  local fallback="$2"
  local log_key="$3"
  local value="${!variable_name}"

  if [[ "$value" =~ ^-?(0|[1-9][0-9]*)$ ]]; then
    return
  fi
  log_overlay "$log_key" "invalid $variable_name=$value; using $fallback"
  printf -v "$variable_name" '%s' "$fallback"
}

validate_optional_integer() {
  local variable_name="$1"
  local fallback="$2"
  local log_key="$3"
  local fallback_note="$4"
  local value="${!variable_name}"

  if [[ -z "$value" || "$value" =~ ^-?(0|[1-9][0-9]*)$ ]]; then
    return
  fi
  log_overlay "$log_key" "invalid $variable_name=$value; using $fallback_note"
  printf -v "$variable_name" '%s' "$fallback"
}

if [[ ! "$LINEAR_PRIMARY_MONITOR_INDEX" =~ ^(0|[1-9][0-9]*)$ ]]; then
  log_overlay linear "invalid LINEAR_PRIMARY_MONITOR_INDEX=$LINEAR_PRIMARY_MONITOR_INDEX; using 0"
  LINEAR_PRIMARY_MONITOR_INDEX=0
fi

if [[ ! "$PRIMARY_WAIT_SECONDS" =~ ^(0|[1-9][0-9]*)$ ]]; then
  log_overlay linear "invalid PRIMARY_WAIT_SECONDS=$PRIMARY_WAIT_SECONDS; using 20"
  PRIMARY_WAIT_SECONDS=20
fi

validate_positive_integer RATE_LIMIT_CHANGED_INTERVAL 60 rate-limit-panel
validate_positive_integer RATE_LIMIT_UNCHANGED_INTERVAL 300 rate-limit-panel
validate_positive_integer RATE_LIMIT_RECENT_CHANGE_WINDOW 600 rate-limit-panel
validate_positive_integer MINECRAFT_REFRESH_SECONDS 60 minecraft
validate_positive_integer GITHUB_REFRESH_SECONDS 1800 github
validate_positive_integer WEATHER_REFRESH_SECONDS 600 weather
validate_positive_integer WORKOUTS_REFRESH_SECONDS 20 weather
validate_positive_integer BILLING_REFRESH_SECONDS 900 billing
validate_positive_integer GIT_REFRESH_SECONDS 30 git
validate_positive_integer SESSIONS_REFRESH_SECONDS 20 sessions
validate_positive_integer CONKY_LOG_MAX_BYTES 5242880 linear
validate_positive_integer CONKY_LOG_ROTATIONS 2 linear
validate_integer RATE_LIMIT_PANEL_GAP_Y 6 rate-limit-panel
validate_positive_integer GITHUB_SKYLINE_HEIGHT 200 github
validate_positive_integer GITHUB_SKYLINE_MIN_HEIGHT 180 github
validate_nonnegative_integer GITHUB_LINEAR_CLEARANCE 14 github
validate_nonnegative_integer GITHUB_ROOF_CLEARANCE 11 github
validate_integer MINECRAFT_GAP_X 4 minecraft
validate_integer MINECRAFT_GAP_Y 6 minecraft
validate_optional_integer GITHUB_GAP_X "" github "automatic placement"
validate_optional_integer GITHUB_GAP_Y "" github "automatic placement"
validate_integer SESSIONS_GAP_X 4 sessions
validate_integer SESSIONS_GAP_Y 6 sessions
validate_integer WEATHER_GAP_X 6 weather
validate_integer WEATHER_GAP_Y 6 weather
validate_integer RESOURCE_MONITOR_GAP_X 0 resource-monitor
validate_optional_integer RESOURCE_MONITOR_GAP_Y "" resource-monitor "the Linear gap"
validate_integer GIT_GAP_X 1 git
validate_optional_integer GIT_GAP_Y 1 git "1"
if (( CONKY_LOG_ROTATIONS > 10 )); then
  log_overlay linear "invalid CONKY_LOG_ROTATIONS=$CONKY_LOG_ROTATIONS; using 2"
  CONKY_LOG_ROTATIONS=2
fi

fetch_interval[minecraft]="$MINECRAFT_REFRESH_SECONDS"
fetch_interval[codex]="$RATE_LIMIT_UNCHANGED_INTERVAL"
fetch_interval[claude]="$RATE_LIMIT_UNCHANGED_INTERVAL"
fetch_interval[cursor]="$RATE_LIMIT_UNCHANGED_INTERVAL"
fetch_interval[gemini]="$RATE_LIMIT_UNCHANGED_INTERVAL"
fetch_interval[grok]="$RATE_LIMIT_UNCHANGED_INTERVAL"
fetch_interval[opencode]="$RATE_LIMIT_UNCHANGED_INTERVAL"
fetch_interval[commandcode]="$RATE_LIMIT_UNCHANGED_INTERVAL"
fetch_interval[github]="$GITHUB_REFRESH_SECONDS"
fetch_interval[weather]="$WEATHER_REFRESH_SECONDS"
fetch_interval[workouts]="$WORKOUTS_REFRESH_SECONDS"
fetch_interval[billing]="$BILLING_REFRESH_SECONDS"
fetch_interval[git]="$GIT_REFRESH_SECONDS"
fetch_interval[sessions]="$SESSIONS_REFRESH_SECONDS"

if [[ -n "$BILLING_GAP_X" && ! "$BILLING_GAP_X" =~ ^-?(0|[1-9][0-9]*)$ ]]; then
  log_overlay billing "invalid BILLING_GAP_X=$BILLING_GAP_X; following resource monitor"
  BILLING_GAP_X=""
fi

if [[ -n "$BILLING_GAP_Y" && ! "$BILLING_GAP_Y" =~ ^-?(0|[1-9][0-9]*)$ ]]; then
  log_overlay billing "invalid BILLING_GAP_Y=$BILLING_GAP_Y; using automatic placement"
  BILLING_GAP_Y=""
fi

log_overlay linear "starting; root=$ROOT generate_only=$GENERATE_ONLY"
for key in "${overlay_keys[@]}"; do
  enabled_var="${overlay_enabled_var[$key]}"
  if env_flag_disabled "${!enabled_var}"; then
    log_overlay "$key" "${overlay_disabled_name[$key]} overlay disabled by $enabled_var=${!enabled_var}"
  fi
done

linear_overlay_height() {
  run_python "$ROOT/scripts/fetch_linear_tasks.py" --print-overlay-height
}

rate_limit_panel_overlay_height() {
  run_python "$ROOT/scripts/fetch_common.py" --print-rate-limit-panel-height
}

rate_limit_panel_frame_height() {
  run_python "$ROOT/scripts/fetch_common.py" --print-rate-limit-panel-frame-height
}

rate_limit_panel_frame_width() {
  run_python "$ROOT/scripts/fetch_common.py" --print-rate-limit-panel-frame-width "$1"
}

sessions_overlay_height() {
  run_python "$ROOT/scripts/fetch_sessions.py" --print-overlay-height
}

generate_config() {
  local source_config="$1"
  local output_config="$2"
  local monitor_index="$3"
  local monitor_gap_x="$4"
  local monitor_gap_y="$5"
  local minimum_height="${6:-}"
  local minimum_width="${7:-}"
  local lua_entrypoint="$ROOT/conky/overlay-entrypoint.lua"
  local staged_config
  local temporary_config

  if [[ "$source_config" == "$BILLING_CONFIG" ]]; then
    lua_entrypoint="$ROOT/conky/billing-entrypoint.lua"
  fi

  staged_config="$GENERATION_STAGE_DIR/${output_config##*/}"
  temporary_config="$(mktemp "${staged_config}.tmp.XXXXXX")"
  if ! {
    while IFS= read -r config_line; do
      case "$config_line" in
        "  alignment = "*)
          printf "%s\n" "$config_line"
          printf "  xinerama_head = %s,\n" "$monitor_index"
          ;;
        "  gap_x = "*)
          printf "  gap_x = %s,\n" "$monitor_gap_x"
          ;;
        "  gap_y = "*)
          printf "  gap_y = %s,\n" "$monitor_gap_y"
          ;;
        "  minimum_height = "*)
          if [[ -n "$minimum_height" ]]; then
            printf "  minimum_height = %s,\n" "$minimum_height"
          else
            printf "%s\n" "$config_line"
          fi
          ;;
        "  minimum_width = "*|"  maximum_width = "*)
          if [[ -n "$minimum_width" ]]; then
            printf "%s = %s,\n" "${config_line%% =*}" "$minimum_width"
          else
            printf "%s\n" "$config_line"
          fi
          ;;
        "  lua_load = "*)
          printf "  lua_load = '%s',\n" "$lua_entrypoint"
          ;;
        *"fetch_linear_tasks.py"*) ;;
        *"fetch_codex_usage.py"*) ;;
        *"fetch_claude_usage.py"*) ;;
        *"fetch_cursor_usage.py"*) ;;
        *"fetch_gemini_usage.py"*) ;;
        *"fetch_grok_usage.py"*) ;;
        *"fetch_opencode_usage.py"*) ;;
        *"fetch_commandcode_usage.py"*) ;;
        *"fetch_weather.py"*) ;;
        *"fetch_billing_usage.py"*) ;;
        *"fetch_git_status.py"*) ;;
        *)
          printf "%s\n" "$config_line"
          ;;
      esac
    done < "$source_config" > "$temporary_config"
  }; then
    rm -f -- "$temporary_config"
    return 1
  fi
  mv -f -- "$temporary_config" "$staged_config"
  generated_config_expected["$output_config"]=1
  generated_config_staged["$output_config"]="$staged_config"
  generated_config_targets+=("$output_config")
}

install_generated_configs() {
  local output_config

  for output_config in "${generated_config_targets[@]}"; do
    mv -f -- "${generated_config_staged[$output_config]}" "$output_config"
  done
}

prune_stale_generated_configs() {
  local key
  local config_path
  local -a existing_configs=()

  shopt -s nullglob
  for key in "${overlay_keys[@]}"; do
    existing_configs+=("$GENERATED_DIR/$key-overlay-"*.conkyrc)
  done
  existing_configs+=("$GENERATED_DIR/codex-overlay-"*.conkyrc)
  shopt -u nullglob

  for config_path in "${existing_configs[@]}"; do
    if [[ -z "${generated_config_expected[$config_path]+present}" ]]; then
      rm -f -- "$config_path"
    fi
  done
}

read_monitor_lines() {
  local -n output_lines="$1"
  local deadline
  local now
  local line
  local has_primary=0

  output_lines=()
  MONITOR_HAS_PRIMARY=0
  deadline=$((SECONDS + PRIMARY_WAIT_SECONDS))

  while true; do
    output_lines=()
    has_primary=0

    while IFS= read -r line; do
      if [[ ! "$line" =~ ^[[:space:]]*[0-9]+: ]]; then
        continue
      fi

      output_lines+=("$line")
      if [[ "$line" =~ ^[[:space:]]*[0-9]+:[[:space:]]*[^[:space:]]*\* ]]; then
        has_primary=1
      fi
    done < <(xrandr --listmonitors 2>> "$LINEAR_LOG_PATH" || true)

    if [[ "${#output_lines[@]}" -eq 0 || "$has_primary" -eq 1 ]]; then
      MONITOR_HAS_PRIMARY="$has_primary"
      break
    fi

    now="$SECONDS"
    if (( now >= deadline )); then
      log_overlay linear "xrandr reported monitors but no primary marker; using fallback primary index=$LINEAR_PRIMARY_MONITOR_INDEX"
      break
    fi

    sleep 1
  done
}

read_cached_monitor_lines() {
  local -n cached_lines_ref="$1"
  local line
  local cache_path="$CACHE_DIR/monitor-layout.json"

  cached_lines_ref=()
  [[ -f "$cache_path" ]] || return
  while IFS= read -r line; do
    [[ -n "$line" ]] && cached_lines_ref+=("$line")
  done < <(
    run_python - "$cache_path" <<'PY' 2>> "$LINEAR_LOG_PATH" || true
import json
import sys
from pathlib import Path

try:
    monitors = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(0)
if not isinstance(monitors, list):
    raise SystemExit(0)
for position, monitor in enumerate(monitors):
    if not isinstance(monitor, dict):
        continue
    values = [monitor.get(key) for key in ("width", "height", "x", "y")]
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        continue
    width, height, x, y = values
    if width <= 0 or height <= 0:
        continue
    print(f"{position}: +cached-{position} {width}/1x{height}/1{x:+d}{y:+d} cached-{position}")
PY
  )
}

overlay_gap_x() {
  local key="$1"
  local monitor_gap_x="$2"

  case "$key" in
    linear|rate-limit-panel) printf "%s\n" "$monitor_gap_x" ;;
    minecraft) printf "%s\n" "$MINECRAFT_GAP_X" ;;
    github)
      if [[ -n "$GITHUB_GAP_X" ]]; then
        printf "%s\n" "$GITHUB_GAP_X"
      else
        # Flush with the panel it roofs.
        printf "%s\n" "$RATE_LIMIT_FRAME_LEFT"
      fi
      ;;
    sessions)
      printf "%s\n" "$SESSIONS_GAP_X"
      ;;
    weather) printf "%s\n" "$WEATHER_GAP_X" ;;
    resource-monitor) printf "%s\n" "$RESOURCE_MONITOR_GAP_X" ;;
    billing)
      if [[ -n "$BILLING_GAP_X" ]]; then
        printf "%s\n" "$BILLING_GAP_X"
      elif overlay_enabled weather; then
        # Billing window is the same 456px as weather, so they share gap_x.
        printf "%s\n" "$WEATHER_GAP_X"
      else
        printf "%s\n" "$RESOURCE_MONITOR_GAP_X"
      fi
      ;;
    git) printf "%s\n" "$GIT_GAP_X" ;;
  esac
}

# The rate limit panel's drawn frame, in screen space. It is narrower than its
# 1548px window and sits a fixed inset above the window's bottom edge, so the
# skyline that roofs it and the sessions bay beside it are both placed off these
# numbers rather than off the window.
RATE_LIMIT_FRAME_LEFT=0
RATE_LIMIT_FRAME_TOP=0
GITHUB_ROOF_BASELINE=0
GITHUB_RESOLVED_HEIGHT=200
MONITOR_HEIGHT=1080

rate_limit_frame_for_monitor() {
  local monitor_h="$1"
  local monitor_gap_x="$2"
  local linear_gap_y="$3"
  local window_width=$((OVERLAY_WIDTH + 8))
  local linear_bottom
  local headroom

  if [[ ! "$monitor_h" =~ ^[0-9]+$ ]] || (( monitor_h < 200 )); then
    monitor_h=1080
  fi
  MONITOR_HEIGHT="$monitor_h"

  # The renderer centers the frame in the window; the window itself starts 4px
  # left of its text area.
  RATE_LIMIT_FRAME_LEFT=$(( monitor_gap_x - 4 + (window_width - RATE_LIMIT_FRAME_WIDTH) / 2 ))
  # Window bottom is gap_y off the screen bottom plus that same 4px, and the
  # frame's own bottom inset is another 12.
  RATE_LIMIT_FRAME_TOP=$(( monitor_h - RATE_LIMIT_PANEL_GAP_Y + 4 - 12 - RATE_LIMIT_FRAME_HEIGHT ))
  GITHUB_ROOF_BASELINE=$(( RATE_LIMIT_FRAME_TOP - GITHUB_ROOF_CLEARANCE ))

  if ! overlay_enabled rate-limit-panel; then
    # Nothing to be the roof of; stand the skyline on the screen bottom instead.
    GITHUB_ROOF_BASELINE=$(( monitor_h - RATE_LIMIT_PANEL_GAP_Y ))
  fi

  # The Linear cards grow downward as tasks land. Give back height rather than
  # let the two meet.
  GITHUB_RESOLVED_HEIGHT="$GITHUB_SKYLINE_HEIGHT"
  if overlay_enabled linear; then
    linear_bottom=$(( linear_gap_y + LINEAR_MINIMUM_HEIGHT + 4 ))
    headroom=$(( GITHUB_ROOF_BASELINE - linear_bottom - GITHUB_LINEAR_CLEARANCE ))
    if (( headroom < GITHUB_RESOLVED_HEIGHT )); then
      GITHUB_RESOLVED_HEIGHT="$headroom"
    fi
  fi
  if (( GITHUB_RESOLVED_HEIGHT < GITHUB_SKYLINE_MIN_HEIGHT )); then
    GITHUB_RESOLVED_HEIGHT="$GITHUB_SKYLINE_MIN_HEIGHT"
  fi
}

github_placement_note() {
  local note="auto roof=$GITHUB_ROOF_BASELINE width=$RATE_LIMIT_FRAME_WIDTH height=$GITHUB_RESOLVED_HEIGHT"
  if [[ -n "$GITHUB_GAP_X" ]]; then
    note="pinned gap_x=$GITHUB_GAP_X $note"
  fi
  if [[ -n "$GITHUB_GAP_Y" ]]; then
    printf "pinned gap_y=%s\n" "$GITHUB_GAP_Y"
  else
    printf "%s\n" "$note"
  fi
}

sessions_placement_note() {
  printf "gap_x=%s gap_y=%s height=%s\n" \
    "$(overlay_gap_x sessions 0)" "$(overlay_gap_y sessions 0)" "$SESSIONS_MINIMUM_HEIGHT"
}

# Sit the 300px-tall map just above the weather card. The window is 456px so
# it shares the weather overlay's width. The diamond's origin is 268px from
# the billing window top; the weather chip starts 74px into its window.
BILLING_RESOLVED_GAP_Y=350
BILLING_WEATHER_GAP=24

billing_placement_for_monitor() {
  local monitor_h="$1"
  local linear_gap_y="$2"
  local band_top=0
  local weather_text_top
  local weather_chip_top
  local resource_gap
  local weather_gap="$WEATHER_GAP_Y"

  if [[ ! "$monitor_h" =~ ^[0-9]+$ ]] || (( monitor_h < 300 )); then
    monitor_h=1080
  fi
  if overlay_enabled resource-monitor; then
    resource_gap="$(overlay_gap_y resource-monitor "$linear_gap_y")"
    [[ "$resource_gap" =~ ^-?[0-9]+$ ]] || resource_gap=0
    band_top=$(( resource_gap + 258 ))
  fi
  if overlay_enabled weather; then
    [[ "$weather_gap" =~ ^-?[0-9]+$ ]] || weather_gap=6
    weather_text_top=$(( monitor_h - weather_gap - 417 ))
    weather_chip_top=$(( weather_text_top + 74 ))
    BILLING_RESOLVED_GAP_Y=$(( weather_chip_top - 268 - BILLING_WEATHER_GAP ))
    if (( BILLING_RESOLVED_GAP_Y < band_top )); then
      BILLING_RESOLVED_GAP_Y="$band_top"
    fi
  elif (( monitor_h - band_top >= 300 )); then
    BILLING_RESOLVED_GAP_Y=$(( band_top + (monitor_h - band_top - 300) / 2 ))
  else
    BILLING_RESOLVED_GAP_Y=$(( (monitor_h - 300) / 2 ))
  fi
  if (( BILLING_RESOLVED_GAP_Y < 0 )); then
    BILLING_RESOLVED_GAP_Y=0
  fi
}

billing_placement_note() {
  local gap_x_note
  if [[ -n "$BILLING_GAP_X" ]]; then
    gap_x_note="pinned gap_x=$BILLING_GAP_X"
  elif overlay_enabled weather; then
    gap_x_note="auto gap_x=$(overlay_gap_x billing 0) (weather-centered)"
  else
    gap_x_note="auto gap_x=$(overlay_gap_x billing 0) (resource)"
  fi
  if [[ -n "$BILLING_GAP_Y" ]]; then
    printf "%s pinned gap_y=%s\n" "$gap_x_note" "$BILLING_GAP_Y"
  else
    printf "%s auto gap_y=%s\n" "$gap_x_note" "$BILLING_RESOLVED_GAP_Y"
  fi
}

overlay_gap_y() {
  local key="$1"
  local linear_gap_y="$2"

  case "$key" in
    linear) printf "%s\n" "$linear_gap_y" ;;
    rate-limit-panel) printf "%s\n" "$RATE_LIMIT_PANEL_GAP_Y" ;;
    minecraft) printf "%s\n" "$MINECRAFT_GAP_Y" ;;
    github)
      if [[ -n "$GITHUB_GAP_Y" ]]; then
        printf "%s\n" "$GITHUB_GAP_Y"
      else
        # bottom_left: gap_y is the distance from the screen bottom up to the
        # roof line, where the renderer puts the plinth.
        printf "%s\n" "$((MONITOR_HEIGHT - GITHUB_ROOF_BASELINE))"
      fi
      ;;
    sessions)
      printf "%s\n" "$SESSIONS_GAP_Y"
      ;;
    weather) printf "%s\n" "$WEATHER_GAP_Y" ;;
    resource-monitor)
      if [[ -n "$RESOURCE_MONITOR_GAP_Y" ]]; then
        printf "%s\n" "$RESOURCE_MONITOR_GAP_Y"
      else
        printf "%s\n" "$linear_gap_y"
      fi
      ;;
    billing)
      if [[ -n "$BILLING_GAP_Y" ]]; then
        printf "%s\n" "$BILLING_GAP_Y"
      else
        printf "%s\n" "$BILLING_RESOLVED_GAP_Y"
      fi
      ;;
    git)
      if [[ -n "$GIT_GAP_Y" ]]; then
        printf "%s\n" "$GIT_GAP_Y"
      else
        printf "%s\n" "$linear_gap_y"
      fi
      ;;
  esac
}

log_generated_overlay() {
  local key="$1"
  local monitor_index="$2"
  local width="$3"
  local monitor_gap_x="$4"
  local linear_gap_y="$5"
  local config_path="$6"

  case "$key" in
    linear)
      log_overlay linear "generated monitor_index=$monitor_index width=$width gap_x=$monitor_gap_x gap_y=$linear_gap_y config=$config_path"
      ;;
    rate-limit-panel)
      log_overlay rate-limit-panel "generated monitor_index=$monitor_index width=$width gap_x=$monitor_gap_x config=$config_path"
      ;;
    minecraft)
      log_overlay minecraft "generated monitor_index=$monitor_index width=$width gap_x=$MINECRAFT_GAP_X gap_y=$MINECRAFT_GAP_Y config=$config_path"
      ;;
    github)
      log_overlay github "generated monitor_index=$monitor_index width=$RATE_LIMIT_FRAME_WIDTH gap_x=$(overlay_gap_x github "$monitor_gap_x") $(github_placement_note) config=$config_path"
      ;;
    weather)
      log_overlay weather "generated monitor_index=$monitor_index width=$width gap_x=$WEATHER_GAP_X gap_y=$WEATHER_GAP_Y config=$config_path"
      ;;
    resource-monitor)
      log_overlay resource-monitor "generated monitor_index=$monitor_index width=$width gap_x=$RESOURCE_MONITOR_GAP_X gap_y=$(overlay_gap_y resource-monitor "$linear_gap_y") config=$config_path"
      ;;
    billing)
      log_overlay billing "generated monitor_index=$monitor_index width=$width gap_x=$(overlay_gap_x billing "$monitor_gap_x") $(billing_placement_note) config=$config_path"
      ;;
    git)
      log_overlay git "generated monitor_index=$monitor_index width=$width gap_x=$GIT_GAP_X gap_y=$(overlay_gap_y git "$linear_gap_y") config=$config_path"
      ;;
    sessions)
      log_overlay sessions "generated monitor_index=$monitor_index width=$SESSIONS_PANEL_WIDTH $(sessions_placement_note) config=$config_path"
      ;;
  esac
}

queue_overlay_launch() {
  local key="$1"
  local monitor_index="$2"
  local config_path="$3"

  queued_launch_keys+=("$key")
  queued_launch_configs+=("$config_path")
  queued_launch_notes+=("monitor_index=$monitor_index config=$config_path")
}

launch_queued_overlays() {
  local index
  local key
  local config_path

  for index in "${!queued_launch_keys[@]}"; do
    key="${queued_launch_keys[$index]}"
    config_path="${queued_launch_configs[$index]}"
    setsid conky -c "$config_path" >> "${overlay_log_path[$key]}" 2>&1 < /dev/null &
    log_overlay "$key" "launched ${queued_launch_notes[$index]} pid=$!"
  done
}

monitor_lines=()
read_monitor_lines monitor_lines
if [[ "$GENERATE_ONLY" -eq 1 && "${#monitor_lines[@]}" -eq 0 ]]; then
  read_cached_monitor_lines monitor_lines
  if [[ "${#monitor_lines[@]}" -gt 0 ]]; then
    log_overlay linear "xrandr unavailable; generating from cached monitor layout"
  fi
fi

LINEAR_MINIMUM_HEIGHT="$(linear_overlay_height 2>>"$LINEAR_LOG_PATH" || true)"
if [[ ! "$LINEAR_MINIMUM_HEIGHT" =~ ^[0-9]+$ ]]; then
  log_overlay linear "could not compute linear overlay height; using 292"
  LINEAR_MINIMUM_HEIGHT=292
fi
log_overlay linear "linear overlay minimum_height=$LINEAR_MINIMUM_HEIGHT (from current cards)"

RATE_LIMIT_PANEL_MINIMUM_HEIGHT="$(rate_limit_panel_overlay_height 2>>"$RATE_LIMIT_PANEL_LOG_PATH" || true)"
if [[ ! "$RATE_LIMIT_PANEL_MINIMUM_HEIGHT" =~ ^[0-9]+$ ]]; then
  log_overlay rate-limit-panel "could not compute rate limit panel height; using 320"
  RATE_LIMIT_PANEL_MINIMUM_HEIGHT=320
fi
log_overlay rate-limit-panel "rate limit panel minimum_height=$RATE_LIMIT_PANEL_MINIMUM_HEIGHT (from current accounts)"

RATE_LIMIT_FRAME_HEIGHT="$(rate_limit_panel_frame_height 2>>"$RATE_LIMIT_PANEL_LOG_PATH" || true)"
if [[ ! "$RATE_LIMIT_FRAME_HEIGHT" =~ ^[0-9]+$ ]]; then
  log_overlay rate-limit-panel "could not compute rate limit frame height; using 296"
  RATE_LIMIT_FRAME_HEIGHT=296
fi
RATE_LIMIT_FRAME_WIDTH="$(rate_limit_panel_frame_width $((OVERLAY_WIDTH + 8)) 2>>"$RATE_LIMIT_PANEL_LOG_PATH" || true)"
if [[ ! "$RATE_LIMIT_FRAME_WIDTH" =~ ^[0-9]+$ ]]; then
  log_overlay rate-limit-panel "could not compute rate limit frame width; using 1000"
  RATE_LIMIT_FRAME_WIDTH=1000
fi
log_overlay github "rate limit frame ${RATE_LIMIT_FRAME_WIDTH}x${RATE_LIMIT_FRAME_HEIGHT} (skyline is sized and placed against it)"

SESSIONS_MINIMUM_HEIGHT=790
if overlay_enabled sessions; then
  SESSIONS_MINIMUM_HEIGHT="$(sessions_overlay_height 2>>"$SESSIONS_LOG_PATH" || true)"
  if [[ ! "$SESSIONS_MINIMUM_HEIGHT" =~ ^[0-9]+$ ]]; then
    log_overlay sessions "could not compute sessions overlay height; using 790"
    SESSIONS_MINIMUM_HEIGHT=790
  fi
  log_overlay sessions "sessions overlay minimum_height=$SESSIONS_MINIMUM_HEIGHT (from current devices and sessions)"
fi

index=0
for line in "${monitor_lines[@]}"; do
  if [[ ! "$line" =~ ([0-9]+)\/[0-9]+x([0-9]+)\/[0-9]+([+-][0-9]+)([+-][0-9]+) ]]; then
    continue
  fi

  width="${BASH_REMATCH[1]}"
  monitor_height="${BASH_REMATCH[2]}"
  monitor_gap_x=$(((width - OVERLAY_WIDTH) / 2))
  linear_gap_y="$LINEAR_GAP_Y"
  if [[ "$line" =~ ^[[:space:]]*[0-9]+:[[:space:]]*[^[:space:]]*\* ]] || { [[ "$MONITOR_HAS_PRIMARY" -eq 0 ]] && [[ "$index" -eq "$LINEAR_PRIMARY_MONITOR_INDEX" ]]; }; then
    linear_gap_y="$LINEAR_PRIMARY_GAP_Y"
  fi

  rate_limit_frame_for_monitor "$monitor_height" "$monitor_gap_x" "$linear_gap_y"
  billing_placement_for_monitor "$monitor_height" "$linear_gap_y"

  for key in "${overlay_keys[@]}"; do
    if overlay_enabled "$key"; then
      config_path="$GENERATED_DIR/$key-overlay-$index.conkyrc"
      extra_height=""
      extra_width=""
      if [[ "$key" == "linear" ]]; then
        extra_height="$LINEAR_MINIMUM_HEIGHT"
      elif [[ "$key" == "rate-limit-panel" ]]; then
        extra_height="$RATE_LIMIT_PANEL_MINIMUM_HEIGHT"
      elif [[ "$key" == "github" ]]; then
        extra_height="$GITHUB_RESOLVED_HEIGHT"
        extra_width="$RATE_LIMIT_FRAME_WIDTH"
      elif [[ "$key" == "sessions" ]]; then
        extra_height="$SESSIONS_MINIMUM_HEIGHT"
      fi
      generate_config "${overlay_config[$key]}" "$config_path" "$index" "$(overlay_gap_x "$key" "$monitor_gap_x")" "$(overlay_gap_y "$key" "$linear_gap_y")" "$extra_height" "$extra_width"
      GENERATED_CONFIG_COUNT=$((GENERATED_CONFIG_COUNT + 1))
    fi
  done

  for key in "${overlay_keys[@]}"; do
    if overlay_enabled "$key"; then
      config_path="$GENERATED_DIR/$key-overlay-$index.conkyrc"
      log_generated_overlay "$key" "$index" "$width" "$monitor_gap_x" "$linear_gap_y" "$config_path"
      if [[ "$GENERATE_ONLY" -eq 0 ]]; then
        queue_overlay_launch "$key" "$index" "$config_path"
      fi
    fi
  done

  index=$((index + 1))
done

if [[ "$index" -eq 0 ]]; then
  log_overlay linear "no monitors detected from xrandr; generating one fallback monitor"
  width=1920
  monitor_height=1080
  monitor_gap_x=350
  linear_gap_y="$LINEAR_PRIMARY_GAP_Y"
  rate_limit_frame_for_monitor "$monitor_height" "$monitor_gap_x" "$linear_gap_y"
  billing_placement_for_monitor "$monitor_height" "$linear_gap_y"

  for key in "${overlay_keys[@]}"; do
    if ! overlay_enabled "$key"; then
      continue
    fi
    config_path="$GENERATED_DIR/$key-overlay-fallback.conkyrc"
    extra_height=""
    extra_width=""
    case "$key" in
      linear) extra_height="$LINEAR_MINIMUM_HEIGHT" ;;
      rate-limit-panel) extra_height="$RATE_LIMIT_PANEL_MINIMUM_HEIGHT" ;;
      github)
        extra_height="$GITHUB_RESOLVED_HEIGHT"
        extra_width="$RATE_LIMIT_FRAME_WIDTH"
        ;;
      sessions) extra_height="$SESSIONS_MINIMUM_HEIGHT" ;;
    esac
    generate_config "${overlay_config[$key]}" "$config_path" 0 \
      "$(overlay_gap_x "$key" "$monitor_gap_x")" \
      "$(overlay_gap_y "$key" "$linear_gap_y")" \
      "$extra_height" "$extra_width"
    GENERATED_CONFIG_COUNT=$((GENERATED_CONFIG_COUNT + 1))
    log_generated_overlay "$key" 0 "$width" "$monitor_gap_x" "$linear_gap_y" "$config_path"
    if [[ "$GENERATE_ONLY" -eq 0 ]]; then
      queue_overlay_launch "$key" 0 "$config_path"
    fi
  done
  index=1
fi

install_generated_configs
prune_stale_generated_configs
cleanup_generation_stage
trap - EXIT

if [[ "$GENERATE_ONLY" -eq 1 ]]; then
  printf "Generated %s overlay config(s) for %s monitor(s) in %s\n" \
    "$GENERATED_CONFIG_COUNT" "$index" "$GENERATED_DIR"
else
  for key in "${overlay_keys[@]}"; do
    terminate_matching_conky_processes "$GENERATED_DIR/$key-overlay-" prefix
  done
  terminate_matching_conky_processes "$GENERATED_DIR/codex-overlay-" prefix
  for key in "${overlay_keys[@]}"; do
    terminate_matching_conky_processes "${overlay_config[$key]}" exact
  done
  terminate_matching_conky_processes "$ROOT/conky/codex-overlay.conkyrc" exact
  for fetch_key in "${fetch_keys[@]}"; do
    stop_fetch_loop "$fetch_key"
  done
  log_overlay linear "stopped existing matching Conky processes"
  rotate_oversized_logs

  for fetch_key in "${fetch_keys[@]}"; do
    if overlay_enabled "${fetch_overlay_key[$fetch_key]}"; then
      start_fetch_loop "$fetch_key"
    fi
  done
  launch_queued_overlays
fi

log_overlay linear "finished; generated_configs=$GENERATED_CONFIG_COUNT monitors=$index"

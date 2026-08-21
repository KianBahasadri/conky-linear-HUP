#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
ENV_PATH="$ROOT/.env"

if [[ -f "$ENV_PATH" ]]; then
  while IFS= read -r env_line || [[ -n "$env_line" ]]; do
    [[ "$env_line" =~ ^[[:space:]]*$ || "$env_line" =~ ^[[:space:]]*# ]] && continue
    [[ "$env_line" == *"="* ]] || continue

    env_key="${env_line%%=*}"
    env_value="${env_line#*=}"
    env_key="${env_key//[[:space:]]/}"
    env_value="${env_value#"${env_value%%[![:space:]]*}"}"
    env_value="${env_value%"${env_value##*[![:space:]]}"}"

    if [[ "$env_value" == \"*\" && "$env_value" == *\" ]]; then
      env_value="${env_value:1:${#env_value}-2}"
    elif [[ "$env_value" == \'*\' && "$env_value" == *\' ]]; then
      env_value="${env_value:1:${#env_value}-2}"
    fi

    [[ "$env_key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    export "$env_key=$env_value"
  done < "$ENV_PATH"
fi

BASE_CONFIG="$ROOT/conky/linear-overlay.conkyrc"
RATE_LIMIT_PANEL_CONFIG="$ROOT/conky/rate-limit-panel-overlay.conkyrc"
MINECRAFT_CONFIG="$ROOT/conky/minecraft-overlay.conkyrc"
GITHUB_CONFIG="$ROOT/conky/github-overlay.conkyrc"
WEATHER_CONFIG="$ROOT/conky/weather-overlay.conkyrc"
RESOURCE_MONITOR_CONFIG="$ROOT/conky/resource-monitor-overlay.conkyrc"
BILLING_CONFIG="$ROOT/conky/billing-overlay.conkyrc"
GIT_CONFIG="$ROOT/conky/git-overlay.conkyrc"
GENERATED_DIR="$ROOT/conky/generated"
CACHE_DIR="$ROOT/cache"
LINEAR_LOG_PATH="$CACHE_DIR/conky-linear.log"
RATE_LIMIT_PANEL_LOG_PATH="$CACHE_DIR/conky-rate-limit-panel.log"
MINECRAFT_LOG_PATH="$CACHE_DIR/conky-minecraft.log"
GITHUB_LOG_PATH="$CACHE_DIR/conky-github.log"
WEATHER_LOG_PATH="$CACHE_DIR/conky-weather.log"
RESOURCE_MONITOR_LOG_PATH="$CACHE_DIR/conky-resource-monitor.log"
BILLING_LOG_PATH="$CACHE_DIR/conky-billing.log"
GIT_LOG_PATH="$CACHE_DIR/conky-git.log"
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
BILLING_FETCH_PID="$CACHE_DIR/billing-fetch-loop.pid"
GIT_FETCH_PID="$CACHE_DIR/git-fetch-loop.pid"
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
GITHUB_GAP_X="${GITHUB_GAP_X:-18}"
# Empty = auto-center the contribution rail between the git panel (top) and
# Minecraft panel (bottom) on each monitor. Set an explicit pixel value to pin it.
GITHUB_GAP_Y="${GITHUB_GAP_Y-}"
GITHUB_REFRESH_SECONDS="${GITHUB_REFRESH_SECONDS:-1800}"
GITHUB_OVERLAY_ENABLED="${GITHUB_OVERLAY_ENABLED:-1}"
# Auto placement spans the rail window across the whole band between the git
# panel and Minecraft; the renderer centers the calendar inside it from the live
# repo count, so the git panel's height is measured there instead of estimated
# here. Only the Minecraft edge and the rail's own size are named here.
# Minecraft: panel + bottom clearance inside its bottom-aligned window.
GITHUB_AUTO_MC_PANEL_H="${GITHUB_AUTO_MC_PANEL_H:-126}"
# Shortest the rail window may be: ~53 weeks × (7px + 4px gap) + top pad.
GITHUB_AUTO_RAIL_H="${GITHUB_AUTO_RAIL_H:-590}"
# Bias the centered rail upward by this many pixels (0 keeps it centered).
GITHUB_AUTO_GAP_NUDGE_UP="${GITHUB_AUTO_GAP_NUDGE_UP:-0}"
# On the primary monitor the git panel is a normal window, so GNOME's top bar
# pushes it down; the github rail is a desktop window measured from screen top.
# Empty = detect from _NET_WORKAREA (fallback 32). Set 0 to disable.
GITHUB_AUTO_PRIMARY_GIT_EXTRA="${GITHUB_AUTO_PRIMARY_GIT_EXTRA-}"
WEATHER_GAP_X="${WEATHER_GAP_X:-18}"
WEATHER_GAP_Y="${WEATHER_GAP_Y:-6}"
WEATHER_REFRESH_SECONDS="${WEATHER_REFRESH_SECONDS:-600}"
WEATHER_OVERLAY_ENABLED="${WEATHER_OVERLAY_ENABLED:-1}"
RESOURCE_MONITOR_GAP_X="${RESOURCE_MONITOR_GAP_X:-0}"
# Empty means follow Linear's per-monitor gap_y so gauge tops stay flush with cards.
RESOURCE_MONITOR_GAP_Y="${RESOURCE_MONITOR_GAP_Y:-}"
RESOURCE_MONITOR_OVERLAY_ENABLED="${RESOURCE_MONITOR_OVERLAY_ENABLED:-1}"
# Empty = follow RESOURCE_MONITOR_GAP_X so both right-side centers align.
BILLING_GAP_X="${BILLING_GAP_X-}"
# Empty = auto-center between the resource HUD above and weather below.
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
GENERATE_ONLY=0
MONITOR_HAS_PRIMARY=0

overlay_keys=(linear rate-limit-panel minecraft github weather resource-monitor billing git)
fetch_keys=(linear codex claude cursor gemini grok opencode commandcode minecraft github weather billing git)

declare -A overlay_disabled_name=(
  [linear]="linear"
  [rate-limit-panel]="rate limit panel"
  [minecraft]="minecraft"
  [github]="github"
  [weather]="weather"
  [resource-monitor]="resource monitor"
  [billing]="billing"
  [git]="git status"
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
  [billing]="Billing"
  [git]="Git"
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
  [billing]="billing"
  [git]="git"
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
  [billing]="$BILLING_REFRESH_SECONDS"
  [git]="$GIT_REFRESH_SECONDS"
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
  [billing]="$ROOT/scripts/fetch_billing_usage.py"
  [git]="$ROOT/scripts/fetch_git_status.py"
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
  [billing]="$BILLING_FETCH_PID"
  [git]="$GIT_FETCH_PID"
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
    log_overlay "$log_key" "stopped existing $label fetch loop pid=$pid"
  fi
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
      "$script_path" >/dev/null 2>>"$log_path" || true
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
    "$RATE_LIMIT_RECENT_CHANGE_WINDOW" </dev/null >/dev/null 2>&1 &
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

if [[ ! "$LINEAR_PRIMARY_MONITOR_INDEX" =~ ^[0-9]+$ ]]; then
  log_overlay linear "invalid LINEAR_PRIMARY_MONITOR_INDEX=$LINEAR_PRIMARY_MONITOR_INDEX; using 0"
  LINEAR_PRIMARY_MONITOR_INDEX=0
fi

if [[ ! "$PRIMARY_WAIT_SECONDS" =~ ^[0-9]+$ ]]; then
  log_overlay linear "invalid PRIMARY_WAIT_SECONDS=$PRIMARY_WAIT_SECONDS; using 20"
  PRIMARY_WAIT_SECONDS=20
fi

if [[ ! "$RATE_LIMIT_CHANGED_INTERVAL" =~ ^[1-9][0-9]*$ ]]; then
  log_overlay rate-limit-panel "invalid RATE_LIMIT_CHANGED_INTERVAL=$RATE_LIMIT_CHANGED_INTERVAL; using 60"
  RATE_LIMIT_CHANGED_INTERVAL=60
fi

if [[ ! "$RATE_LIMIT_UNCHANGED_INTERVAL" =~ ^[1-9][0-9]*$ ]]; then
  log_overlay rate-limit-panel "invalid RATE_LIMIT_UNCHANGED_INTERVAL=$RATE_LIMIT_UNCHANGED_INTERVAL; using 300"
  RATE_LIMIT_UNCHANGED_INTERVAL=300
fi

if [[ ! "$RATE_LIMIT_RECENT_CHANGE_WINDOW" =~ ^[1-9][0-9]*$ ]]; then
  log_overlay rate-limit-panel "invalid RATE_LIMIT_RECENT_CHANGE_WINDOW=$RATE_LIMIT_RECENT_CHANGE_WINDOW; using 600"
  RATE_LIMIT_RECENT_CHANGE_WINDOW=600
fi

if [[ -n "$BILLING_GAP_X" && ! "$BILLING_GAP_X" =~ ^-?[0-9]+$ ]]; then
  log_overlay billing "invalid BILLING_GAP_X=$BILLING_GAP_X; following resource monitor"
  BILLING_GAP_X=""
fi

if [[ -n "$BILLING_GAP_Y" && ! "$BILLING_GAP_Y" =~ ^-?[0-9]+$ ]]; then
  log_overlay billing "invalid BILLING_GAP_Y=$BILLING_GAP_Y; using automatic placement"
  BILLING_GAP_Y=""
fi

if [[ ! "$BILLING_REFRESH_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  log_overlay billing "invalid BILLING_REFRESH_SECONDS=$BILLING_REFRESH_SECONDS; using 900"
  BILLING_REFRESH_SECONDS=900
  fetch_interval[billing]="$BILLING_REFRESH_SECONDS"
fi

log_overlay linear "starting; root=$ROOT generate_only=$GENERATE_ONLY"
for key in "${overlay_keys[@]}"; do
  enabled_var="${overlay_enabled_var[$key]}"
  if env_flag_disabled "${!enabled_var}"; then
    log_overlay "$key" "${overlay_disabled_name[$key]} overlay disabled by $enabled_var=${!enabled_var}"
  fi
done

for key in "${overlay_keys[@]}"; do
  pkill -f "$GENERATED_DIR/$key-overlay-" 2>/dev/null || true
  rm -f "$GENERATED_DIR/$key-overlay-"*.conkyrc
done
pkill -f "$GENERATED_DIR/codex-overlay-" 2>/dev/null || true
rm -f "$GENERATED_DIR/codex-overlay-"*.conkyrc
for key in "${overlay_keys[@]}"; do
  pkill -f "${overlay_config[$key]}" 2>/dev/null || true
done
pkill -f "$ROOT/conky/codex-overlay.conkyrc" 2>/dev/null || true
for fetch_key in "${fetch_keys[@]}"; do
  stop_fetch_loop "$fetch_key"
done
pkill -f "$ROOT/scripts/fetch_minecraft_status.py" 2>/dev/null || true
pkill -f "$ROOT/scripts/fetch_github_contributions.py" 2>/dev/null || true
pkill -f "$ROOT/scripts/fetch_weather.py" 2>/dev/null || true
pkill -f "$ROOT/scripts/fetch_billing_usage.py" 2>/dev/null || true
pkill -f "$ROOT/scripts/fetch_git_status.py" 2>/dev/null || true
log_overlay linear "stopped existing matching Conky processes"

if [[ "$GENERATE_ONLY" -eq 0 ]]; then
  for fetch_key in "${fetch_keys[@]}"; do
    if overlay_enabled "${fetch_overlay_key[$fetch_key]}"; then
      start_fetch_loop "$fetch_key"
    fi
  done
fi

linear_overlay_height() {
  python3 "$ROOT/scripts/fetch_linear_tasks.py" --print-overlay-height
}

rate_limit_panel_overlay_height() {
  python3 "$ROOT/scripts/fetch_common.py" --print-rate-limit-panel-height
}

generate_config() {
  local source_config="$1"
  local output_config="$2"
  local monitor_index="$3"
  local monitor_gap_x="$4"
  local monitor_gap_y="$5"
  local minimum_height="${6:-}"
  local lua_entrypoint="$ROOT/conky/overlay-entrypoint.lua"

  if [[ "$source_config" == "$BILLING_CONFIG" ]]; then
    lua_entrypoint="$ROOT/conky/billing-entrypoint.lua"
  fi

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
  done < "$source_config" > "$output_config"
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

overlay_gap_x() {
  local key="$1"
  local monitor_gap_x="$2"

  case "$key" in
    linear|rate-limit-panel) printf "%s\n" "$monitor_gap_x" ;;
    minecraft) printf "%s\n" "$MINECRAFT_GAP_X" ;;
    github) printf "%s\n" "$GITHUB_GAP_X" ;;
    weather) printf "%s\n" "$WEATHER_GAP_X" ;;
    resource-monitor) printf "%s\n" "$RESOURCE_MONITOR_GAP_X" ;;
    billing)
      if [[ -n "$BILLING_GAP_X" ]]; then
        printf "%s\n" "$BILLING_GAP_X"
      else
        printf "%s\n" "$RESOURCE_MONITOR_GAP_X"
      fi
      ;;
    git) printf "%s\n" "$GIT_GAP_X" ;;
  esac
}

# GNOME reports a single workarea inset (top bar) for the whole virtual
# desktop. The bar itself only sits on the primary monitor.
primary_top_inset() {
  local wa
  wa="$(xprop -root _NET_WORKAREA 2>/dev/null || true)"
  if [[ "$wa" =~ =\ *([0-9]+),\ *([0-9]+), ]]; then
    printf "%s\n" "${BASH_REMATCH[2]}"
    return
  fi
  printf "%s\n" 32
}

if [[ -z "$GITHUB_AUTO_PRIMARY_GIT_EXTRA" ]]; then
  GITHUB_AUTO_PRIMARY_GIT_EXTRA="$(primary_top_inset)"
fi
if [[ ! "$GITHUB_AUTO_PRIMARY_GIT_EXTRA" =~ ^[0-9]+$ ]]; then
  log_overlay github "invalid GITHUB_AUTO_PRIMARY_GIT_EXTRA=$GITHUB_AUTO_PRIMARY_GIT_EXTRA; using 32"
  GITHUB_AUTO_PRIMARY_GIT_EXTRA=32
fi

if [[ ! "$GITHUB_AUTO_GAP_NUDGE_UP" =~ ^[0-9]+$ ]]; then
  log_overlay github "invalid GITHUB_AUTO_GAP_NUDGE_UP=$GITHUB_AUTO_GAP_NUDGE_UP; using 0"
  GITHUB_AUTO_GAP_NUDGE_UP=0
fi

# Band the contribution rail is centered in: from the top of the git panel's
# window down to where the Minecraft panel starts. The rail window covers the
# whole band and the renderer centers the calendar inside it on every draw, so
# the rail follows the git panel as repo rows come and go.
GITHUB_BAND_GIT_TOP=""
GITHUB_BAND_TOP=0
GITHUB_BAND_BOTTOM=0
GITHUB_BAND_HEIGHT=0

github_band_for_monitor() {
  local monitor_h="$1"
  local git_gap_y="$2"
  local is_primary="${3:-0}"
  local mc_clearance=0

  if [[ ! "$monitor_h" =~ ^[0-9]+$ ]] || (( monitor_h < 200 )); then
    monitor_h=1080
  fi
  if [[ ! "$git_gap_y" =~ ^-?[0-9]+$ ]]; then
    git_gap_y=1
  fi

  GITHUB_BAND_GIT_TOP=""
  if overlay_enabled git; then
    GITHUB_BAND_GIT_TOP="$git_gap_y"
    # Primary: git (normal) is pushed below the top bar; github (desktop) is not.
    if [[ "$is_primary" == "1" ]] && (( GITHUB_AUTO_PRIMARY_GIT_EXTRA > git_gap_y )); then
      GITHUB_BAND_GIT_TOP="$GITHUB_AUTO_PRIMARY_GIT_EXTRA"
    fi
  fi

  if overlay_enabled minecraft; then
    mc_clearance=$((MINECRAFT_GAP_Y + GITHUB_AUTO_MC_PANEL_H))
  fi

  GITHUB_BAND_TOP="${GITHUB_BAND_GIT_TOP:-0}"
  if (( GITHUB_BAND_TOP < 0 )); then
    GITHUB_BAND_TOP=0
  fi
  GITHUB_BAND_BOTTOM=$((monitor_h - mc_clearance))
  if (( GITHUB_BAND_BOTTOM - GITHUB_BAND_TOP < GITHUB_AUTO_RAIL_H )); then
    GITHUB_BAND_BOTTOM=$((GITHUB_BAND_TOP + GITHUB_AUTO_RAIL_H))
  fi
  GITHUB_BAND_HEIGHT=$((GITHUB_BAND_BOTTOM - GITHUB_BAND_TOP))
}

github_placement_note() {
  if [[ -n "$GITHUB_GAP_Y" ]]; then
    printf "pinned gap_y=%s\n" "$GITHUB_GAP_Y"
  else
    printf "auto band=%s..%s height=%s git_top=%s\n" \
      "$GITHUB_BAND_TOP" "$GITHUB_BAND_BOTTOM" "$GITHUB_BAND_HEIGHT" "${GITHUB_BAND_GIT_TOP:-none}"
  fi
}

# Keep the 300px map centered in the right-side lane that remains between the
# top resource HUD and bottom weather panel. The explicit BILLING_GAP_Y escape
# hatch is useful on unusual monitor layouts.
BILLING_RESOLVED_GAP_Y=350

billing_placement_for_monitor() {
  local monitor_h="$1"
  local linear_gap_y="$2"
  local band_top=0
  local band_bottom
  local available
  local resource_gap
  local weather_gap="$WEATHER_GAP_Y"

  if [[ ! "$monitor_h" =~ ^[0-9]+$ ]] || (( monitor_h < 300 )); then
    monitor_h=1080
  fi
  band_bottom="$monitor_h"
  if overlay_enabled resource-monitor; then
    resource_gap="$(overlay_gap_y resource-monitor "$linear_gap_y")"
    [[ "$resource_gap" =~ ^-?[0-9]+$ ]] || resource_gap=0
    band_top=$(( resource_gap + 258 ))
  fi
  if overlay_enabled weather; then
    [[ "$weather_gap" =~ ^-?[0-9]+$ ]] || weather_gap=6
    band_bottom=$(( monitor_h - weather_gap - 276 ))
  fi
  available=$(( band_bottom - band_top ))
  if (( available >= 300 )); then
    BILLING_RESOLVED_GAP_Y=$(( band_top + (available - 300) / 2 ))
  else
    BILLING_RESOLVED_GAP_Y=$(( (monitor_h - 300) / 2 ))
    (( BILLING_RESOLVED_GAP_Y < 0 )) && BILLING_RESOLVED_GAP_Y=0
  fi
}

billing_placement_note() {
  if [[ -n "$BILLING_GAP_Y" ]]; then
    printf "pinned gap_y=%s\n" "$BILLING_GAP_Y"
  else
    printf "auto gap_y=%s\n" "$BILLING_RESOLVED_GAP_Y"
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
        printf "%s\n" "$GITHUB_BAND_TOP"
      fi
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
      log_overlay github "generated monitor_index=$monitor_index width=$width gap_x=$GITHUB_GAP_X $(github_placement_note) config=$config_path"
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
  esac
}

launch_overlay() {
  local key="$1"
  local monitor_index="$2"
  local width="$3"
  local monitor_gap_x="$4"
  local linear_gap_y="$5"
  local config_path="$6"
  local -a launch_env=()

  if [[ "$key" == "github" && -z "$GITHUB_GAP_Y" ]]; then
    # Screen-space band the renderer re-centers the rail in on every draw.
    launch_env=(
      "GITHUB_RAIL_WINDOW_TOP=$GITHUB_BAND_TOP"
      "GITHUB_RAIL_BAND_BOTTOM=$GITHUB_BAND_BOTTOM"
      "GITHUB_RAIL_GIT_TOP=$GITHUB_BAND_GIT_TOP"
      "GITHUB_RAIL_NUDGE_UP=$GITHUB_AUTO_GAP_NUDGE_UP"
    )
  fi

  setsid env ${launch_env[@]+"${launch_env[@]}"} conky -c "$config_path" >> "${overlay_log_path[$key]}" 2>&1 < /dev/null &

  case "$key" in
    linear)
      log_overlay linear "launched monitor_index=$monitor_index width=$width gap_x=$monitor_gap_x gap_y=$linear_gap_y config=$config_path pid=$!"
      ;;
    rate-limit-panel)
      log_overlay rate-limit-panel "launched monitor_index=$monitor_index width=$width gap_x=$monitor_gap_x config=$config_path pid=$!"
      ;;
    minecraft)
      log_overlay minecraft "launched monitor_index=$monitor_index width=$width gap_x=$MINECRAFT_GAP_X gap_y=$MINECRAFT_GAP_Y config=$config_path pid=$!"
      ;;
    github)
      log_overlay github "launched monitor_index=$monitor_index width=$width gap_x=$GITHUB_GAP_X $(github_placement_note) config=$config_path pid=$!"
      ;;
    weather)
      log_overlay weather "launched monitor_index=$monitor_index width=$width gap_x=$WEATHER_GAP_X gap_y=$WEATHER_GAP_Y config=$config_path pid=$!"
      ;;
    resource-monitor)
      log_overlay resource-monitor "launched monitor_index=$monitor_index width=$width gap_x=$RESOURCE_MONITOR_GAP_X gap_y=$(overlay_gap_y resource-monitor "$linear_gap_y") config=$config_path pid=$!"
      ;;
    billing)
      log_overlay billing "launched monitor_index=$monitor_index width=$width gap_x=$(overlay_gap_x billing "$monitor_gap_x") $(billing_placement_note) config=$config_path pid=$!"
      ;;
    git)
      log_overlay git "launched monitor_index=$monitor_index width=$width gap_x=$GIT_GAP_X gap_y=$(overlay_gap_y git "$linear_gap_y") config=$config_path pid=$!"
      ;;
  esac
}

launch_fallback_overlay() {
  local key="$1"
  local config_path="${overlay_config[$key]}"

  setsid conky -c "$config_path" >> "${overlay_log_path[$key]}" 2>&1 < /dev/null &
  log_overlay "$key" "launched fallback config=$config_path pid=$!"
}

monitor_lines=()
read_monitor_lines monitor_lines

LINEAR_MINIMUM_HEIGHT="$(linear_overlay_height 2>>"$LINEAR_LOG_PATH" || true)"
if [[ ! "$LINEAR_MINIMUM_HEIGHT" =~ ^[0-9]+$ ]]; then
  log_overlay linear "could not compute linear overlay height; using 528"
  LINEAR_MINIMUM_HEIGHT=528
fi
log_overlay linear "linear overlay minimum_height=$LINEAR_MINIMUM_HEIGHT (from current cards)"

RATE_LIMIT_PANEL_MINIMUM_HEIGHT="$(rate_limit_panel_overlay_height 2>>"$RATE_LIMIT_PANEL_LOG_PATH" || true)"
if [[ ! "$RATE_LIMIT_PANEL_MINIMUM_HEIGHT" =~ ^[0-9]+$ ]]; then
  log_overlay rate-limit-panel "could not compute rate limit panel height; using 320"
  RATE_LIMIT_PANEL_MINIMUM_HEIGHT=320
fi
log_overlay rate-limit-panel "rate limit panel minimum_height=$RATE_LIMIT_PANEL_MINIMUM_HEIGHT (from current accounts)"

index=0
for line in "${monitor_lines[@]}"; do
  if [[ ! "$line" =~ ([0-9]+)\/[0-9]+x([0-9]+)\/[0-9]+\+(-?[0-9]+)\+(-?[0-9]+) ]]; then
    continue
  fi

  width="${BASH_REMATCH[1]}"
  monitor_height="${BASH_REMATCH[2]}"
  monitor_gap_x=$(((width - OVERLAY_WIDTH) / 2))
  linear_gap_y="$LINEAR_GAP_Y"
  is_primary=0
  if [[ "$line" =~ ^[[:space:]]*[0-9]+:[[:space:]]*[^[:space:]]*\* ]] || { [[ "$MONITOR_HAS_PRIMARY" -eq 0 ]] && [[ "$index" -eq "$LINEAR_PRIMARY_MONITOR_INDEX" ]]; }; then
    linear_gap_y="$LINEAR_PRIMARY_GAP_Y"
    is_primary=1
  fi

  github_band_for_monitor "$monitor_height" "$(overlay_gap_y git "$linear_gap_y")" "$is_primary"
  billing_placement_for_monitor "$monitor_height" "$linear_gap_y"

  for key in "${overlay_keys[@]}"; do
    if overlay_enabled "$key"; then
      config_path="$GENERATED_DIR/$key-overlay-$index.conkyrc"
      extra_height=""
      if [[ "$key" == "linear" ]]; then
        extra_height="$LINEAR_MINIMUM_HEIGHT"
      elif [[ "$key" == "rate-limit-panel" ]]; then
        extra_height="$RATE_LIMIT_PANEL_MINIMUM_HEIGHT"
      elif [[ "$key" == "github" && -z "$GITHUB_GAP_Y" ]]; then
        extra_height="$GITHUB_BAND_HEIGHT"
      fi
      generate_config "${overlay_config[$key]}" "$config_path" "$index" "$(overlay_gap_x "$key" "$monitor_gap_x")" "$(overlay_gap_y "$key" "$linear_gap_y")" "$extra_height"
    fi
  done

  for key in "${overlay_keys[@]}"; do
    if overlay_enabled "$key"; then
      config_path="$GENERATED_DIR/$key-overlay-$index.conkyrc"
      if [[ "$GENERATE_ONLY" -eq 0 ]]; then
        launch_overlay "$key" "$index" "$width" "$monitor_gap_x" "$linear_gap_y" "$config_path"
      else
        log_generated_overlay "$key" "$index" "$width" "$monitor_gap_x" "$linear_gap_y" "$config_path"
      fi
    fi
  done

  index=$((index + 1))
done

if [[ "$index" -eq 0 ]]; then
  log_overlay linear "no monitors detected from xrandr; using base config"
  if [[ "$GENERATE_ONLY" -eq 0 ]]; then
    for key in "${overlay_keys[@]}"; do
      if overlay_enabled "$key"; then
        if [[ "$key" == "linear" ]]; then
          config_path="$GENERATED_DIR/linear-overlay-fallback.conkyrc"
          generate_config "${overlay_config[$key]}" "$config_path" 0 350 "$LINEAR_PRIMARY_GAP_Y" "$LINEAR_MINIMUM_HEIGHT"
          setsid conky -c "$config_path" >> "${overlay_log_path[$key]}" 2>&1 < /dev/null &
          log_overlay linear "launched fallback config=$config_path height=$LINEAR_MINIMUM_HEIGHT pid=$!"
        elif [[ "$key" == "rate-limit-panel" ]]; then
          config_path="$GENERATED_DIR/rate-limit-panel-overlay-fallback.conkyrc"
          generate_config "${overlay_config[$key]}" "$config_path" 0 350 "$RATE_LIMIT_PANEL_GAP_Y" "$RATE_LIMIT_PANEL_MINIMUM_HEIGHT"
          setsid conky -c "$config_path" >> "${overlay_log_path[$key]}" 2>&1 < /dev/null &
          log_overlay rate-limit-panel "launched fallback config=$config_path height=$RATE_LIMIT_PANEL_MINIMUM_HEIGHT pid=$!"
        else
          launch_fallback_overlay "$key"
        fi
      fi
    done
  fi
fi

if [[ "$GENERATE_ONLY" -eq 1 ]]; then
  printf "Generated %s overlay config(s) in %s\n" "$index" "$GENERATED_DIR"
fi

log_overlay linear "finished; generated_configs=$index"

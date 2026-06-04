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
CODEX_CONFIG="$ROOT/conky/codex-overlay.conkyrc"
MINECRAFT_CONFIG="$ROOT/conky/minecraft-overlay.conkyrc"
GITHUB_CONFIG="$ROOT/conky/github-overlay.conkyrc"
GENERATED_DIR="$ROOT/conky/generated"
CACHE_DIR="$ROOT/cache"
LINEAR_LOG_PATH="$CACHE_DIR/conky-linear.log"
CODEX_LOG_PATH="$CACHE_DIR/conky-codex.log"
MINECRAFT_LOG_PATH="$CACHE_DIR/conky-minecraft.log"
GITHUB_LOG_PATH="$CACHE_DIR/conky-github.log"
LINEAR_FETCH_PID="$CACHE_DIR/linear-fetch-loop.pid"
CODEX_FETCH_PID="$CACHE_DIR/codex-fetch-loop.pid"
CLAUDE_FETCH_PID="$CACHE_DIR/claude-fetch-loop.pid"
MINECRAFT_FETCH_PID="$CACHE_DIR/minecraft-fetch-loop.pid"
GITHUB_FETCH_PID="$CACHE_DIR/github-fetch-loop.pid"
OVERLAY_WIDTH=1540
LINEAR_GAP_Y=4
LINEAR_PRIMARY_GAP_Y=34
LINEAR_PRIMARY_MONITOR_INDEX="${LINEAR_PRIMARY_MONITOR_INDEX:-0}"
LINEAR_OVERLAY_ENABLED="${LINEAR_OVERLAY_ENABLED:-1}"
PRIMARY_WAIT_SECONDS="${PRIMARY_WAIT_SECONDS:-20}"
CODEX_GAP_Y=12
CODEX_OVERLAY_ENABLED="${CODEX_OVERLAY_ENABLED:-1}"
MINECRAFT_GAP_X="${MINECRAFT_GAP_X:-4}"
MINECRAFT_GAP_Y="${MINECRAFT_GAP_Y:-12}"
MINECRAFT_REFRESH_SECONDS="${MINECRAFT_REFRESH_SECONDS:-60}"
MINECRAFT_OVERLAY_ENABLED="${MINECRAFT_OVERLAY_ENABLED:-1}"
GITHUB_GAP_X="${GITHUB_GAP_X:-18}"
GITHUB_GAP_Y="${GITHUB_GAP_Y:-0}"
GITHUB_REFRESH_SECONDS="${GITHUB_REFRESH_SECONDS:-1800}"
GITHUB_OVERLAY_ENABLED="${GITHUB_OVERLAY_ENABLED:-1}"
GENERATE_ONLY=0
MONITOR_HAS_PRIMARY=0

overlay_keys=(linear codex minecraft github)
fetch_keys=(linear codex claude minecraft github)

declare -A overlay_label=(
  [linear]="Linear"
  [codex]="Codex"
  [minecraft]="Minecraft"
  [github]="GitHub"
)
declare -A overlay_disabled_name=(
  [linear]="linear"
  [codex]="codex"
  [minecraft]="minecraft"
  [github]="github"
)
declare -A overlay_config=(
  [linear]="$BASE_CONFIG"
  [codex]="$CODEX_CONFIG"
  [minecraft]="$MINECRAFT_CONFIG"
  [github]="$GITHUB_CONFIG"
)
declare -A overlay_log_path=(
  [linear]="$LINEAR_LOG_PATH"
  [codex]="$CODEX_LOG_PATH"
  [minecraft]="$MINECRAFT_LOG_PATH"
  [github]="$GITHUB_LOG_PATH"
)
declare -A overlay_enabled_var=(
  [linear]="LINEAR_OVERLAY_ENABLED"
  [codex]="CODEX_OVERLAY_ENABLED"
  [minecraft]="MINECRAFT_OVERLAY_ENABLED"
  [github]="GITHUB_OVERLAY_ENABLED"
)

declare -A fetch_label=(
  [linear]="Linear"
  [codex]="Codex"
  [claude]="Claude"
  [minecraft]="Minecraft"
  [github]="GitHub"
)
declare -A fetch_overlay_key=(
  [linear]="linear"
  [codex]="codex"
  [claude]="codex"
  [minecraft]="minecraft"
  [github]="github"
)
declare -A fetch_interval=(
  [linear]="180"
  [codex]="300"
  [claude]="60"
  [minecraft]="$MINECRAFT_REFRESH_SECONDS"
  [github]="$GITHUB_REFRESH_SECONDS"
)
declare -A fetch_script=(
  [linear]="$ROOT/scripts/fetch_linear_tasks.py"
  [codex]="$ROOT/scripts/fetch_codex_usage.py"
  [claude]="$ROOT/scripts/fetch_claude_usage.py"
  [minecraft]="$ROOT/scripts/fetch_minecraft_status.py"
  [github]="$ROOT/scripts/fetch_github_contributions.py"
)
declare -A fetch_pid_file=(
  [linear]="$LINEAR_FETCH_PID"
  [codex]="$CODEX_FETCH_PID"
  [claude]="$CLAUDE_FETCH_PID"
  [minecraft]="$MINECRAFT_FETCH_PID"
  [github]="$GITHUB_FETCH_PID"
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

  stop_fetch_loop "$fetch_key"

  setsid bash -c '
    script_path="$1"
    log_path="$2"
    interval_seconds="$3"

    while true; do
      "$script_path" >/dev/null 2>>"$log_path" || true
      sleep "$interval_seconds"
    done
  ' bash "$script_path" "$log_path" "$interval_seconds" </dev/null >/dev/null 2>&1 &
  printf '%s\n' "$!" > "$pid_file"
  log_overlay "$log_key" "started $label fetch loop interval=${interval_seconds}s pid=$!"
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

log_overlay linear "starting; root=$ROOT generate_only=$GENERATE_ONLY"
for key in "${overlay_keys[@]}"; do
  enabled_var="${overlay_enabled_var[$key]}"
  if env_flag_disabled "${!enabled_var}"; then
    log_overlay "$key" "${overlay_disabled_name[$key]} overlay disabled by $enabled_var=${!enabled_var}"
  fi
done

for key in "${overlay_keys[@]}"; do
  pkill -f "$GENERATED_DIR/$key-overlay-" 2>/dev/null || true
done
for key in "${overlay_keys[@]}"; do
  pkill -f "${overlay_config[$key]}" 2>/dev/null || true
done
for fetch_key in "${fetch_keys[@]}"; do
  stop_fetch_loop "$fetch_key"
done
pkill -f "$ROOT/scripts/fetch_minecraft_status.py" 2>/dev/null || true
pkill -f "$ROOT/scripts/fetch_github_contributions.py" 2>/dev/null || true
log_overlay linear "stopped existing matching Conky processes"

if [[ "$GENERATE_ONLY" -eq 0 ]]; then
  for fetch_key in "${fetch_keys[@]}"; do
    if overlay_enabled "${fetch_overlay_key[$fetch_key]}"; then
      start_fetch_loop "$fetch_key"
    fi
  done
fi

generate_config() {
  local source_config="$1"
  local output_config="$2"
  local monitor_index="$3"
  local monitor_gap_x="$4"
  local monitor_gap_y="$5"

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
      "  lua_load = "*)
        printf "  lua_load = '%s/conky/overlay-entrypoint.lua',\n" "$ROOT"
        ;;
      *"fetch_linear_tasks.py"*) ;;
      *"fetch_codex_usage.py"*) ;;
      *"fetch_claude_usage.py"*) ;;
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
    linear|codex) printf "%s\n" "$monitor_gap_x" ;;
    minecraft) printf "%s\n" "$MINECRAFT_GAP_X" ;;
    github) printf "%s\n" "$GITHUB_GAP_X" ;;
  esac
}

overlay_gap_y() {
  local key="$1"
  local linear_gap_y="$2"

  case "$key" in
    linear) printf "%s\n" "$linear_gap_y" ;;
    codex) printf "%s\n" "$CODEX_GAP_Y" ;;
    minecraft) printf "%s\n" "$MINECRAFT_GAP_Y" ;;
    github) printf "%s\n" "$GITHUB_GAP_Y" ;;
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
    codex)
      log_overlay codex "generated monitor_index=$monitor_index width=$width gap_x=$monitor_gap_x config=$config_path"
      ;;
    minecraft)
      log_overlay minecraft "generated monitor_index=$monitor_index width=$width gap_x=$MINECRAFT_GAP_X gap_y=$MINECRAFT_GAP_Y config=$config_path"
      ;;
    github)
      log_overlay github "generated monitor_index=$monitor_index width=$width gap_x=$GITHUB_GAP_X gap_y=$GITHUB_GAP_Y config=$config_path"
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

  setsid conky -c "$config_path" >> "${overlay_log_path[$key]}" 2>&1 < /dev/null &

  case "$key" in
    linear)
      log_overlay linear "launched monitor_index=$monitor_index width=$width gap_x=$monitor_gap_x gap_y=$linear_gap_y config=$config_path pid=$!"
      ;;
    codex)
      log_overlay codex "launched monitor_index=$monitor_index width=$width gap_x=$monitor_gap_x config=$config_path pid=$!"
      ;;
    minecraft)
      log_overlay minecraft "launched monitor_index=$monitor_index width=$width gap_x=$MINECRAFT_GAP_X gap_y=$MINECRAFT_GAP_Y config=$config_path pid=$!"
      ;;
    github)
      log_overlay github "launched monitor_index=$monitor_index width=$width gap_x=$GITHUB_GAP_X gap_y=$GITHUB_GAP_Y config=$config_path pid=$!"
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

index=0
for line in "${monitor_lines[@]}"; do
  if [[ ! "$line" =~ ([0-9]+)\/[0-9]+x([0-9]+)\/[0-9]+\+(-?[0-9]+)\+(-?[0-9]+) ]]; then
    continue
  fi

  width="${BASH_REMATCH[1]}"
  monitor_gap_x=$(((width - OVERLAY_WIDTH) / 2))
  linear_gap_y="$LINEAR_GAP_Y"
  if [[ "$line" =~ ^[[:space:]]*[0-9]+:[[:space:]]*[^[:space:]]*\* ]] || { [[ "$MONITOR_HAS_PRIMARY" -eq 0 ]] && [[ "$index" -eq "$LINEAR_PRIMARY_MONITOR_INDEX" ]]; }; then
    linear_gap_y="$LINEAR_PRIMARY_GAP_Y"
  fi

  for key in "${overlay_keys[@]}"; do
    if overlay_enabled "$key"; then
      config_path="$GENERATED_DIR/$key-overlay-$index.conkyrc"
      generate_config "${overlay_config[$key]}" "$config_path" "$index" "$(overlay_gap_x "$key" "$monitor_gap_x")" "$(overlay_gap_y "$key" "$linear_gap_y")"
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
        launch_fallback_overlay "$key"
      fi
    done
  fi
fi

if [[ "$GENERATE_ONLY" -eq 1 ]]; then
  printf "Generated %s overlay config(s) in %s\n" "$index" "$GENERATED_DIR"
fi

log_overlay linear "finished; generated_configs=$index"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BASE_CONFIG="$ROOT/conky/linear-overlay.conkyrc"
CODEX_CONFIG="$ROOT/conky/codex-overlay.conkyrc"
GENERATED_DIR="$ROOT/conky/generated"
CACHE_DIR="$ROOT/cache"
LOG_PATH="$CACHE_DIR/conky-linear.log"
LINEAR_FETCH_PID="$CACHE_DIR/linear-fetch-loop.pid"
CODEX_FETCH_PID="$CACHE_DIR/codex-fetch-loop.pid"
OVERLAY_WIDTH=1540
LINEAR_GAP_Y=4
LINEAR_PRIMARY_GAP_Y=34
LINEAR_PRIMARY_MONITOR_INDEX="${LINEAR_PRIMARY_MONITOR_INDEX:-0}"
PRIMARY_WAIT_SECONDS="${PRIMARY_WAIT_SECONDS:-20}"
CODEX_GAP_Y=12
GENERATE_ONLY=0
MONITOR_HAS_PRIMARY=0

log() {
  printf '[%s] start_conky_overlays: %s\n' "$(date --iso-8601=seconds)" "$*" >> "$LOG_PATH"
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
    log "stopped existing $label fetch loop pid=$pid"
  fi
  rm -f "$pid_file"
}

start_fetch_loop() {
  local label="$1"
  local interval_seconds="$2"
  local script_path="$3"
  local pid_file="$4"

  stop_fetch_loop "$pid_file" "$label"

  setsid bash -c '
    script_path="$1"
    log_path="$2"
    interval_seconds="$3"

    while true; do
      "$script_path" >/dev/null 2>>"$log_path" || true
      sleep "$interval_seconds"
    done
  ' bash "$script_path" "$LOG_PATH" "$interval_seconds" </dev/null >/dev/null 2>&1 &
  printf '%s\n' "$!" > "$pid_file"
  log "started $label fetch loop interval=${interval_seconds}s pid=$!"
}

if [[ "${1:-}" == "--generate-only" ]]; then
  GENERATE_ONLY=1
fi

mkdir -p "$GENERATED_DIR"
mkdir -p "$CACHE_DIR"

if [[ ! "$LINEAR_PRIMARY_MONITOR_INDEX" =~ ^[0-9]+$ ]]; then
  log "invalid LINEAR_PRIMARY_MONITOR_INDEX=$LINEAR_PRIMARY_MONITOR_INDEX; using 0"
  LINEAR_PRIMARY_MONITOR_INDEX=0
fi

if [[ ! "$PRIMARY_WAIT_SECONDS" =~ ^[0-9]+$ ]]; then
  log "invalid PRIMARY_WAIT_SECONDS=$PRIMARY_WAIT_SECONDS; using 20"
  PRIMARY_WAIT_SECONDS=20
fi

log "starting; root=$ROOT generate_only=$GENERATE_ONLY"

pkill -f "$GENERATED_DIR/linear-overlay-" 2>/dev/null || true
pkill -f "$GENERATED_DIR/codex-overlay-" 2>/dev/null || true
pkill -f "$BASE_CONFIG" 2>/dev/null || true
pkill -f "$CODEX_CONFIG" 2>/dev/null || true
stop_fetch_loop "$LINEAR_FETCH_PID" "Linear"
stop_fetch_loop "$CODEX_FETCH_PID" "Codex"
log "stopped existing matching Conky processes"

if [[ "$GENERATE_ONLY" -eq 0 ]]; then
  start_fetch_loop "Linear" 180 "$ROOT/scripts/fetch_linear_tasks.py" "$LINEAR_FETCH_PID"
  start_fetch_loop "Codex" 300 "$ROOT/scripts/fetch_codex_usage.py" "$CODEX_FETCH_PID"
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
        printf "  lua_load = '%s/conky/linear-cards.lua',\n" "$ROOT"
        ;;
      *"fetch_linear_tasks.py"*) ;;
      *"fetch_codex_usage.py"*) ;;
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
    done < <(xrandr --listmonitors 2>> "$LOG_PATH" || true)

    if [[ "${#output_lines[@]}" -eq 0 || "$has_primary" -eq 1 ]]; then
      MONITOR_HAS_PRIMARY="$has_primary"
      break
    fi

    now="$SECONDS"
    if (( now >= deadline )); then
      log "xrandr reported monitors but no primary marker; using fallback primary index=$LINEAR_PRIMARY_MONITOR_INDEX"
      break
    fi

    sleep 1
  done
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
  linear_config="$GENERATED_DIR/linear-overlay-$index.conkyrc"
  codex_config="$GENERATED_DIR/codex-overlay-$index.conkyrc"

  generate_config "$BASE_CONFIG" "$linear_config" "$index" "$monitor_gap_x" "$linear_gap_y"
  generate_config "$CODEX_CONFIG" "$codex_config" "$index" "$monitor_gap_x" "$CODEX_GAP_Y"

  if [[ "$GENERATE_ONLY" -eq 0 ]]; then
    setsid conky -c "$linear_config" >> "$LOG_PATH" 2>&1 < /dev/null &
    log "launched monitor_index=$index width=$width gap_x=$monitor_gap_x gap_y=$linear_gap_y config=$linear_config pid=$!"
    setsid conky -c "$codex_config" >> "$LOG_PATH" 2>&1 < /dev/null &
    log "launched monitor_index=$index width=$width gap_x=$monitor_gap_x config=$codex_config pid=$!"
  else
    log "generated monitor_index=$index width=$width gap_x=$monitor_gap_x gap_y=$linear_gap_y config=$linear_config"
    log "generated monitor_index=$index width=$width gap_x=$monitor_gap_x config=$codex_config"
  fi
  index=$((index + 1))
done

if [[ "$index" -eq 0 ]]; then
  log "no monitors detected from xrandr; using base config"
  if [[ "$GENERATE_ONLY" -eq 0 ]]; then
    setsid conky -c "$BASE_CONFIG" >> "$LOG_PATH" 2>&1 < /dev/null &
    log "launched fallback config=$BASE_CONFIG pid=$!"
    setsid conky -c "$CODEX_CONFIG" >> "$LOG_PATH" 2>&1 < /dev/null &
    log "launched fallback config=$CODEX_CONFIG pid=$!"
  fi
fi

if [[ "$GENERATE_ONLY" -eq 1 ]]; then
  printf "Generated %s overlay config(s) in %s\n" "$index" "$GENERATED_DIR"
fi

log "finished; generated_configs=$index"

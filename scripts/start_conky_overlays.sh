#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BASE_CONFIG="$ROOT/conky/linear-overlay.conkyrc"
CODEX_CONFIG="$ROOT/conky/codex-overlay.conkyrc"
GENERATED_DIR="$ROOT/conky/generated"
LOG_PATH="$ROOT/conky-linear.log"
OVERLAY_WIDTH=1540
GAP_Y=34
GENERATE_ONLY=0

log() {
  printf '[%s] start_conky_overlays: %s\n' "$(date --iso-8601=seconds)" "$*" >> "$LOG_PATH"
}

if [[ "${1:-}" == "--generate-only" ]]; then
  GENERATE_ONLY=1
fi

mkdir -p "$GENERATED_DIR"

log "starting; root=$ROOT generate_only=$GENERATE_ONLY"

pkill -f "$GENERATED_DIR/linear-overlay-" 2>/dev/null || true
pkill -f "$GENERATED_DIR/codex-overlay-" 2>/dev/null || true
pkill -f "$BASE_CONFIG" 2>/dev/null || true
pkill -f "$CODEX_CONFIG" 2>/dev/null || true
log "stopped existing matching Conky processes"

generate_config() {
  local source_config="$1"
  local output_config="$2"
  local monitor_index="$3"
  local monitor_gap_x="$4"

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
        printf "  gap_y = %s,\n" "$GAP_Y"
        ;;
      "  lua_load = "*)
        printf "  lua_load = '%s/conky/linear-cards.lua',\n" "$ROOT"
        ;;
      *"fetch_linear_tasks.py"*)
        printf '${execi 180 %s/scripts/fetch_linear_tasks.py >/dev/null 2>>%s}\n' "$ROOT" "$LOG_PATH"
        ;;
      *"fetch_codex_usage.py"*)
        printf '${execi 300 %s/scripts/fetch_codex_usage.py >/dev/null 2>>%s}\n' "$ROOT" "$LOG_PATH"
        ;;
      *)
        printf "%s\n" "$config_line"
        ;;
    esac
  done < "$source_config" > "$output_config"
}

index=0
while IFS= read -r line; do
  if [[ ! "$line" =~ ^[[:space:]]*[0-9]+: ]]; then
    continue
  fi

  if [[ ! "$line" =~ ([0-9]+)\/[0-9]+x([0-9]+)\/[0-9]+\+(-?[0-9]+)\+(-?[0-9]+) ]]; then
    continue
  fi

  width="${BASH_REMATCH[1]}"
  monitor_gap_x=$(((width - OVERLAY_WIDTH) / 2))
  linear_config="$GENERATED_DIR/linear-overlay-$index.conkyrc"
  codex_config="$GENERATED_DIR/codex-overlay-$index.conkyrc"

  generate_config "$BASE_CONFIG" "$linear_config" "$index" "$monitor_gap_x"
  generate_config "$CODEX_CONFIG" "$codex_config" "$index" "$monitor_gap_x"

  if [[ "$GENERATE_ONLY" -eq 0 ]]; then
    conky -c "$linear_config" >> "$LOG_PATH" 2>&1 &
    log "launched monitor_index=$index width=$width gap_x=$monitor_gap_x config=$linear_config pid=$!"
    conky -c "$codex_config" >> "$LOG_PATH" 2>&1 &
    log "launched monitor_index=$index width=$width gap_x=$monitor_gap_x config=$codex_config pid=$!"
  else
    log "generated monitor_index=$index width=$width gap_x=$monitor_gap_x config=$linear_config"
    log "generated monitor_index=$index width=$width gap_x=$monitor_gap_x config=$codex_config"
  fi
  index=$((index + 1))
done < <(xrandr --listmonitors 2>> "$LOG_PATH")

if [[ "$index" -eq 0 ]]; then
  log "no monitors detected from xrandr; using base config"
  if [[ "$GENERATE_ONLY" -eq 0 ]]; then
    conky -c "$BASE_CONFIG" >> "$LOG_PATH" 2>&1 &
    log "launched fallback config=$BASE_CONFIG pid=$!"
    conky -c "$CODEX_CONFIG" >> "$LOG_PATH" 2>&1 &
    log "launched fallback config=$CODEX_CONFIG pid=$!"
  fi
fi

if [[ "$GENERATE_ONLY" -eq 1 ]]; then
  printf "Generated %s overlay config(s) in %s\n" "$index" "$GENERATED_DIR"
fi

log "finished; generated_configs=$index"

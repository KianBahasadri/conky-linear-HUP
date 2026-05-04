#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BASE_CONFIG="$ROOT/conky/linear-overlay.conkyrc"
GENERATED_DIR="$ROOT/conky/generated"
LOG_PATH="$ROOT/conky-linear.log"
CARD_WIDTH=1220
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
pkill -f "$BASE_CONFIG" 2>/dev/null || true
log "stopped existing matching Conky processes"

index=0
while IFS= read -r line; do
  if [[ ! "$line" =~ ^[[:space:]]*[0-9]+: ]]; then
    continue
  fi

  if [[ ! "$line" =~ ([0-9]+)\/[0-9]+x([0-9]+)\/[0-9]+\+(-?[0-9]+)\+(-?[0-9]+) ]]; then
    continue
  fi

  width="${BASH_REMATCH[1]}"
  monitor_gap_x=$(((width - CARD_WIDTH) / 2))
  config="$GENERATED_DIR/linear-overlay-$index.conkyrc"

  while IFS= read -r config_line; do
    case "$config_line" in
      "  alignment = "*)
        printf "%s\n" "$config_line"
        printf "  xinerama_head = %s,\n" "$index"
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
      *)
        printf "%s\n" "$config_line"
        ;;
    esac
  done < "$BASE_CONFIG" > "$config"

  if [[ "$GENERATE_ONLY" -eq 0 ]]; then
    conky -c "$config" >> "$LOG_PATH" 2>&1 &
    log "launched monitor_index=$index width=$width gap_x=$monitor_gap_x config=$config pid=$!"
  else
    log "generated monitor_index=$index width=$width gap_x=$monitor_gap_x config=$config"
  fi
  index=$((index + 1))
done < <(xrandr --listmonitors 2>> "$LOG_PATH")

if [[ "$index" -eq 0 ]]; then
  log "no monitors detected from xrandr; using base config"
  if [[ "$GENERATE_ONLY" -eq 0 ]]; then
    conky -c "$BASE_CONFIG" >> "$LOG_PATH" 2>&1 &
    log "launched fallback config=$BASE_CONFIG pid=$!"
  fi
fi

if [[ "$GENERATE_ONLY" -eq 1 ]]; then
  printf "Generated %s overlay config(s) in %s\n" "$index" "$GENERATED_DIR"
fi

log "finished; generated_configs=$index"

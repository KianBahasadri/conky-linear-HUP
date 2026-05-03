#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BASE_CONFIG="$ROOT/conky/linear-overlay.conkyrc"
GENERATED_DIR="$ROOT/conky/generated"
CARD_WIDTH=1220
GAP_Y=34
GENERATE_ONLY=0

if [[ "${1:-}" == "--generate-only" ]]; then
  GENERATE_ONLY=1
fi

mkdir -p "$GENERATED_DIR"

pkill -f "$GENERATED_DIR/linear-overlay-" 2>/dev/null || true
pkill -f "$BASE_CONFIG" 2>/dev/null || true

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
        printf '${execi 180 %s/scripts/fetch_linear_tasks.py >/dev/null}\n' "$ROOT"
        ;;
      *)
        printf "%s\n" "$config_line"
        ;;
    esac
  done < "$BASE_CONFIG" > "$config"

  if [[ "$GENERATE_ONLY" -eq 0 ]]; then
    conky -c "$config" &
  fi
  index=$((index + 1))
done < <(xrandr --listmonitors)

if [[ "$index" -eq 0 ]]; then
  if [[ "$GENERATE_ONLY" -eq 0 ]]; then
    conky -c "$BASE_CONFIG" &
  fi
fi

if [[ "$GENERATE_ONLY" -eq 1 ]]; then
  printf "Generated %s overlay config(s) in %s\n" "$index" "$GENERATED_DIR"
fi

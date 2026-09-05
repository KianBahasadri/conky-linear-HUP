#!/usr/bin/env bash
set -euo pipefail
font_source="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../assets/fonts" && pwd)"
font_target="${XDG_DATA_HOME:-$HOME/.local/share}/fonts/conky-linear-HUP"
mkdir -p "$font_target"
font_changed=0
for font_file in "$font_source"/*.ttf; do
  font_destination="$font_target/${font_file##*/}"
  if ! cmp -s "$font_file" "$font_destination"; then
    cp -- "$font_file" "$font_destination"
    font_changed=1
  fi
done
font_config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/fontconfig/conf.d"
font_config_path="$font_config_dir/70-conky-plex.conf"
mkdir -p "$font_config_dir"
if ! cmp -s "$font_source/70-conky-plex.conf" "$font_config_path"; then
  cp -- "$font_source/70-conky-plex.conf" "$font_config_path"
  font_changed=1
fi
if (( font_changed )); then fc-cache "$font_target"; fi

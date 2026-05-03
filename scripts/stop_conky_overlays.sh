#!/usr/bin/env bash
set -euo pipefail

pkill -f '/home/kian/personal_media/Obsidian/summer_2026/conky/generated/linear-overlay-' 2>/dev/null || true
pkill -f '/home/kian/personal_media/Obsidian/summer_2026/conky/linear-overlay.conkyrc' 2>/dev/null || true

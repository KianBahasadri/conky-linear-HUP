#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

pkill -f "$ROOT/conky/generated/linear-overlay-" 2>/dev/null || true
pkill -f "$ROOT/conky/linear-overlay.conkyrc" 2>/dev/null || true

#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
ENV_PATH = ROOT / ".env"

FIVE_HOUR_WINDOW_SECONDS = 5 * 60 * 60
WEEKLY_WINDOW_SECONDS = 7 * 24 * 60 * 60


def load_env(path=ENV_PATH):
    if not Path(path).exists():
        return

    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def make_logger(log_path, source):
    """Return a log_event(message) bound to a log file and a source label."""

    def log_event(message):
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {source}: {message}\n")

    return log_event


def atomic_write_text(path, content):
    path = Path(path)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


def atomic_write_json(path, data):
    # ensure_ascii=False keeps characters like em dashes as UTF-8 instead of \u2014,
    # which the Conky Lua JSON string unescaper must otherwise decode.
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False))


def escape_tsv(value):
    return str(value).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_iso_epoch(value):
    if not value:
        return 0
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def usage_render_tsv(output):
    """The meta/account/bar TSV shared by the Codex and Claude usage fetchers."""
    lines = [
        "\t".join(
            [
                "meta",
                "ok",
                "1" if output.get("ok") else "0",
                "updatedAt",
                escape_tsv(output.get("updatedAt", "")),
                "error",
                escape_tsv(output.get("error", "")),
            ]
        )
    ]

    for account in output.get("accounts", []):
        lines.append(
            "\t".join(
                [
                    "account",
                    escape_tsv(account.get("label", "")),
                    escape_tsv(account.get("planType", "")),
                    "1" if account.get("isSelected") else "0",
                    "1" if account.get("ok") else "0",
                    escape_tsv(account.get("error", "")),
                    "1" if account.get("staleCache") else "0",
                ]
            )
        )

    for bar in output.get("bars", []):
        lines.append(
            "\t".join(
                [
                    "bar",
                    escape_tsv(bar.get("account", "")),
                    escape_tsv(bar.get("planType", "")),
                    "1" if bar.get("isSelected") else "0",
                    escape_tsv(bar.get("window", "")),
                    str(bar.get("usedPercent", 0)),
                    str(bar.get("remainingPercent", 0)),
                    escape_tsv(bar.get("resetsAt") or ""),
                    str(bar.get("resetAtEpoch", 0)),
                    str(bar.get("resetAfterSeconds", 0)),
                    str(bar.get("windowSeconds", 0)),
                ]
            )
        )

    return "\n".join(lines) + "\n"


def flatten_bars(accounts):
    bars = []
    for account in accounts:
        for window in account.get("windows", []):
            bars.append(
                {
                    "account": account.get("label", ""),
                    "planType": account.get("planType", ""),
                    "isSelected": account.get("isSelected", False),
                    "window": window.get("label", ""),
                    "usedPercent": window.get("usedPercent", 0),
                    "remainingPercent": window.get("remainingPercent", 0),
                    "resetsAt": window.get("resetsAt"),
                    "resetAtEpoch": window.get("resetAtEpoch", 0),
                    "resetAfterSeconds": window.get("resetAfterSeconds", 0),
                    "windowSeconds": window.get("windowSeconds", 0),
                    "ok": account.get("ok", False),
                }
            )
    return bars


def write_usage_outputs(output_path, render_path, output):
    atomic_write_json(output_path, output)
    atomic_write_text(render_path, usage_render_tsv(output))


# Must match conky/rate-limit-panel-renderer.lua.
RATE_LIMIT_PANEL_MIN_HEIGHT = 110
RATE_LIMIT_PANEL_ROW_GAP = 19
RATE_LIMIT_PANEL_DYNAMIC_PADDING = 30
RATE_LIMIT_PANEL_TOP_INSET = 12
RATE_LIMIT_PANEL_BOTTOM_INSET = 12
RATE_LIMIT_PANEL_WINDOW_FLOOR = 320
RATE_LIMIT_PANEL_RENDER_TSVS = (
    "codex-usage-render.tsv",
    "claude-usage-render.tsv",
    "cursor-usage-render.tsv",
    "gemini-usage-render.tsv",
    "grok-usage-render.tsv",
    "opencode-usage-render.tsv",
    "commandcode-usage-render.tsv",
)


def rate_limit_account_count_from_cache(cache_dir=CACHE_DIR):
    count = 0
    for name in RATE_LIMIT_PANEL_RENDER_TSVS:
        path = Path(cache_dir) / name
        if not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if line.startswith("account\t"):
                count += 1
    return count


def rate_limit_panel_window_height(account_count):
    """Return the Conky minimum_height needed for the account list.

    Must match the layout math in conky/rate-limit-panel-renderer.lua.
    """
    count = max(1, int(account_count or 0))
    panel = max(
        RATE_LIMIT_PANEL_MIN_HEIGHT,
        RATE_LIMIT_PANEL_DYNAMIC_PADDING + count * RATE_LIMIT_PANEL_ROW_GAP,
    )
    return max(
        RATE_LIMIT_PANEL_WINDOW_FLOOR,
        RATE_LIMIT_PANEL_TOP_INSET + panel + RATE_LIMIT_PANEL_BOTTOM_INSET,
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--print-rate-limit-panel-height":
        print(rate_limit_panel_window_height(rate_limit_account_count_from_cache()))
    else:
        print(
            "usage: fetch_common.py --print-rate-limit-panel-height",
            file=sys.stderr,
        )
        sys.exit(1)

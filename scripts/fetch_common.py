#!/usr/bin/env python3
import json
import os
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
    atomic_write_text(path, json.dumps(data, indent=2))


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

#!/usr/bin/env python3
import json
import os
import select
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
STATUSLINE_PATH = CACHE_DIR / "claude-statusline.json"
OUTPUT_PATH = CACHE_DIR / "claude-usage.json"
RENDER_PATH = CACHE_DIR / "claude-usage-render.tsv"
LOG_PATH = CACHE_DIR / "conky-codex.log"
FIVE_HOUR_WINDOW_SECONDS = common.FIVE_HOUR_WINDOW_SECONDS
WEEKLY_WINDOW_SECONDS = common.WEEKLY_WINDOW_SECONDS


log_event = common.make_logger(LOG_PATH, "fetch_claude_usage")
atomic_write_json = common.atomic_write_json
as_float = common.as_float
as_int = common.as_int


def read_stdin_json():
    if sys.stdin.isatty():
        return None

    ready, _, _ = select.select([sys.stdin], [], [], 0)
    if not ready:
        return None

    raw = sys.stdin.read().strip()
    if not raw:
        return None

    return json.loads(raw)


def read_cached_statusline():
    try:
        return json.loads(STATUSLINE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid Claude statusline cache: {error}") from error


def read_auth_status():
    try:
        completed = subprocess.run(
            ["claude", "auth", "status"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return {}

    if completed.returncode != 0:
        return {}

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {}


def normalize_window(label, raw_window, fetched_at):
    if not isinstance(raw_window, dict):
        return None

    used_percent = max(0.0, min(100.0, as_float(raw_window.get("used_percentage"))))
    reset_at = as_int(raw_window.get("resets_at"))
    if reset_at <= int(fetched_at.timestamp()):
        return None

    reset_after_seconds = max(0, reset_at - int(fetched_at.timestamp())) if reset_at else 0
    window_seconds = WEEKLY_WINDOW_SECONDS if label == "weekly" else FIVE_HOUR_WINDOW_SECONDS
    resets_at_iso = datetime.fromtimestamp(reset_at, tz=timezone.utc).isoformat() if reset_at else None

    return {
        "label": label,
        "usedPercent": round(used_percent, 1),
        "remainingPercent": max(0, round(100 - used_percent, 1)),
        "resetsAt": resets_at_iso,
        "resetAtEpoch": reset_at,
        "resetAfterSeconds": reset_after_seconds,
        "windowSeconds": window_seconds,
    }


def normalize_usage(statusline):
    fetched_at = datetime.now(timezone.utc)
    auth_status = read_auth_status()
    plan_type = os.environ.get("CLAUDE_PLAN_TYPE", "").strip() or auth_status.get("subscriptionType", "")
    label = os.environ.get("CLAUDE_USAGE_LABEL", "").strip() or "claude"
    rate_limits = statusline.get("rate_limits") if isinstance(statusline, dict) else None
    windows = []

    if isinstance(rate_limits, dict):
        five_hour = normalize_window("5h", rate_limits.get("five_hour"), fetched_at)
        weekly = normalize_window("weekly", rate_limits.get("seven_day"), fetched_at)
        if five_hour:
            windows.append(five_hour)
        if weekly:
            windows.append(weekly)

    if not windows:
        message = "Waiting for Claude Code statusline rate_limits after the next Claude response."
        return {
            "updatedAt": fetched_at.isoformat(),
            "provider": "Claude",
            "ok": False,
            "error": message,
            "accounts": [
                {
                    "ok": False,
                    "label": label,
                    "email": auth_status.get("email", ""),
                    "planType": plan_type,
                    "isSelected": True,
                    "error": message,
                    "windows": [],
                }
            ],
            "bars": [],
        }

    account = {
        "ok": True,
        "label": label,
        "email": auth_status.get("email", ""),
        "planType": plan_type,
        "isSelected": True,
        "windows": windows,
    }
    return {
        "updatedAt": fetched_at.isoformat(),
        "provider": "Claude",
        "ok": True,
        "accounts": [account],
        "bars": [
            {
                "account": label,
                "planType": plan_type,
                "isSelected": True,
                "window": window["label"],
                "usedPercent": window["usedPercent"],
                "remainingPercent": window["remainingPercent"],
                "resetsAt": window["resetsAt"],
                "resetAtEpoch": window["resetAtEpoch"],
                "resetAfterSeconds": window["resetAfterSeconds"],
                "windowSeconds": window["windowSeconds"],
                "ok": True,
            }
            for window in windows
        ],
    }


def format_statusline(output):
    if not output.get("ok"):
        return "Claude"

    windows = {}
    for bar in output.get("bars", []):
        windows[bar.get("window", "")] = bar

    labels = []
    if "5h" in windows:
        labels.append(f"5h {windows['5h'].get('usedPercent', 0):.0f}%")
    if "weekly" in windows:
        labels.append(f"7d {windows['weekly'].get('usedPercent', 0):.0f}%")

    return "Claude " + " ".join(labels) if labels else "Claude"


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()

    try:
        statusline = read_stdin_json()
        from_statusline = statusline is not None
        if statusline:
            atomic_write_json(STATUSLINE_PATH, statusline)
        else:
            statusline = read_cached_statusline()

        if not statusline:
            raise RuntimeError("No Claude statusline cache found. Configure Claude Code statusLine to run this script.")

        output = normalize_usage(statusline)
        common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
        log_event(f"completed fetch ok={output.get('ok')} wrote={OUTPUT_PATH.name}")
        print(format_statusline(output) if from_statusline else json.dumps(output, indent=2))
        return 0 if output.get("ok") else 1
    except Exception as error:
        message = f"Claude usage fetch failed: {error}"
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "Claude",
            "ok": False,
            "error": message,
            "accounts": [],
            "bars": [],
        }
        common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
        log_event(f"error: {message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

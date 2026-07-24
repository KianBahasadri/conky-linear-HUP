#!/usr/bin/env python3
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "opencode-usage.json"
RENDER_PATH = CACHE_DIR / "opencode-usage-render.tsv"
LOG_PATH = CACHE_DIR / "conky-rate-limit-panel.log"
DEFAULT_AUTH_NAME = "auth.json"
OPENCODE_HOME = Path.home() / ".local" / "share" / "opencode"
OPENCODE_DB = OPENCODE_HOME / "opencode.db"

# OpenCode Go subscription limits (dollar values)
FIVE_HOUR_LIMIT_USD = 12.0
WEEKLY_LIMIT_USD = 30.0
MONTHLY_LIMIT_USD = 60.0

FIVE_HOUR_WINDOW_SECONDS = common.FIVE_HOUR_WINDOW_SECONDS
WEEKLY_WINDOW_SECONDS = common.WEEKLY_WINDOW_SECONDS
MONTHLY_WINDOW_SECONDS = 31 * 24 * 60 * 60


log_event = common.make_logger(LOG_PATH, "fetch_opencode_usage")
atomic_write_json = common.atomic_write_json
as_float = common.as_float
as_int = common.as_int
flatten_bars = common.flatten_bars


def opencode_home():
    return Path(os.environ.get("OPENCODE_HOME", Path.home() / ".local" / "share" / "opencode")).expanduser()


def opencode_db_path():
    return Path(os.environ.get("OPENCODE_DB", opencode_home() / "opencode.db")).expanduser()


def default_auth_path():
    return opencode_home() / DEFAULT_AUTH_NAME


def configured_auth_path():
    configured = os.environ.get("OPENCODE_AUTH_PATH", "").strip()
    return Path(configured).expanduser() if configured else None


def has_go_key(path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        go_auth = raw.get("opencode-go")
        return bool(go_auth and go_auth.get("type") == "api" and go_auth.get("key"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False


def discover_auth_files():
    configured = configured_auth_path()
    if configured:
        return [(auth_label(configured), configured, is_selected_auth(configured))]

    home = opencode_home()
    suffixed_paths = sorted(
        path for path in home.glob(f"{DEFAULT_AUTH_NAME}.*") if path.is_file() and has_go_key(path)
    )
    if suffixed_paths:
        return [(auth_label(path), path, is_selected_auth(path)) for path in suffixed_paths]

    default_path = default_auth_path()
    return [(auth_label(default_path), default_path, is_selected_auth(default_path))]


def is_selected_auth(path):
    try:
        return default_auth_path().resolve() == path.resolve()
    except OSError:
        return default_auth_path() == path


def auth_label(path):
    name = path.name
    prefix = f"{DEFAULT_AUTH_NAME}."
    if name.startswith(prefix) and len(name) > len(prefix):
        return name[len(prefix):]
    if name == DEFAULT_AUTH_NAME:
        return "default"
    return path.stem.lstrip(".") or name


def read_auth(label, path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"missing OpenCode auth file: {path}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid OpenCode auth JSON: {error}") from error

    go_auth = raw.get("opencode-go")
    if not go_auth or go_auth.get("type") != "api" or not go_auth.get("key"):
        raise RuntimeError(f"auth file has no opencode-go API key: {path}")

    return {
        "label": label,
        "path": path,
        "api_key": go_auth["key"],
    }


def compute_usage_windows(db_path, now_ms):
    """Query the opencode SQLite database for Go usage in each window.

    Returns total cost and the oldest session time for each sliding window.
    The reset time is when that oldest session falls outside the window.
    """
    five_hours_ago_ms = now_ms - (FIVE_HOUR_WINDOW_SECONDS * 1000)
    week_ago_ms = now_ms - (WEEKLY_WINDOW_SECONDS * 1000)
    month_ago_ms = now_ms - (MONTHLY_WINDOW_SECONDS * 1000)

    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        row = connection.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN time_created > ? THEN cost END), 0),
              COALESCE(SUM(CASE WHEN time_created > ? THEN cost END), 0),
              COALESCE(SUM(CASE WHEN time_created > ? THEN cost END), 0),
              COALESCE(MIN(CASE WHEN time_created > ? THEN time_created END), 0),
              COALESCE(MIN(CASE WHEN time_created > ? THEN time_created END), 0),
              COALESCE(MIN(CASE WHEN time_created > ? THEN time_created END), 0)
            FROM session
            WHERE model LIKE '%opencode-go%'
            """,
            (
                five_hours_ago_ms,
                week_ago_ms,
                month_ago_ms,
                five_hours_ago_ms,
                week_ago_ms,
                month_ago_ms,
            ),
        ).fetchone()
    finally:
        connection.close()

    return {
        "5h": {"cost": row[0], "oldest_session_ms": row[3]},
        "weekly": {"cost": row[1], "oldest_session_ms": row[4]},
        "monthly": {"cost": row[2], "oldest_session_ms": row[5]},
    }


def normalize_window(label, cost_usd, limit_usd, window_seconds, oldest_session_ms):
    used_percent = min(100.0, (cost_usd / limit_usd) * 100) if limit_usd > 0 else 0.0

    now_epoch = int(datetime.now(timezone.utc).timestamp())
    reset_at_epoch = 0
    if oldest_session_ms > 0:
        reset_at_epoch = int(oldest_session_ms / 1000) + window_seconds
    reset_after_seconds = max(0, reset_at_epoch - now_epoch) if reset_at_epoch > 0 else 0
    resets_at_iso = (
        datetime.fromtimestamp(reset_at_epoch, tz=timezone.utc).isoformat()
        if reset_at_epoch > 0
        else None
    )

    return {
        "label": label,
        "usedPercent": round(used_percent, 1),
        "remainingPercent": max(0, round(100.0 - used_percent, 1)),
        "resetsAt": resets_at_iso,
        "resetAtEpoch": reset_at_epoch,
        "resetAfterSeconds": reset_after_seconds,
        "windowSeconds": window_seconds,
        "costUsd": round(cost_usd, 4),
        "limitUsd": limit_usd,
    }


def normalize_usage(auth, windows, is_selected):
    return {
        "ok": True,
        "label": auth["label"],
        "email": "",
        "accountId": "",
        "planType": "go",
        "isSelected": is_selected,
        "windows": [
            normalize_window(
                "5h", windows["5h"]["cost"], FIVE_HOUR_LIMIT_USD,
                FIVE_HOUR_WINDOW_SECONDS, windows["5h"]["oldest_session_ms"],
            ),
            normalize_window(
                "weekly", windows["weekly"]["cost"], WEEKLY_LIMIT_USD,
                WEEKLY_WINDOW_SECONDS, windows["weekly"]["oldest_session_ms"],
            ),
            normalize_window(
                "monthly", windows["monthly"]["cost"], MONTHLY_LIMIT_USD,
                MONTHLY_WINDOW_SECONDS, windows["monthly"]["oldest_session_ms"],
            ),
        ],
    }


def normalize_error(label, message, is_selected=False):
    return {
        "ok": False,
        "label": label,
        "error": message,
        "isSelected": is_selected,
        "windows": [],
    }


def fetch_account(label, path, is_selected):
    try:
        auth = read_auth(label, path)
        db_path = opencode_db_path()
        if not db_path.is_file():
            return normalize_error(label, f"OpenCode database not found: {db_path}", is_selected)

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        windows = compute_usage_windows(db_path, now_ms)
        account = normalize_usage(auth, windows, is_selected)
        log_event(
            f"account={label} completed plan=go "
            f"5h=${windows['5h']['cost']:.2f} weekly=${windows['weekly']['cost']:.2f} monthly=${windows['monthly']['cost']:.2f}"
        )
        return account
    except Exception as error:
        return normalize_error(label, str(error), is_selected)


def write_error(message):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "OpenCode",
        "ok": False,
        "error": message,
        "accounts": [],
        "bars": [],
    }
    common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
    log_event(f"error: {message}")


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()
    auth_files = discover_auth_files()
    labels = ",".join(label for label, _, _ in auth_files)
    log_event(f"starting OpenCode Go usage fetch accounts={labels or 'none'}")

    try:
        accounts = [fetch_account(label, path, is_selected) for label, path, is_selected in auth_files]
        ok_count = sum(1 for account in accounts if account.get("ok"))
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "OpenCode",
            "ok": ok_count > 0,
            "accounts": accounts,
            "bars": flatten_bars(accounts),
        }
        common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
        log_event(f"completed fetch accounts={len(accounts)} ok={ok_count} wrote={OUTPUT_PATH.name}")
        print(json.dumps(output, indent=2))
        return 0 if ok_count > 0 else 1
    except Exception as error:
        write_error(f"OpenCode Go usage fetch failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

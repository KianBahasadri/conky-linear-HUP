#!/usr/bin/env python3
import json
import os
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "opencode-usage.json"
RENDER_PATH = CACHE_DIR / "opencode-usage-render.tsv"
LOG_PATH = CACHE_DIR / "conky-rate-limit-panel.log"
USAGE_CACHE_PATH = CACHE_DIR / "opencode-usage-cache.json"

# The Go client reads this inference route with the workspace's API key.
# https://github.com/anomalyco/opencode/blob/dev/packages/core/src/usage-limits.ts
USAGE_URL = "https://opencode.ai/zen/go/v1/usage"
API_KEY_ENV = "OPENCODE_API_KEY"
WORKSPACE_ID_ENV = "OPENCODE_WORKSPACE_ID"

# resetsAt is absolute. The route does not return the window length the pace
# tick needs, so these match the published 5-hour, weekly, and monthly meters.
WINDOWS = (
    ("rolling", "5h", common.FIVE_HOUR_WINDOW_SECONDS),
    ("weekly", "weekly", common.WEEKLY_WINDOW_SECONDS),
    ("monthly", "monthly", 31 * 24 * 60 * 60),
)


log_event = common.make_logger(LOG_PATH, "fetch_opencode_usage")
flatten_bars = common.flatten_bars


def opencode_data_dir():
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return base / "opencode"


def _credential_rows(data_dir):
    db_path = data_dir / "opencode.db"
    if not db_path.is_file():
        return []
    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error:
        return []
    try:
        return connection.execute(
            "SELECT integration_id, value FROM credential WHERE active = 1"
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        connection.close()


def _legacy_api_key(data_dir):
    try:
        payload = json.loads((data_dir / "auth.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    entry = payload.get("opencode-go") if isinstance(payload, dict) else None
    if (
        isinstance(entry, dict)
        and entry.get("type") == "api"
        and isinstance(entry.get("key"), str)
        and entry["key"].strip()
    ):
        return entry["key"].strip()
    return None


def stored_credentials(data_dir=None):
    """Return the active Go API key and signed-in workspace id, if saved."""
    data_dir = data_dir or opencode_data_dir()
    key = None
    workspace = None
    for integration_id, raw in _credential_rows(data_dir):
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(value, dict):
            continue
        if (
            integration_id == "opencode-go"
            and value.get("type") == "key"
            and isinstance(value.get("key"), str)
            and value["key"].strip()
        ):
            key = value["key"].strip()
        elif integration_id == "opencode" and isinstance(value.get("metadata"), dict):
            org_id = value["metadata"].get("orgID")
            if isinstance(org_id, str) and org_id.strip():
                workspace = org_id.strip()
    if not key:
        key = _legacy_api_key(data_dir)
    return key, workspace


def resolve_auth(data_dir=None):
    key = os.environ.get(API_KEY_ENV, "").strip()
    workspace = os.environ.get(WORKSPACE_ID_ENV, "").strip()
    if not key or not workspace:
        stored_key, stored_workspace = stored_credentials(data_dir)
        key = key or stored_key
        workspace = workspace or stored_workspace
    if not key:
        raise RuntimeError(
            f"{API_KEY_ENV} is unset and OpenCode has no active Go API key"
        )
    if not workspace:
        raise RuntimeError(
            f"{WORKSPACE_ID_ENV} is unset and OpenCode has no signed-in workspace"
        )
    return key, workspace


def _parse_reset(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_usage(payload, now_epoch=None):
    """Turn the Go usage meters into the panel's 5h, weekly, and monthly windows."""
    now_epoch = int(now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp())
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        raise RuntimeError("OpenCode Go usage response is missing usage")

    windows = []
    for source, label, window_seconds in WINDOWS:
        meter = usage.get(source)
        if not isinstance(meter, dict):
            raise RuntimeError(f"OpenCode Go usage is missing the {source} meter")
        percent = meter.get("percent")
        if isinstance(percent, bool) or not isinstance(percent, (int, float)):
            raise RuntimeError(f"OpenCode Go {source} usage percent is invalid")
        used = max(0.0, min(100.0, float(percent)))
        if meter.get("status") == "rate-limited":
            used = 100.0
        reset_at = _parse_reset(meter.get("resetsAt"))
        reset_epoch = int(reset_at.timestamp()) if reset_at else 0
        remaining = max(0, reset_epoch - now_epoch) if reset_epoch else 0
        windows.append(
            {
                "label": label,
                "usedPercent": round(used, 1),
                "remainingPercent": round(100.0 - used, 1),
                "resetsAt": reset_at.isoformat() if reset_at else None,
                "resetAtEpoch": reset_epoch,
                "resetAfterSeconds": remaining,
                "windowSeconds": window_seconds,
            }
        )
    return windows


def _http_error_message(error):
    message = f"OpenCode Go usage returned HTTP {error.code}"
    try:
        payload = json.loads(error.read().decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError, UnicodeError):
        payload = None
    finally:
        error.close()
    if isinstance(payload, dict):
        inner = payload.get("error")
        if isinstance(inner, dict) and isinstance(inner.get("message"), str) and inner["message"].strip():
            message = inner["message"].strip()
    return message


def fetch_usage(api_key, workspace_id, now_epoch=None):
    request = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "opencode",
            "x-opencode-org-id": workspace_id,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise RuntimeError(_http_error_message(error)) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"OpenCode Go usage request failed: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError("OpenCode Go usage response was not JSON") from error
    return parse_usage(payload, now_epoch=now_epoch)


def save_usage_cache(windows, workspace_id):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        common.atomic_write_json(
            USAGE_CACHE_PATH,
            {
                "fetched_at": int(datetime.now(timezone.utc).timestamp()),
                "workspace_id": workspace_id,
                "windows": windows,
            },
        )
    except OSError:
        pass


def load_usage_cache(workspace_id):
    try:
        raw = json.loads(USAGE_CACHE_PATH.read_text(encoding="utf-8"))
        if raw.get("workspace_id") != workspace_id:
            return None
        windows = raw.get("windows")
        if isinstance(windows, list) and len(windows) == 3:
            return windows
    except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError, UnicodeError):
        pass
    return None


def account_payload(label, windows, stale=False, error="", ok=True):
    account = {
        "ok": ok,
        "label": label,
        "email": "",
        "accountId": "",
        "planType": "go",
        "isSelected": True,
        "windows": windows,
        "staleCache": stale,
    }
    if error:
        account["error"] = error
    return account


def empty_usage_windows():
    """Placeholder 5h/weekly/monthly bars so the row stays visible on hard failure."""
    return [
        {
            "label": label,
            "usedPercent": 0.0,
            "remainingPercent": 100.0,
            "resetsAt": None,
            "resetAtEpoch": 0,
            "resetAfterSeconds": 0,
            "windowSeconds": window_seconds,
        }
        for _source, label, window_seconds in WINDOWS
    ]


def write_error(message, label="default"):
    account = account_payload(
        label,
        empty_usage_windows(),
        stale=True,
        error=message,
        ok=False,
    )
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "OpenCode",
        "ok": False,
        "error": message,
        "accounts": [account],
        "bars": flatten_bars([account]),
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
    log_event(f"error: {message}")


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()
    label = os.environ.get("OPENCODE_USAGE_LABEL", "default").strip() or "default"

    try:
        api_key, workspace_id = resolve_auth()
        windows = fetch_usage(api_key, workspace_id)
        save_usage_cache(windows, workspace_id)
        account = account_payload(label, windows)
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "OpenCode",
            "ok": True,
            "accounts": [account],
            "bars": flatten_bars([account]),
        }
        common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
        log_event(f"completed usage fetch account={label} wrote={OUTPUT_PATH.name}")
        print(json.dumps(output, indent=2))
        return 0
    except Exception as error:
        log_event(f"usage fetch failed ({error})")
        try:
            _api_key, workspace_id = resolve_auth()
        except RuntimeError:
            workspace_id = ""
        cached_windows = load_usage_cache(workspace_id) if workspace_id else None
        if cached_windows:
            message = f"using stale usage cache after {error}"
            account = account_payload(label, cached_windows, stale=True, error=message)
            output = {
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "provider": "OpenCode",
                "ok": True,
                "accounts": [account],
                "bars": flatten_bars([account]),
            }
            common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
            log_event(f"using stale usage cache for account={label}")
            print(json.dumps(output, indent=2))
            return 0

        write_error(f"OpenCode Go usage fetch failed: {error}", label=label)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "cursor-usage.json"
RENDER_PATH = CACHE_DIR / "cursor-usage-render.tsv"
LOG_PATH = CACHE_DIR / "conky-rate-limit-panel.log"
DEFAULT_AUTH_NAME = "auth.json"
API_BASE_URL = "https://api2.cursor.sh/aiserver.v1.DashboardService"
USER_AGENT = "cursor/3.7.21"
MONTHLY_WINDOW_SECONDS = 31 * 24 * 60 * 60


log_event = common.make_logger(LOG_PATH, "fetch_cursor_usage")
as_int = common.as_int
flatten_bars = common.flatten_bars


def cursor_home():
    return Path(os.environ.get("CURSOR_HOME", Path.home() / ".config" / "cursor")).expanduser()


def default_auth_path():
    return cursor_home() / DEFAULT_AUTH_NAME


def configured_auth_path():
    configured = os.environ.get("CURSOR_AUTH_PATH", "").strip()
    return Path(configured).expanduser() if configured else None


def discover_auth_files():
    configured = configured_auth_path()
    if configured:
        return [(auth_label(configured), configured, is_selected_auth(configured))]

    default_path = default_auth_path()
    suffixed_paths = sorted(path for path in default_path.parent.glob(f"{DEFAULT_AUTH_NAME}.*") if path.is_file())
    if suffixed_paths:
        return [(auth_label(path), path, is_selected_auth(path)) for path in suffixed_paths]

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
    if name.endswith(".json"):
        return name[:-5].lstrip(".") or path.stem
    return path.stem.lstrip(".") or name


def read_auth(label, path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"missing Cursor auth file: {path}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid Cursor auth JSON: {error}") from error

    access_token = raw.get("accessToken", "")
    if not access_token:
        raise RuntimeError(f"auth file has no accessToken: {path}")

    return {
        "label": label,
        "path": path,
        "access_token": access_token,
        "refresh_token": raw.get("refreshToken", ""),
    }


def cursor_request(auth, method):
    body = b"{}"
    request = urllib.request.Request(f"{API_BASE_URL}/{method}", data=body, method="POST")
    request.add_header("Authorization", f"Bearer {auth['access_token']}")
    request.add_header("Content-Type", "application/json")
    request.add_header("Connect-Protocol-Version", "1")
    request.add_header("User-Agent", USER_AGENT)

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body_text = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError:
            payload = {"error": body_text[:500]}
        return error.code, payload
    except urllib.error.URLError as error:
        raise RuntimeError(f"Cursor {method} request failed: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Cursor {method} response was not JSON: {error}") from error


def optional_metadata(auth, method):
    status, payload = cursor_request(auth, method)
    if status == 200 and isinstance(payload, dict):
        return payload
    log_event(f"account={auth['label']} {method} returned HTTP {status}")
    return {}


def epoch_millis(value):
    epoch = as_int(value)
    if epoch > 10**11:
        return epoch // 1000
    return epoch


def normalize_cursor_window(label, used_percent, spend_cents, limit_cents, cycle_start, cycle_end, fetched_at):
    now = int(fetched_at.timestamp())
    if used_percent is None and limit_cents > 0:
        used_percent = (spend_cents / limit_cents) * 100
    if used_percent is None:
        used_percent = 0

    used_percent = max(0.0, min(100.0, float(used_percent)))
    window_seconds = cycle_end - cycle_start if cycle_start > 0 and cycle_end > cycle_start else MONTHLY_WINDOW_SECONDS
    reset_after_seconds = max(0, cycle_end - now) if cycle_end > 0 else 0
    resets_at = datetime.fromtimestamp(cycle_end, tz=timezone.utc).isoformat() if cycle_end > 0 else None

    return {
        "label": label,
        "usedPercent": round(used_percent, 1),
        "remainingPercent": max(0, round(100 - used_percent, 1)),
        "resetsAt": resets_at,
        "resetAtEpoch": cycle_end,
        "resetAfterSeconds": reset_after_seconds,
        "windowSeconds": window_seconds,
        "spentCents": spend_cents,
        "limitCents": limit_cents,
    }


def normalize_usage(auth, usage, me, plan_info, is_selected):
    fetched_at = datetime.now(timezone.utc)
    usage = usage if isinstance(usage, dict) else {}
    plan_usage = usage.get("planUsage") if isinstance(usage, dict) else {}
    plan_usage = plan_usage if isinstance(plan_usage, dict) else {}
    plan = plan_info.get("planInfo") if isinstance(plan_info, dict) else {}
    plan = plan if isinstance(plan, dict) else {}
    cycle_start = epoch_millis(usage.get("billingCycleStart"))
    cycle_end = epoch_millis(usage.get("billingCycleEnd")) or epoch_millis(plan.get("billingCycleEnd"))
    windows = [
        normalize_cursor_window(
            "auto",
            plan_usage.get("autoPercentUsed"),
            as_int(plan_usage.get("autoSpend")),
            as_int(plan_usage.get("autoLimit")),
            cycle_start,
            cycle_end,
            fetched_at,
        ),
        normalize_cursor_window(
            "api",
            plan_usage.get("apiPercentUsed"),
            as_int(plan_usage.get("apiSpend")),
            as_int(plan_usage.get("apiLimit")),
            cycle_start,
            cycle_end,
            fetched_at,
        ),
    ]

    account = {
        "ok": bool(windows),
        "label": auth["label"],
        "email": me.get("email", "") if isinstance(me, dict) else "",
        "accountId": str(me.get("userId", "")) if isinstance(me, dict) else "",
        "planType": plan.get("planName", ""),
        "isSelected": is_selected,
        "windows": windows,
    }
    if usage.get("displayMessage"):
        account["usageMessage"] = usage["displayMessage"]
    if not windows:
        account["error"] = "Cursor usage API returned no monthly usage buckets."
    return account


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
        status, usage = cursor_request(auth, "GetCurrentPeriodUsage")
        if status != 200:
            print(json.dumps({label: usage}, indent=2), file=sys.stderr)
            return normalize_error(label, f"Cursor usage API error: HTTP {status}", is_selected)

        me = optional_metadata(auth, "GetMe")
        plan_info = optional_metadata(auth, "GetPlanInfo")
        account = normalize_usage(auth, usage, me, plan_info, is_selected)
        log_event(
            f"account={label} completed plan={account['planType'] or 'unknown'} "
            f"windows={len(account['windows'])}"
        )
        return account
    except Exception as error:
        return normalize_error(label, str(error), is_selected)


def write_error(message):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "Cursor",
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
    log_event(f"starting Cursor usage fetch accounts={labels or 'none'}")

    try:
        accounts = [fetch_account(label, path, is_selected) for label, path, is_selected in auth_files]
        ok_count = sum(1 for account in accounts if account.get("ok"))
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "Cursor",
            "ok": ok_count > 0,
            "accounts": accounts,
            "bars": flatten_bars(accounts),
        }
        common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
        log_event(f"completed fetch accounts={len(accounts)} ok={ok_count} wrote={OUTPUT_PATH.name}")
        print(json.dumps(output, indent=2))
        return 0 if ok_count > 0 else 1
    except Exception as error:
        write_error(f"Cursor usage fetch failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

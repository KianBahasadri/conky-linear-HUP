#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "claude-usage.json"
RENDER_PATH = CACHE_DIR / "claude-usage-render.tsv"
LOG_PATH = CACHE_DIR / "conky-codex.log"
DEFAULT_CREDENTIALS_NAME = ".credentials.json"
CREDENTIALS_PREFIX = ".credentials.json."
USAGE_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
SYSTEM_PROMPT = "You are Claude Code, Anthropic's official CLI for Claude."
FIVE_HOUR_WINDOW_SECONDS = common.FIVE_HOUR_WINDOW_SECONDS
WEEKLY_WINDOW_SECONDS = common.WEEKLY_WINDOW_SECONDS


log_event = common.make_logger(LOG_PATH, "fetch_claude_usage")
atomic_write_json = common.atomic_write_json
as_float = common.as_float
as_int = common.as_int


def claude_home():
    return Path(os.environ.get("CLAUDE_HOME", Path.home() / ".claude")).expanduser()


def default_credentials_path():
    return claude_home() / DEFAULT_CREDENTIALS_NAME


def usage_cache_ttl_seconds():
    return as_int(os.environ.get("CLAUDE_USAGE_TTL"), 300)


def configured_credentials_path():
    configured = os.environ.get("CLAUDE_CREDENTIALS_PATH", "").strip()
    if not configured:
        configured = os.environ.get("CLAUDE_AUTH_PATH", "").strip()
    return Path(configured).expanduser() if configured else None


def discover_credentials():
    configured_path = configured_credentials_path()
    if configured_path:
        return [(configured_label(configured_path), configured_path, is_selected_credentials(configured_path))]

    suffixed_paths = sorted(path for path in claude_home().glob(f"{DEFAULT_CREDENTIALS_NAME}.*") if path.is_file())
    if suffixed_paths:
        return [(credentials_label(path), path, is_selected_credentials(path)) for path in suffixed_paths]

    path = default_credentials_path()
    return [(configured_label(path), path, is_selected_credentials(path))]


def configured_label(path):
    return os.environ.get("CLAUDE_USAGE_LABEL", "").strip() or credentials_label(path)


def credentials_label(path):
    name = path.name
    if name.startswith(CREDENTIALS_PREFIX) and len(name) > len(CREDENTIALS_PREFIX):
        return name[len(CREDENTIALS_PREFIX):]
    if name == DEFAULT_CREDENTIALS_NAME:
        return "default"
    if name.endswith(".json"):
        return name[:-5].lstrip(".") or path.stem
    return path.stem.lstrip(".") or name


def is_selected_credentials(path):
    try:
        return default_credentials_path().resolve() == path.resolve()
    except OSError:
        return default_credentials_path() == path


def read_credentials(label, path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"missing Claude credentials file: {path}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid Claude credentials JSON: {error}") from error

    oauth = raw.get("claudeAiOauth") or {}
    access_token = oauth.get("accessToken", "")
    if not access_token:
        raise RuntimeError(f"credentials file has no claudeAiOauth.accessToken: {path}")

    return {
        "label": label,
        "path": path,
        "access_token": access_token,
        "plan_type": os.environ.get("CLAUDE_PLAN_TYPE", "").strip()
        or oauth.get("subscriptionType", "")
        or oauth.get("rateLimitTier", ""),
        "email": "",
    }


def optional_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def optional_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def quota_request(auth):
    model = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", DEFAULT_MODEL)
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 1,
            "system": [{"type": "text", "text": SYSTEM_PROMPT}],
            "messages": [{"role": "user", "content": "quota"}],
        }
    ).encode("utf-8")
    request = urllib.request.Request(USAGE_URL, data=body, method="POST")
    request.add_header("authorization", f"Bearer {auth['access_token']}")
    request.add_header("anthropic-version", "2023-06-01")
    request.add_header("anthropic-beta", "oauth-2025-04-20")
    request.add_header("content-type", "application/json")
    request.add_header("user-agent", "claude-cli/2.1.162 (external, cli)")

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.headers, ""
    except urllib.error.HTTPError as error:
        body_text = error.read().decode("utf-8", errors="replace")
        return error.code, error.headers, body_text[:500]
    except urllib.error.URLError as error:
        raise RuntimeError(f"Claude usage API request failed: {error.reason}") from error


def usage_from_headers(headers):
    usage = {}
    for window, key in (("5h", "five_hour"), ("7d", "seven_day")):
        utilization = optional_float(headers.get(f"anthropic-ratelimit-unified-{window}-utilization"))
        reset_at = optional_int(headers.get(f"anthropic-ratelimit-unified-{window}-reset"))
        if utilization is None:
            continue
        usage[key] = {
            "used_percentage": max(0.0, min(100.0, utilization * 100)),
            "resets_at": reset_at,
        }
    return usage


def fetch_quota_usage(auth):
    status, headers, body_text = quota_request(auth)
    usage = usage_from_headers(headers)
    if usage:
        return usage, status

    detail = f": {body_text}" if body_text else ""
    raise RuntimeError(f"Claude usage API returned no rate-limit headers: HTTP {status}{detail}")


def safe_cache_label(label):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("._")
    return safe or "default"


def account_cache_path(label):
    return CACHE_DIR / f"claude-usage-cache-{safe_cache_label(label)}.json"


def read_account_cache(label):
    try:
        return json.loads(account_cache_path(label).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_account_cache(label, usage, status):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(usage)
    payload["fetched_at"] = int(datetime.now(timezone.utc).timestamp())
    payload["source"] = "api"
    payload["status"] = status
    atomic_write_json(account_cache_path(label), payload)


def normalize_window(label, raw_window, fetched_at):
    if not isinstance(raw_window, dict):
        return None

    used_percent = max(0.0, min(100.0, as_float(raw_window.get("used_percentage"))))
    reset_at = as_int(raw_window.get("resets_at"))
    if reset_at <= int(fetched_at.timestamp()):
        return None

    reset_after_seconds = max(0, reset_at - int(fetched_at.timestamp()))
    window_seconds = WEEKLY_WINDOW_SECONDS if label == "weekly" else FIVE_HOUR_WINDOW_SECONDS

    return {
        "label": label,
        "usedPercent": round(used_percent, 1),
        "remainingPercent": max(0, round(100 - used_percent, 1)),
        "resetsAt": datetime.fromtimestamp(reset_at, tz=timezone.utc).isoformat(),
        "resetAtEpoch": reset_at,
        "resetAfterSeconds": reset_after_seconds,
        "windowSeconds": window_seconds,
    }


def windows_from_usage(usage):
    fetched_at = datetime.now(timezone.utc)
    windows = []
    for label, key in (("5h", "five_hour"), ("weekly", "seven_day")):
        window = normalize_window(label, usage.get(key), fetched_at)
        if window:
            windows.append(window)
    return windows


def cache_is_fresh(cache):
    if not isinstance(cache, dict) or not windows_from_usage(cache):
        return False
    return int(datetime.now(timezone.utc).timestamp()) - as_int(cache.get("fetched_at")) < usage_cache_ttl_seconds()


def account_from_usage(auth, usage, is_selected, error="", stale=False):
    windows = windows_from_usage(usage)
    account = {
        "ok": bool(windows),
        "label": auth["label"],
        "email": auth.get("email", ""),
        "planType": auth.get("plan_type", ""),
        "isSelected": is_selected,
        "windows": windows,
    }
    if error:
        account["error"] = error
    if stale:
        account["staleCache"] = True
    if not windows and not error:
        account["error"] = "Claude usage API returned no future rate-limit windows."
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
        auth = read_credentials(label, path)
        cached = read_account_cache(label)
        if cache_is_fresh(cached):
            account = account_from_usage(auth, cached, is_selected)
            log_event(f"account={label} using cached Claude usage windows={len(account['windows'])}")
            return account

        try:
            usage, status = fetch_quota_usage(auth)
            write_account_cache(label, usage, status)
            account = account_from_usage(auth, usage, is_selected)
            log_event(
                f"account={label} completed plan={account['planType'] or 'unknown'} "
                f"windows={len(account['windows'])} status={status}"
            )
            return account
        except Exception as error:
            if isinstance(cached, dict) and windows_from_usage(cached):
                account = account_from_usage(auth, cached, is_selected, f"using stale cache after {error}", stale=True)
                log_event(f"account={label} using stale Claude usage cache after error: {error}")
                return account
            raise
    except Exception as error:
        return normalize_error(label, str(error), is_selected)


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


def write_error(message):
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


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()
    credentials = discover_credentials()
    labels = ",".join(label for label, _, _ in credentials)
    log_event(f"starting Claude usage fetch accounts={labels or 'none'}")

    try:
        accounts = [fetch_account(label, path, is_selected) for label, path, is_selected in credentials]
        ok_count = sum(1 for account in accounts if account.get("ok"))
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "Claude",
            "ok": ok_count > 0,
            "accounts": accounts,
            "bars": flatten_bars(accounts),
        }
        common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
        log_event(f"completed fetch accounts={len(accounts)} ok={ok_count} wrote={OUTPUT_PATH.name}")
        print(json.dumps(output, indent=2))
        return 0 if ok_count > 0 else 1
    except Exception as error:
        write_error(f"Claude usage fetch failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

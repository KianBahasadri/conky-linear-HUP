#!/usr/bin/env python3
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "commandcode-usage.json"
RENDER_PATH = CACHE_DIR / "commandcode-usage-render.tsv"
LOG_PATH = CACHE_DIR / "conky-rate-limit-panel.log"
DEFAULT_AUTH_NAME = "auth.json"
DEFAULT_API_BASE_URL = "https://api.commandcode.ai"
USER_AGENT = "command-code/1.27.1"
API_KEY_ENV = "COMMAND_CODE_API_KEY"
USAGE_LABEL_ENV = "COMMAND_CODE_USAGE_LABEL"
FIVE_HOUR_WINDOW_SECONDS = common.FIVE_HOUR_WINDOW_SECONDS
WEEKLY_WINDOW_SECONDS = common.WEEKLY_WINDOW_SECONDS
MONTHLY_WINDOW_SECONDS = 31 * 24 * 60 * 60

# Plan credit pools used by the Command Code CLI `/usage` view.
PLAN_MONTHLY_CREDITS = {
    "individual-go": 10,
    "individual-goat": 70,
    "individual-pro": 30,
    "individual-pro-v1": 80,
    "individual-provider": 15,
    "individual-max": 150,
    "individual-ultra": 300,
    "teams-pro": 40,
}
PLAN_DISPLAY_NAMES = {
    "individual-go": "Go",
    "individual-goat": "GOAT",
    "individual-pro": "Pro",
    "individual-pro-v1": "Pro",
    "individual-provider": "Provider",
    "individual-max": "Max",
    "individual-ultra": "Ultra",
    "teams-pro": "Teams Pro",
}
PLAN_ID_PREFIXES = sorted(PLAN_MONTHLY_CREDITS, key=len, reverse=True)


log_event = common.make_logger(LOG_PATH, "fetch_commandcode_usage")
as_int = common.as_int
as_float = common.as_float
flatten_bars = common.flatten_bars


def commandcode_home():
    configured = (
        os.environ.get("COMMAND_CODE_HOME", "").strip()
        or os.environ.get("COMMANDCODE_HOME", "").strip()
    )
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".commandcode"


def default_auth_path():
    return commandcode_home() / DEFAULT_AUTH_NAME


def api_base_url():
    configured = os.environ.get("COMMANDCODE_API_URL", "").strip().rstrip("/")
    return configured or DEFAULT_API_BASE_URL


def configured_auth_path():
    configured = (
        os.environ.get("COMMAND_CODE_AUTH_PATH", "").strip()
        or os.environ.get("COMMANDCODE_AUTH_PATH", "").strip()
    )
    return Path(configured).expanduser() if configured else None


def env_api_key():
    return os.environ.get(API_KEY_ENV, "").strip()


def auth_label(path):
    name = path.name
    prefix = f"{DEFAULT_AUTH_NAME}."
    if name.startswith(prefix) and len(name) > len(prefix):
        return name[len(prefix):]
    if name == DEFAULT_AUTH_NAME:
        return "cmd"
    if name.endswith(".json"):
        return name[:-5].lstrip(".") or path.stem
    return path.stem.lstrip(".") or name


def is_selected_auth(path):
    try:
        return default_auth_path().resolve() == path.resolve()
    except OSError:
        return default_auth_path() == path


def discover_auth_files():
    """Return (label, path_or_none, is_selected, env_key_or_none) sources."""
    env_key = env_api_key()
    if env_key:
        label = os.environ.get(USAGE_LABEL_ENV, "").strip() or "cmd"
        return [(label, None, True, env_key)]

    configured = configured_auth_path()
    if configured:
        return [(auth_label(configured), configured, is_selected_auth(configured), None)]

    default_path = default_auth_path()
    suffixed_paths = sorted(
        path
        for path in default_path.parent.glob(f"{DEFAULT_AUTH_NAME}.*")
        if path.is_file() and not path.name.endswith(".lock")
    )
    if suffixed_paths:
        return [
            (auth_label(path), path, is_selected_auth(path), None)
            for path in suffixed_paths
        ]
    return [(auth_label(default_path), default_path, is_selected_auth(default_path), None)]


def read_auth(label, path, env_key=None):
    if env_key:
        return {
            "label": label,
            "path": path,
            "api_key": env_key,
            "userName": "",
            "userId": "",
        }

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"missing Command Code auth file: {path}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid Command Code auth JSON: {error}") from error

    if not isinstance(raw, dict):
        raise RuntimeError(f"invalid Command Code auth payload: {path}")

    api_key = str(raw.get("apiKey") or "").strip()
    if not api_key:
        raise RuntimeError(f"auth file has no apiKey: {path}")

    return {
        "label": label,
        "path": path,
        "api_key": api_key,
        "userName": str(raw.get("userName") or "").strip(),
        "userId": str(raw.get("userId") or "").strip(),
    }


def commandcode_request(auth, endpoint, query=None):
    url = f"{api_base_url()}{endpoint}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, method="GET")
    request.add_header("Authorization", f"Bearer {auth['api_key']}")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
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
        raise RuntimeError(f"Command Code {endpoint} request failed: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Command Code {endpoint} response was not JSON: {error}") from error


def request_json(auth, endpoint, query=None):
    status, payload = commandcode_request(auth, endpoint, query)
    if status != 200:
        detail = ""
        if isinstance(payload, dict):
            detail = payload.get("error") or payload.get("message") or ""
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Command Code {endpoint} error: HTTP {status}{suffix}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"Command Code {endpoint} returned a non-object payload")
    return payload


def epoch_seconds(value):
    epoch = as_int(value)
    if epoch > 10**12:
        return epoch // 1000
    return epoch


def normalize_plan_id(plan_id):
    if not plan_id:
        return ""
    return str(plan_id).lower().replace("_", "-")


def plan_info(plan_id):
    normalized = normalize_plan_id(plan_id)
    if not normalized:
        return None
    match = next((prefix for prefix in PLAN_ID_PREFIXES if normalized.startswith(prefix)), None)
    if not match:
        return None
    return {
        "id": match,
        "name": PLAN_DISPLAY_NAMES.get(match, match),
        "monthlyCredits": PLAN_MONTHLY_CREDITS[match],
    }


def credits_object(credits_payload):
    if not isinstance(credits_payload, dict):
        return {}
    nested = credits_payload.get("credits")
    return nested if isinstance(nested, dict) else {}


def window_limits_object(credits_payload):
    if not isinstance(credits_payload, dict):
        return {}
    nested = credits_payload.get("windowLimits")
    return nested if isinstance(nested, dict) else {}


def subscription_object(subscription_payload):
    if not isinstance(subscription_payload, dict):
        return {}
    nested = subscription_payload.get("data")
    return nested if isinstance(nested, dict) else {}


def normalize_window(label, used_percent, reset_at_epoch, window_seconds, fetched_at):
    now = int(fetched_at.timestamp())
    used_percent = max(0.0, min(100.0, float(used_percent)))
    reset_after_seconds = max(0, reset_at_epoch - now) if reset_at_epoch > 0 else 0
    resets_at = (
        datetime.fromtimestamp(reset_at_epoch, tz=timezone.utc).isoformat()
        if reset_at_epoch > 0
        else None
    )
    return {
        "label": label,
        "usedPercent": round(used_percent, 1),
        "remainingPercent": max(0, round(100 - used_percent, 1)),
        "resetsAt": resets_at,
        "resetAtEpoch": reset_at_epoch,
        "resetAfterSeconds": reset_after_seconds,
        "windowSeconds": window_seconds,
    }


def rolling_window(label, payload, window_seconds, fetched_at):
    if not isinstance(payload, dict):
        return None
    cap = as_float(payload.get("cap"))
    used = as_float(payload.get("used"))
    if cap <= 0 and used <= 0 and not payload.get("resetAt"):
        return None
    used_percent = (used / cap) * 100 if cap > 0 else 0.0
    return normalize_window(
        label,
        used_percent,
        epoch_seconds(payload.get("resetAt")),
        window_seconds,
        fetched_at,
    )


def monthly_usage(credits, subscription, summary, plan, fetched_at):
    monthly_remaining = max(0.0, as_float(credits.get("monthlyCredits")))
    purchased_remaining = max(0.0, as_float(credits.get("purchasedCredits")))
    free_remaining = max(0.0, as_float(credits.get("freeCredits")))
    total_remaining = monthly_remaining + purchased_remaining + free_remaining
    total_spent = max(0.0, as_float((summary or {}).get("totalCost")))
    plan_monthly = plan["monthlyCredits"] if plan and subscription.get("status") == "active" else None
    if plan_monthly is not None:
        total_pool = max(plan_monthly, monthly_remaining) + purchased_remaining + free_remaining
    else:
        total_pool = total_spent + total_remaining
    used_percent = ((total_pool - total_remaining) / total_pool) * 100 if total_pool > 0 else 0.0

    cycle_start = common.parse_iso_epoch(subscription.get("currentPeriodStart"))
    cycle_end = common.parse_iso_epoch(subscription.get("currentPeriodEnd"))
    window_seconds = (
        cycle_end - cycle_start
        if cycle_start > 0 and cycle_end > cycle_start
        else MONTHLY_WINDOW_SECONDS
    )
    window = normalize_window("monthly", used_percent, cycle_end, window_seconds, fetched_at)
    window["monthlyRemaining"] = round(monthly_remaining, 4)
    window["purchasedRemaining"] = round(purchased_remaining, 4)
    window["freeRemaining"] = round(free_remaining, 4)
    window["totalRemaining"] = round(total_remaining, 4)
    window["totalSpent"] = round(total_spent, 4)
    window["totalPool"] = round(total_pool, 4)
    return window


def empty_usage_windows():
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
        for label, window_seconds in (
            ("5h", FIVE_HOUR_WINDOW_SECONDS),
            ("weekly", WEEKLY_WINDOW_SECONDS),
            ("monthly", MONTHLY_WINDOW_SECONDS),
        )
    ]


def normalize_usage(auth, whoami, credits_payload, subscription_payload, summary, is_selected):
    fetched_at = datetime.now(timezone.utc)
    credits = credits_object(credits_payload)
    limits = window_limits_object(credits_payload)
    subscription = subscription_object(subscription_payload)
    summary = summary if isinstance(summary, dict) else {}
    plan = plan_info(subscription.get("planId") or credits.get("planId"))
    user = whoami.get("user") if isinstance(whoami, dict) else {}
    user = user if isinstance(user, dict) else {}

    windows = []
    five_hour = rolling_window("5h", limits.get("fiveHour"), FIVE_HOUR_WINDOW_SECONDS, fetched_at)
    weekly = rolling_window("weekly", limits.get("weekly"), WEEKLY_WINDOW_SECONDS, fetched_at)
    if five_hour:
        windows.append(five_hour)
    if weekly:
        windows.append(weekly)
    windows.append(monthly_usage(credits, subscription, summary, plan, fetched_at))

    account = {
        "ok": bool(windows),
        "label": auth["label"],
        "email": str(user.get("email") or ""),
        "accountId": str(user.get("id") or auth.get("userId") or ""),
        "planType": (plan or {}).get("name", ""),
        "planId": (plan or {}).get("id", "") or str(subscription.get("planId") or ""),
        "isSelected": is_selected,
        "windows": windows,
    }
    return account


def normalize_error(label, message, is_selected=False):
    return {
        "ok": False,
        "label": label,
        "error": message,
        "isSelected": is_selected,
        "windows": empty_usage_windows(),
    }


def safe_cache_label(label):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("._")
    return safe or "default"


def account_cache_path(label):
    return CACHE_DIR / f"commandcode-usage-cache-{safe_cache_label(label)}.json"


def read_account_cache(label):
    try:
        cached = json.loads(account_cache_path(label).read_text(encoding="utf-8"))
        if isinstance(cached, dict) and cached.get("windows"):
            return cached
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    try:
        output = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    if not isinstance(output, dict):
        return None
    for account in output.get("accounts", []):
        if isinstance(account, dict) and account.get("label") == label and account.get("windows"):
            return account
    return None


def write_account_cache(account):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.atomic_write_json(account_cache_path(account["label"]), account)


def fetch_account(label, path, is_selected, env_key=None):
    try:
        auth = read_auth(label, path, env_key=env_key)
        whoami = request_json(auth, "/alpha/whoami")
        org = whoami.get("org") if isinstance(whoami.get("org"), dict) else {}
        org_id = org.get("id")
        query = {"orgId": org_id} if org_id else None
        credits_payload = request_json(auth, "/alpha/billing/credits", query)
        subscription_payload = request_json(auth, "/alpha/billing/subscriptions", query)
        period_start = subscription_object(subscription_payload).get("currentPeriodStart")
        summary_query = dict(query or {})
        if period_start:
            summary_query["since"] = period_start
        summary = request_json(auth, "/alpha/usage/summary", summary_query or None)
        account = normalize_usage(
            auth,
            whoami,
            credits_payload,
            subscription_payload,
            summary,
            is_selected,
        )
        write_account_cache(account)
        monthly = next((window for window in account["windows"] if window.get("label") == "monthly"), {})
        log_event(
            f"account={label} completed plan={account.get('planType') or 'unknown'} "
            f"monthly={monthly.get('usedPercent', 0)}% windows={len(account['windows'])}"
        )
        return account
    except Exception as error:
        cached = read_account_cache(label)
        if isinstance(cached, dict) and cached.get("windows"):
            cached = dict(cached)
            cached["isSelected"] = is_selected
            cached["ok"] = True
            cached["staleCache"] = True
            cached["error"] = f"using stale cache after {error}"
            log_event(f"account={label} using stale Command Code cache after error: {error}")
            return cached
        return normalize_error(label, str(error), is_selected)


def write_error(message, label="cmd"):
    account = normalize_error(label, message, is_selected=True)
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "CommandCode",
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
    auth_files = discover_auth_files()
    labels = ",".join(label for label, _, _, _ in auth_files)
    log_event(f"starting Command Code usage fetch accounts={labels or 'none'}")

    try:
        accounts = [
            fetch_account(label, path, is_selected, env_key)
            for label, path, is_selected, env_key in auth_files
        ]
        ok_count = sum(1 for account in accounts if account.get("ok"))
        errors = [account.get("error", "") for account in accounts if not account.get("ok")]
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "CommandCode",
            "ok": ok_count > 0,
            "error": "; ".join(error for error in errors if error),
            "accounts": accounts,
            "bars": flatten_bars(accounts),
        }
        common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
        log_event(f"completed fetch accounts={len(accounts)} ok={ok_count} wrote={OUTPUT_PATH.name}")
        print(json.dumps(output, indent=2))
        return 0 if ok_count > 0 else 1
    except Exception as error:
        write_error(f"Command Code usage fetch failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

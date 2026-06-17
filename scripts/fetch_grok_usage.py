#!/usr/bin/env python3
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "grok-usage.json"
RENDER_PATH = CACHE_DIR / "grok-usage-render.tsv"
LOG_PATH = CACHE_DIR / "conky-rate-limit-panel.log"
DEFAULT_AUTH_NAME = "auth.json"
DEFAULT_API_BASE_URL = "https://cli-chat-proxy.grok.com/v1"
USER_AGENT = "grok/0.2.51"
MONTHLY_WINDOW_SECONDS = 31 * 24 * 60 * 60


log_event = common.make_logger(LOG_PATH, "fetch_grok_usage")
as_int = common.as_int
flatten_bars = common.flatten_bars


def grok_home():
    return Path(os.environ.get("GROK_HOME", Path.home() / ".grok")).expanduser()


def default_auth_path():
    return grok_home() / DEFAULT_AUTH_NAME


def api_base_url():
    configured = os.environ.get("GROK_CLI_CHAT_PROXY_BASE_URL", "").strip().rstrip("/")
    return configured or DEFAULT_API_BASE_URL


def configured_auth_path():
    configured = os.environ.get("GROK_AUTH_PATH", "").strip()
    return Path(configured).expanduser() if configured else None


def auth_email(label, path):
    try:
        return read_auth(label, path).get("email", "")
    except Exception:
        return ""


def discover_auth_files():
    configured = configured_auth_path()
    if configured:
        return [(auth_label(configured), configured, is_selected_auth(configured))]

    default_path = default_auth_path()
    suffixed_paths = sorted(
        path
        for path in default_path.parent.glob(f"{DEFAULT_AUTH_NAME}.*")
        if path.is_file() and not path.name.endswith(".lock")
    )

    # Grok CLI refreshes auth.json in place. Suffixed copies can go stale when
    # auth.json is a standalone file instead of a symlink to one of them.
    if default_path.is_file() and not default_path.is_symlink():
        accounts = [(auth_label(default_path), default_path, True)]
        default_email = auth_email(accounts[0][0], default_path)
        for path in suffixed_paths:
            try:
                if path.resolve() == default_path.resolve():
                    continue
            except OSError:
                pass
            label = auth_label(path)
            if default_email and auth_email(label, path) == default_email:
                continue
            accounts.append((label, path, False))
        return accounts

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
        return "grok"
    if name.endswith(".json"):
        return name[:-5].lstrip(".") or path.stem
    return path.stem.lstrip(".") or name


def unwrap_val(value):
    if isinstance(value, dict) and "val" in value:
        return value["val"]
    return value


def read_auth(label, path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"missing Grok auth file: {path}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid Grok auth JSON: {error}") from error

    if not isinstance(raw, dict):
        raise RuntimeError(f"invalid Grok auth payload: {path}")

    entry = None
    for candidate in raw.values():
        if isinstance(candidate, dict) and candidate.get("key"):
            entry = candidate
            break
    if not entry:
        raise RuntimeError(f"auth file has no session token: {path}")

    return {
        "label": label,
        "path": path,
        "access_token": entry["key"],
        "refresh_token": entry.get("refresh_token", ""),
        "email": entry.get("email", ""),
        "tier": as_int(entry.get("tier"), 0),
    }


def grok_request(auth, resource, query=None):
    url = f"{api_base_url()}/{resource}"
    if query:
        url = f"{url}?{query}"
    request = urllib.request.Request(url, method="GET")
    request.add_header("Authorization", f"Bearer {auth['access_token']}")
    request.add_header("User-Agent", USER_AGENT)
    request.add_header("X-XAI-Token-Auth", "xai-grok-cli")
    request.add_header("Accept", "application/json")

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
        raise RuntimeError(f"Grok {resource} request failed: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Grok {resource} response was not JSON: {error}") from error


def optional_metadata(auth, resource):
    status, payload = grok_request(auth, resource)
    if status == 200 and isinstance(payload, dict):
        return payload
    log_event(f"account={auth['label']} {resource} returned HTTP {status}")
    return {}


def plan_type(auth, user):
    tier = auth.get("tier")
    if tier:
        return f"tier-{tier}"
    if isinstance(user, dict) and user.get("hasGrokCodeAccess"):
        return "build"
    return ""


def normalize_grok_window(label, used_percent, cycle_start, cycle_end, fetched_at):
    now = int(fetched_at.timestamp())
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
    }


def billing_usage_percent(config):
    used = as_int(unwrap_val(config.get("used")))
    monthly_limit = as_int(unwrap_val(config.get("monthlyLimit")))
    if monthly_limit > 0:
        return (used / monthly_limit) * 100, used, monthly_limit

    credit_usage_percent = config.get("creditUsagePercent")
    if credit_usage_percent is not None:
        return float(credit_usage_percent), 0, 0

    return 0.0, used, monthly_limit


def billing_cycle_bounds(config):
    cycle_start = common.parse_iso_epoch(config.get("billingPeriodStart"))
    cycle_end = common.parse_iso_epoch(config.get("billingPeriodEnd"))
    current_period = config.get("currentPeriod")
    if isinstance(current_period, dict):
        if cycle_start <= 0:
            cycle_start = common.parse_iso_epoch(current_period.get("start"))
        if cycle_end <= 0:
            cycle_end = common.parse_iso_epoch(current_period.get("end"))
    return cycle_start, cycle_end


def normalize_usage(auth, billing, user, is_selected):
    fetched_at = datetime.now(timezone.utc)
    config = billing.get("config") if isinstance(billing, dict) else {}
    config = config if isinstance(config, dict) else {}

    used_percent, used, monthly_limit = billing_usage_percent(config)
    cycle_start, cycle_end = billing_cycle_bounds(config)

    windows = [
        normalize_grok_window(
            "monthly",
            used_percent,
            cycle_start,
            cycle_end,
            fetched_at,
        )
    ]

    account = {
        "ok": bool(windows),
        "label": auth["label"],
        "email": (user.get("email", "") if isinstance(user, dict) else "") or auth.get("email", ""),
        "accountId": str(user.get("userId", "")) if isinstance(user, dict) else "",
        "planType": plan_type(auth, user),
        "isSelected": is_selected,
        "windows": windows,
        "usedCredits": used,
        "monthlyLimitCredits": monthly_limit,
    }
    if not windows:
        account["error"] = "Grok billing API returned no monthly usage window."
    return account


def normalize_error(label, message, is_selected=False):
    return {
        "ok": False,
        "label": label,
        "error": message,
        "isSelected": is_selected,
        "windows": [],
    }


def fetch_billing(auth):
    status, billing = grok_request(auth, "billing", "format=credits")
    if status == 200:
        return billing

    log_event(f"account={auth['label']} billing?format=credits returned HTTP {status}, retrying /billing")
    status, billing = grok_request(auth, "billing")
    if status != 200:
        detail = billing.get("error", "") if isinstance(billing, dict) else ""
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Grok billing API error: HTTP {status}{suffix}")
    return billing


def fetch_account(label, path, is_selected):
    try:
        auth = read_auth(label, path)
        billing = fetch_billing(auth)

        user = optional_metadata(auth, "user")
        account = normalize_usage(auth, billing, user, is_selected)
        monthly = account["windows"][0] if account.get("windows") else {}
        usage_summary = (
            f"{account.get('usedCredits', 0)}/{account.get('monthlyLimitCredits', 0)}"
            if account.get("monthlyLimitCredits", 0) > 0
            else f"{monthly.get('usedPercent', 0)}%"
        )
        log_event(
            f"account={label} completed plan={account['planType'] or 'unknown'} "
            f"used={usage_summary} windows={len(account['windows'])}"
        )
        return account
    except Exception as error:
        return normalize_error(label, str(error), is_selected)


def write_error(message):
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "Grok",
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
    log_event(f"starting Grok usage fetch accounts={labels or 'none'}")

    try:
        accounts = [fetch_account(label, path, is_selected) for label, path, is_selected in auth_files]
        ok_count = sum(1 for account in accounts if account.get("ok"))
        errors = [account.get("error", "") for account in accounts if not account.get("ok")]
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "Grok",
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
        write_error(f"Grok usage fetch failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

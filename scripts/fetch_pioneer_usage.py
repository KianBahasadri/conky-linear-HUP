#!/usr/bin/env python3
import json
import os
import urllib.error
import urllib.request
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "pioneer-usage.json"
RENDER_PATH = CACHE_DIR / "pioneer-usage-render.tsv"
LOG_PATH = CACHE_DIR / "conky-rate-limit-panel.log"
API_BASE_URL = "https://api.pioneer.ai"
DEFAULT_ACCOUNT_LABEL = "pioneer"
DAILY_WINDOW_SECONDS = 24 * 60 * 60
MONTHLY_WINDOW_SECONDS = 31 * 24 * 60 * 60
PLAN_MONTHLY_CREDIT_LIMITS = {
    "hobby": 3000.0,
    "pro": 150000.0,
}


log_event = common.make_logger(LOG_PATH, "fetch_pioneer_usage")
as_float = common.as_float
flatten_bars = common.flatten_bars


def account_label():
    configured = os.environ.get("PIONEER_USAGE_LABEL", "").strip()
    return configured or DEFAULT_ACCOUNT_LABEL


def api_key():
    return os.environ.get("PIONEER_API_KEY", "").strip()


def monthly_credit_limit_override():
    configured = os.environ.get("PIONEER_MONTHLY_CREDIT_LIMIT", "").strip()
    return as_float(configured) if configured else 0.0


def pioneer_request(path, query=""):
    url = f"{API_BASE_URL}{path}"
    if query:
        url = f"{url}?{query}"

    request = urllib.request.Request(url, method="GET")
    request.add_header("X-API-Key", api_key())
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
        raise RuntimeError(f"Pioneer GET {path} failed: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Pioneer GET {path} response was not JSON: {error}") from error


def next_daily_reset_epoch(now, reset_hour, timezone_name):
    tz = ZoneInfo(timezone_name or "UTC")
    local_now = now.astimezone(tz)
    reset_at = local_now.replace(hour=int(reset_hour), minute=0, second=0, microsecond=0)
    if local_now >= reset_at:
        reset_at += timedelta(days=1)
    return int(reset_at.timestamp())


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def add_one_month(dt):
    month = dt.month + 1
    year = dt.year
    if month > 12:
        month = 1
        year += 1
    day = min(dt.day, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def billing_period(overage_settings, now):
    overage_settings = overage_settings if isinstance(overage_settings, dict) else {}
    period_start = parse_iso_datetime(overage_settings.get("current_month_start"))
    if period_start:
        period_end = add_one_month(period_start)
        return period_start, period_end, True

    calendar_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        calendar_end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        calendar_end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return calendar_start, calendar_end, False


def next_monthly_reset_epoch(now):
    _, period_end, _ = billing_period({}, now)
    return int(period_end.timestamp())


def month_start_epoch(now):
    period_start, _, _ = billing_period({}, now)
    return int(period_start.timestamp())


def resolve_monthly_usage(overage_settings, now):
    overage_settings = overage_settings if isinstance(overage_settings, dict) else {}
    period_start, _, uses_billing_period = billing_period(overage_settings, now)
    if uses_billing_period:
        return as_float(overage_settings.get("current_period_usage"))

    status, payload = pioneer_request(
        "/billing/usage/timeseries",
        f"start_date={period_start.isoformat()}&end_date={now.isoformat()}",
    )
    if status != 200 or not isinstance(payload, dict):
        detail = payload.get("detail", payload.get("error", "")) if isinstance(payload, dict) else ""
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"Pioneer usage timeseries API error: HTTP {status}{suffix}")

    points = payload.get("points") if isinstance(payload.get("points"), list) else []
    return sum(as_float(point.get("total_credits")) for point in points if isinstance(point, dict))


def normalize_window(label, used, limit, reset_at_epoch, window_seconds, fetched_at):
    now = int(fetched_at.timestamp())
    used = max(0.0, as_float(used))
    limit = max(0.0, as_float(limit))
    used_percent = (used / limit) * 100 if limit > 0 else 0.0
    used_percent = max(0.0, min(100.0, used_percent))
    reset_after_seconds = max(0, reset_at_epoch - now) if reset_at_epoch > 0 else 0
    resets_at = datetime.fromtimestamp(reset_at_epoch, tz=timezone.utc).isoformat() if reset_at_epoch > 0 else None

    return {
        "label": label,
        "usedPercent": round(used_percent, 1),
        "remainingPercent": max(0, round(100 - used_percent, 1)),
        "resetsAt": resets_at,
        "resetAtEpoch": reset_at_epoch,
        "resetAfterSeconds": reset_after_seconds,
        "windowSeconds": window_seconds,
        "usedCredits": round(used, 4),
        "limitCredits": round(limit, 4),
    }


def resolve_monthly_credit_limit(payment_plan, overage_settings):
    override = monthly_credit_limit_override()
    if override > 0:
        return override

    configured_cap = as_float(overage_settings.get("max_monthly_spend"))
    if configured_cap > 0:
        return configured_cap

    return PLAN_MONTHLY_CREDIT_LIMITS.get(str(payment_plan or "").lower(), 0.0)


def fetch_monthly_usage(now, overage_settings):
    return resolve_monthly_usage(overage_settings, now)


def fetch_team_overage_settings(team_id):
    if not team_id:
        return {}

    status, payload = pioneer_request(f"/billing/team/{team_id}/overage-settings")
    if status == 200 and isinstance(payload, dict):
        return payload

    log_event(f"team overage settings returned HTTP {status}; using defaults")
    return {}


def normalize_usage(plan_info, overage_settings, monthly_usage, is_selected):
    fetched_at = datetime.now(timezone.utc)
    plan_info = plan_info if isinstance(plan_info, dict) else {}
    overage_settings = overage_settings if isinstance(overage_settings, dict) else {}

    payment_plan = str(plan_info.get("payment_plan", "")).lower()
    daily_used = as_float(plan_info.get("total_usage"))
    daily_limit = as_float(plan_info.get("credit_limit"))
    monthly_limit = resolve_monthly_credit_limit(payment_plan, overage_settings)
    reset_hour = overage_settings.get("usage_reset_hour", 0)
    reset_timezone = overage_settings.get("usage_reset_timezone", "UTC")
    daily_reset_epoch = next_daily_reset_epoch(fetched_at, reset_hour, reset_timezone)
    period_start, period_end, uses_billing_period = billing_period(overage_settings, fetched_at)
    monthly_reset_epoch = int(period_end.timestamp())
    monthly_window_seconds = max(DAILY_WINDOW_SECONDS, monthly_reset_epoch - int(period_start.timestamp()))

    windows = [
        normalize_window(
            "daily",
            daily_used,
            daily_limit,
            daily_reset_epoch,
            DAILY_WINDOW_SECONDS,
            fetched_at,
        )
    ]

    if monthly_limit > 0:
        windows.append(
            normalize_window(
                "monthly",
                monthly_usage,
                monthly_limit,
                monthly_reset_epoch,
                monthly_window_seconds,
                fetched_at,
            )
        )

    account = {
        "ok": bool(windows),
        "label": account_label(),
        "planType": payment_plan,
        "isSelected": is_selected,
        "windows": windows,
        "dailyUsedCredits": daily_used,
        "dailyLimitCredits": daily_limit,
        "monthlyUsedCredits": round(monthly_usage, 4),
        "monthlyLimitCredits": monthly_limit,
        "usageResetHour": reset_hour,
        "usageResetTimezone": reset_timezone,
        "billingPeriodStart": period_start.isoformat(),
        "billingPeriodEnd": period_end.isoformat(),
        "usesBillingPeriod": uses_billing_period,
    }
    if not windows:
        account["error"] = "Pioneer billing API returned no usage windows."
    return account


def normalize_error(message, is_selected=True):
    return {
        "ok": False,
        "label": account_label(),
        "error": message,
        "isSelected": is_selected,
        "windows": [],
    }


def fetch_account(is_selected=True):
    key = api_key()
    if not key:
        return normalize_error("PIONEER_API_KEY is not set.", is_selected)

    status, plan_info = pioneer_request("/billing/plan-info")
    if status != 200 or not isinstance(plan_info, dict):
        detail = plan_info.get("detail", plan_info.get("error", "")) if isinstance(plan_info, dict) else ""
        suffix = f": {detail}" if detail else ""
        return normalize_error(f"Pioneer plan info API error: HTTP {status}{suffix}", is_selected)

    status, billing_status = pioneer_request("/billing/billing-status")
    team_id = billing_status.get("team_id", "") if status == 200 and isinstance(billing_status, dict) else ""
    overage_settings = fetch_team_overage_settings(team_id)

    try:
        monthly_usage = fetch_monthly_usage(datetime.now(timezone.utc), overage_settings)
    except RuntimeError as error:
        return normalize_error(str(error), is_selected)

    account = normalize_usage(plan_info, overage_settings, monthly_usage, is_selected)
    log_event(
        f"account={account['label']} completed plan={account['planType'] or 'unknown'} "
        f"daily={account.get('dailyUsedCredits', 0)}/{account.get('dailyLimitCredits', 0)} "
        f"monthly={account.get('monthlyUsedCredits', 0)}/{account.get('monthlyLimitCredits', 0)} "
        f"windows={len(account['windows'])}"
    )
    return account


def write_error(message):
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "Pioneer",
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
    label = account_label()
    log_event(f"starting Pioneer usage fetch account={label}")

    try:
        account = fetch_account(True)
        ok_count = 1 if account.get("ok") else 0
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "Pioneer",
            "ok": ok_count > 0,
            "error": account.get("error", "") if not account.get("ok") else "",
            "accounts": [account],
            "bars": flatten_bars([account]),
        }
        common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
        log_event(f"completed fetch accounts=1 ok={ok_count} wrote={OUTPUT_PATH.name}")
        print(json.dumps(output, indent=2))
        return 0 if ok_count > 0 else 1
    except Exception as error:
        write_error(f"Pioneer usage fetch failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

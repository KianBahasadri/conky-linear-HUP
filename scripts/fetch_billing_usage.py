#!/usr/bin/env python3
"""Collect month-to-date billing data for the affine billing map.

Metered services are normalized against user-defined monthly caps. OpenRouter
is prepaid against remaining credit. Azure is prepaid against the credit
pool the current month started with: month-to-date spend is the current
point, and calendar pace projects that spend through the same month end.
"""

import calendar
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
STATUS_PATH = CACHE_DIR / "billing-usage.json"
RENDER_PATH = CACHE_DIR / "billing-usage-render.tsv"
HISTORY_PATH = CACHE_DIR / "billing-history.json"
LOG_PATH = CACHE_DIR / "conky-billing.log"

AWS_COLOR = "ffb454"
AZURE_COLOR = "38bdf8"
ANTHROPIC_COLOR = "ff8f73"
OPENROUTER_COLOR = "c8ff00"
GITHUB_ACTIONS_COLOR = "3fb950"
GITHUB_API_VERSION = "2026-03-10"
GITHUB_ACTIONS_PLAN_MINUTES = {
    "free": Decimal("2000"),
    "pro": Decimal("3000"),
}
GITHUB_ACTIONS_STANDARD_SKUS = {
    "actions_linux_slim",
    "actions_linux",
    "actions_linux_arm",
    "actions_windows",
    "actions_windows_arm",
    "actions_macos",
}
USER_AGENT = "conky-linear-HUP/1.0"

log_event = common.make_logger(LOG_PATH, "fetch_billing_usage")


class ProviderError(RuntimeError):
    """A provider could not return trustworthy billing data."""


def utc_iso(value):
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def month_period(reference=None):
    """Return one shared local-calendar horizon for every provider."""
    if reference is None:
        local_now = datetime.now().astimezone()
    elif isinstance(reference, datetime):
        local_now = reference
        if local_now.tzinfo is None:
            local_now = local_now.astimezone()
    else:
        local_now = datetime.combine(reference, time.min).astimezone()

    today = local_now.date()
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    period_start = date(today.year, today.month, 1)
    period_end = date(today.year, today.month, days_in_month)
    if today.month == 12:
        end_exclusive = date(today.year + 1, 1, 1)
    else:
        end_exclusive = date(today.year, today.month + 1, 1)

    return {
        "today": today,
        "periodStart": period_start,
        "periodEnd": period_end,
        "periodEndExclusive": end_exclusive,
        "day": today.day,
        "daysInMonth": days_in_month,
        "daysRemaining": max(0, (period_end - today).days),
        "elapsedFraction": today.day / days_in_month,
        "periodLabel": today.strftime("%B %Y").upper(),
        "endLabel": period_end.strftime("%b %d").upper(),
        "localNow": local_now,
    }


def env_decimal(name, *, allow_zero=True):
    text = os.environ.get(name, "").strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be a number") from error
    if not value.is_finite() or value < 0 or (not allow_zero and value == 0):
        qualifier = "greater than zero" if not allow_zero else "zero or greater"
        raise ValueError(f"{name} must be {qualifier}")
    return value


def as_decimal(value, label):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ProviderError(f"{label} was not numeric") from error
    if not number.is_finite():
        raise ProviderError(f"{label} was not finite")
    return number


def rounded(value, places=4):
    if value is None:
        return None
    return round(float(value), places)


def clean_error(error):
    message = " ".join(str(error).split())
    return message[:320] or error.__class__.__name__


def run_json(command, timeout):
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise ProviderError(f"{command[0]} is not installed") from error
    except subprocess.TimeoutExpired as error:
        raise ProviderError(f"{command[0]} timed out after {timeout}s") from error

    if result.returncode != 0:
        detail = clean_error(result.stderr or result.stdout or "command failed")
        raise ProviderError(f"{command[0]} failed: {detail}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ProviderError(f"{command[0]} returned invalid JSON") from error


def env_flag(name, default=False):
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off", "disabled"}


def request_json(url, *, headers=None, payload=None, timeout=20):
    request_headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        **(headers or {}),
    }
    body = None
    method = "GET"
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(
        url, data=body, headers=request_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as error:
        # HTTPError bodies can contain account metadata, so keep the cache/log
        # message deliberately terse and never include headers or URLs with keys.
        code = getattr(error, "code", None)
        suffix = f" (HTTP {code})" if code else ""
        raise ProviderError(f"request failed{suffix}: {error.__class__.__name__}") from error


def linear_month_forecast(current, period):
    if period["day"] <= 0:
        return current
    return current * Decimal(period["daysInMonth"]) / Decimal(period["day"])


def metered_provider(
    provider_id,
    code,
    name,
    color,
    cap,
    current,
    period,
    source,
):
    if cap is None or cap <= 0:
        raise ValueError(f"BILLING_{provider_id.upper()}_CAP_USD must be greater than zero")
    current = max(Decimal(0), current)
    forecast = linear_month_forecast(current, period)
    forecast = max(current, forecast)
    return {
        "id": provider_id,
        "code": code,
        "name": name,
        "color": color,
        "kind": "metered",
        "ok": True,
        "stale": False,
        "currentUsd": rounded(current, 2),
        "capUsd": rounded(cap, 2),
        "forecastUsd": rounded(forecast, 2),
        "currentPressure": rounded(current / cap),
        "forecastPressure": rounded(forecast / cap),
        "forecastAvailable": True,
        "source": source,
        "forecastSource": "linear-month-pace",
        "detail": f"${float(current):.2f} now · ${float(forecast):.2f} EOM · ${float(cap):.2f} cap",
    }


def fetch_aws_current(period, timeout):
    query_end = min(period["today"] + timedelta(days=1), period["periodEndExclusive"])
    command = [
        "aws",
        "ce",
        "get-cost-and-usage",
        "--time-period",
        f"Start={period['periodStart'].isoformat()},End={query_end.isoformat()}",
        "--granularity",
        "MONTHLY",
        "--metrics",
        "UnblendedCost",
        "--output",
        "json",
        "--no-cli-pager",
    ]
    profile = os.environ.get("BILLING_AWS_PROFILE", "").strip()
    if profile:
        command.extend(["--profile", profile])
    payload = run_json(command, timeout)
    rows = payload.get("ResultsByTime") or []
    if not rows:
        return Decimal(0)
    value = ((rows[0].get("Total") or {}).get("UnblendedCost") or {})
    unit = str(value.get("Unit") or "USD").upper()
    if unit != "USD":
        raise ProviderError(f"AWS returned {unit}; only USD caps are supported")
    return as_decimal(value.get("Amount", 0), "AWS amount")


def azure_throttled(error):
    text = str(error).lower()
    return "429" in text or "too many requests" in text


def azure_subscription_id(timeout):
    subscription_id = os.environ.get("BILLING_AZURE_SUBSCRIPTION_ID", "").strip()
    if subscription_id:
        return subscription_id
    try:
        result = subprocess.run(
            ["az", "account", "show", "--query", "id", "--output", "tsv"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise ProviderError("az is not installed") from error
    except subprocess.TimeoutExpired as error:
        raise ProviderError(f"az timed out after {timeout}s") from error
    if result.returncode != 0 or not result.stdout.strip():
        raise ProviderError("Azure CLI is not logged in and no subscription was set")
    return result.stdout.strip()


def azure_rest(method, url, timeout, body=None):
    command = ["az", "rest", "--method", method, "--url", url, "--output", "json"]
    if body is not None:
        command.extend(["--body", json.dumps(body, separators=(",", ":"))])
    return run_json(command, timeout)


def azure_cost_query_url(subscription_id, api_version):
    return (
        "https://management.azure.com/subscriptions/"
        f"{urllib.parse.quote(subscription_id, safe='')}/providers/"
        f"Microsoft.CostManagement/query?api-version={urllib.parse.quote(api_version)}"
    )


def azure_usage_details_url(subscription_id, top=100):
    return (
        "https://management.azure.com/subscriptions/"
        f"{urllib.parse.quote(subscription_id, safe='')}/providers/"
        f"Microsoft.Consumption/usageDetails?api-version=2023-05-01"
        f"&$top={int(top)}"
    )


def parse_azure_cost_query(payload):
    properties = payload.get("properties") or {}
    columns = [str(item.get("name") or "") for item in properties.get("columns") or []]
    rows = properties.get("rows") or []
    if not rows:
        return Decimal(0), "USD"
    try:
        cost_index = next(
            index
            for index, name in enumerate(columns)
            if name.lower() in {"pretaxcost", "cost"}
        )
    except StopIteration as error:
        raise ProviderError("Azure response did not include a cost column") from error
    currency_index = next(
        (index for index, name in enumerate(columns) if name.lower() == "currency"),
        None,
    )
    total = Decimal(0)
    currency = "USD"
    for row in rows:
        if currency_index is not None and len(row) > currency_index:
            currency = str(row[currency_index] or "USD").upper()
        total += as_decimal(row[cost_index], "Azure cost")
    return total, currency


def azure_cost_query_body(granularity="None"):
    return {
        "type": "ActualCost",
        "timeframe": "MonthToDate",
        "dataset": {
            "granularity": granularity,
            "aggregation": {"totalCost": {"name": "PreTaxCost", "function": "Sum"}},
        },
    }


def azure_cost_management_payload(subscription_id, timeout, granularity="None"):
    configured = os.environ.get("BILLING_AZURE_API_VERSION", "2025-03-01").strip()
    versions = [configured or "2025-03-01"]
    if "2023-11-01" not in versions:
        versions.append("2023-11-01")
    body = azure_cost_query_body(granularity)
    last_error = None
    for api_version in versions:
        try:
            return azure_rest(
                "post",
                azure_cost_query_url(subscription_id, api_version),
                timeout,
                body,
            )
        except ProviderError as error:
            last_error = error
            if not azure_throttled(error):
                raise
    raise last_error


def fetch_azure_cost_management(subscription_id, timeout):
    return parse_azure_cost_query(
        azure_cost_management_payload(subscription_id, timeout, "None")
    )


def azure_usage_properties(item):
    return item.get("properties") or item


def azure_pricing_to_billing_rate(subscription_id, timeout):
    payload = azure_rest("get", azure_usage_details_url(subscription_id, top=1), timeout)
    items = payload.get("value") or []
    if not items:
        raise ProviderError("Azure usage details did not include an exchange rate")
    props = azure_usage_properties(items[0])
    rate = props.get("exchangeRatePricingToBilling") or props.get("exchangeRate")
    value = as_decimal(rate, "Azure exchange rate")
    if value <= 0:
        raise ProviderError("Azure exchange rate was not positive")
    return value


def iter_azure_usage_details(subscription_id, timeout):
    url = azure_usage_details_url(subscription_id, top=100)
    pages = 0
    while url:
        pages += 1
        if pages > 40:
            raise ProviderError("Azure usage details pagination exceeded the page limit")
        payload = azure_rest("get", url, timeout)
        for item in payload.get("value") or []:
            yield azure_usage_properties(item)
        url = payload.get("nextLink")


def fetch_azure_usage_usd(subscription_id, timeout):
    total = Decimal(0)
    for props in iter_azure_usage_details(subscription_id, timeout):
        usd = props.get("costInUSD")
        if usd is None:
            continue
        total += as_decimal(usd, "Azure costInUSD")
    return total


def azure_query_date(value):
    text = str(value or "").strip()
    if len(text) >= 8 and text[:8].isdigit() and "-" not in text[:8]:
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    try:
        return date.fromisoformat(text[:10])
    except ValueError as error:
        raise ProviderError("Azure daily cost row omitted a usable date") from error


def azure_usage_detail_date(props):
    raw = props.get("date") or props.get("usageStart") or props.get("usageDate")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def parse_azure_daily_cost_query(payload):
    properties = payload.get("properties") or {}
    columns = [str(item.get("name") or "") for item in properties.get("columns") or []]
    rows = properties.get("rows") or []
    try:
        cost_index = next(
            index
            for index, name in enumerate(columns)
            if name.lower() in {"pretaxcost", "cost"}
        )
    except StopIteration as error:
        raise ProviderError("Azure daily response did not include a cost column") from error
    try:
        date_index = next(
            index for index, name in enumerate(columns) if "date" in name.lower()
        )
    except StopIteration as error:
        raise ProviderError("Azure daily response did not include a date column") from error
    currency_index = next(
        (index for index, name in enumerate(columns) if name.lower() == "currency"),
        None,
    )
    daily = {}
    currency = "USD"
    for row in rows:
        if currency_index is not None and len(row) > currency_index:
            currency = str(row[currency_index] or "USD").upper()
        day = azure_query_date(row[date_index])
        daily[day] = daily.get(day, Decimal(0)) + as_decimal(
            row[cost_index], "Azure daily cost"
        )
    return daily, currency


def fetch_azure_usage_by_day(subscription_id, timeout, period):
    daily = {}
    start = period["periodStart"]
    end = period["today"]
    for props in iter_azure_usage_details(subscription_id, timeout):
        day = azure_usage_detail_date(props)
        if day is None or day < start or day > end:
            continue
        usd = props.get("costInUSD")
        if usd is None:
            continue
        daily[day] = daily.get(day, Decimal(0)) + as_decimal(usd, "Azure costInUSD")
    return daily


def fetch_azure_daily_usd(period, timeout):
    subscription_id = azure_subscription_id(timeout)
    try:
        payload = azure_cost_management_payload(subscription_id, timeout, "Daily")
        daily, currency = parse_azure_daily_cost_query(payload)
        if currency != "USD" and daily:
            rate = azure_pricing_to_billing_rate(subscription_id, timeout)
            daily = {day: amount / rate for day, amount in daily.items()}
        if daily:
            return daily
    except ProviderError as error:
        log_event(f"Azure daily Cost Management unavailable: {clean_error(error)}")
    return fetch_azure_usage_by_day(subscription_id, timeout, period)


def azure_history_pressures(daily, period, starting):
    """Cumulative spend through each past day, as pressure against month-start credit.

    Today's glyph already sits on the now line, so samples stop at yesterday.
    """
    if not daily or starting is None or starting <= 0:
        return []
    points = []
    cumulative = Decimal(0)
    for offset in range(1, period["day"]):
        day_date = period["periodStart"] + timedelta(days=offset - 1)
        cumulative += daily.get(day_date, Decimal(0))
        points.append({"day": offset, "pressure": rounded(cumulative / starting)})
    return points


def fetch_azure_current(timeout):
    subscription_id = azure_subscription_id(timeout)
    try:
        total, currency = fetch_azure_cost_management(subscription_id, timeout)
    except ProviderError as error:
        if azure_throttled(error):
            return fetch_azure_usage_usd(subscription_id, timeout)
        raise
    if currency == "USD":
        return total
    return total / azure_pricing_to_billing_rate(subscription_id, timeout)


def azure_resource_list(payload):
    if isinstance(payload, list):
        return payload
    return payload.get("value") or []


def azure_money_usd(amount, label):
    if not isinstance(amount, dict) or "value" not in amount:
        return None
    currency = str(amount.get("currency") or "USD").upper()
    value = as_decimal(amount.get("value"), label)
    if currency != "USD":
        raise ProviderError(f"{label} returned {currency}; USD is required")
    return value


def azure_parse_credits(payload):
    """Return remaining, starting, and month-to-date spent credit in USD.

    `currentBalance` is credit still posted (the month-start pool once pending
    charges are excluded). `estimatedBalance` is that pool after pending
    eligible charges. Spent this month is starting minus remaining.
    """
    props = payload.get("properties") or {}
    summary = props.get("balanceSummary") or {}
    remaining = azure_money_usd(
        summary.get("estimatedBalance") or {}, "Azure estimated credit"
    )
    starting = azure_money_usd(
        summary.get("currentBalance") or {}, "Azure current credit"
    )
    pending = azure_money_usd(
        props.get("pendingEligibleCharges") or {}, "Azure pending charges"
    )
    spent = None
    if pending is not None:
        spent = max(Decimal(0), -pending)
    if remaining is not None:
        remaining = max(Decimal(0), remaining)
    if starting is not None:
        starting = max(Decimal(0), starting)
    if spent is None and starting is not None and remaining is not None:
        spent = max(Decimal(0), starting - remaining)
    if starting is None and remaining is not None and spent is not None:
        starting = remaining + spent
    if remaining is None and starting is not None and spent is not None:
        remaining = max(Decimal(0), starting - spent)
    if remaining is None and starting is None and spent is None:
        return None
    return {
        "remaining": remaining,
        "starting": starting,
        "spent": spent,
    }


def fetch_azure_credit_balance(timeout):
    accounts = azure_resource_list(
        azure_rest(
            "get",
            "https://management.azure.com/providers/Microsoft.Billing/billingAccounts?api-version=2024-04-01",
            timeout,
        )
    )
    if not accounts:
        raise ProviderError("Azure returned no billing accounts")
    last_error = None
    for account in accounts:
        account_name = str(account.get("name") or "").strip()
        if not account_name:
            continue
        account_id = urllib.parse.quote(account_name, safe="")
        try:
            profiles = azure_resource_list(
                azure_rest(
                    "get",
                    "https://management.azure.com/providers/Microsoft.Billing/billingAccounts/"
                    f"{account_id}/billingProfiles?api-version=2024-04-01",
                    timeout,
                )
            )
        except ProviderError as error:
            last_error = error
            continue
        ranked = sorted(
            profiles,
            key=lambda item: 0
            if str((item.get("properties") or item).get("spendingLimit") or "") == "On"
            else 1,
        )
        for profile in ranked:
            profile_name = str(profile.get("name") or "").strip()
            if not profile_name:
                continue
            try:
                payload = azure_rest(
                    "get",
                    "https://management.azure.com/providers/Microsoft.Billing/billingAccounts/"
                    f"{account_id}/billingProfiles/"
                    f"{urllib.parse.quote(profile_name, safe='')}/providers/"
                    "Microsoft.Consumption/credits/balanceSummary?api-version=2024-08-01",
                    timeout,
                )
            except ProviderError as error:
                last_error = error
                continue
            credits = azure_parse_credits(payload)
            if credits is not None:
                return credits
    raise last_error or ProviderError("Azure credit balance was unavailable")


def azure_provider(period, timeout):
    credits = fetch_azure_credit_balance(timeout)
    spent = credits.get("spent")
    starting = credits.get("starting")
    remaining = credits.get("remaining")
    burn_source = "azure-credits"

    if spent is None:
        try:
            spent = fetch_azure_current(timeout)
            burn_source = "month-to-date-pace"
        except ProviderError as error:
            log_event(
                f"Azure month-to-date spend unavailable: {clean_error(error)}"
            )

    if starting is None and remaining is not None and spent is not None:
        starting = remaining + spent
    if remaining is None and starting is not None and spent is not None:
        remaining = max(Decimal(0), starting - spent)
    if spent is None and starting is not None and remaining is not None:
        spent = max(Decimal(0), starting - remaining)

    if spent is None or starting is None or starting <= 0:
        raise ProviderError("Azure credit summary omitted starting balance or spend")

    history = []
    try:
        history = azure_history_pressures(
            fetch_azure_daily_usd(period, timeout), period, starting
        )
    except ProviderError as error:
        log_event(f"Azure daily spend unavailable: {clean_error(error)}")

    forecast = linear_month_forecast(spent, period)
    forecast = max(spent, forecast)
    projected = max(Decimal(0), starting - forecast)
    return {
        "id": "azure",
        "code": "AZR",
        "name": "Azure",
        "color": AZURE_COLOR,
        "kind": "prepaid",
        "ok": True,
        "stale": False,
        "currentUsd": rounded(spent, 2),
        "capUsd": rounded(starting, 2),
        "balanceUsd": rounded(remaining, 2),
        "dailyBurnUsd": rounded(spent / Decimal(max(period["day"], 1)), 4),
        "forecastUsd": rounded(forecast, 2),
        "projectedBalanceUsd": rounded(projected, 2),
        "currentPressure": rounded(spent / starting),
        "forecastPressure": rounded(forecast / starting),
        "forecastAvailable": True,
        "source": "azure-credits",
        "forecastSource": burn_source,
        "history": history,
        "detail": (
            f"${float(spent):.2f} now · ${float(forecast):.2f} EOM · "
            f"${float(starting):.2f} at month start"
        ),
    }


def fetch_anthropic_current(period, admin_key, timeout):
    now_utc = datetime.now(timezone.utc)
    start_utc = datetime.combine(period["periodStart"], time.min, tzinfo=timezone.utc)
    # Anthropic's daily cost buckets are UTC-aligned. Use the latest completed
    # boundary, matching their cookbook; on the first UTC day of a month, keep
    # a non-empty range so the endpoint can return the partial first bucket.
    end_utc = datetime.combine(now_utc.date(), time.min, tzinfo=timezone.utc)
    if end_utc <= start_utc:
        end_utc = now_utc
    parameters = {
        "starting_at": utc_iso(start_utc),
        "ending_at": utc_iso(end_utc),
        "bucket_width": "1d",
        "limit": 31,
    }
    headers = {
        "anthropic-version": "2023-06-01",
        "x-api-key": admin_key,
    }
    total_cents = Decimal(0)
    page = None
    while True:
        if page:
            parameters["page"] = page
        url = (
            "https://api.anthropic.com/v1/organizations/cost_report?"
            + urllib.parse.urlencode(parameters)
        )
        payload = request_json(url, headers=headers, timeout=timeout)
        for bucket in payload.get("data") or []:
            for item in bucket.get("results") or []:
                currency = str(item.get("currency") or "USD").upper()
                if currency != "USD":
                    raise ProviderError(
                        f"Anthropic returned {currency}; only USD caps are supported"
                    )
                total_cents += as_decimal(item.get("amount", 0), "Anthropic amount")
        if not payload.get("has_more"):
            break
        page = str(payload.get("next_page") or "").strip()
        if not page:
            raise ProviderError("Anthropic pagination omitted next_page")
    return total_cents / Decimal(100)


def fetch_openrouter_credits(api_key, timeout):
    payload = request_json(
        "https://openrouter.ai/api/v1/credits",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )
    data = payload.get("data") or {}
    total_credits = as_decimal(data.get("total_credits"), "OpenRouter total credits")
    total_usage = as_decimal(data.get("total_usage"), "OpenRouter total usage")
    return {
        "totalCredits": total_credits,
        "totalUsage": total_usage,
        "balance": max(Decimal(0), total_credits - total_usage),
    }


def fetch_openrouter_daily_burn(api_key, now, timeout, history_days=30):
    start = now.astimezone(timezone.utc) - timedelta(days=history_days)
    query = {
        "metrics": ["total_usage"],
        "granularity": "day",
        "time_range": {"start": utc_iso(start), "end": utc_iso(now)},
    }
    payload = request_json(
        "https://openrouter.ai/api/v1/analytics/query",
        headers={"Authorization": f"Bearer {api_key}"},
        payload=query,
        timeout=timeout,
    )
    data = payload.get("data") or {}
    rows = data.get("data") if isinstance(data, dict) else data
    metadata = data.get("metadata") if isinstance(data, dict) else {}
    if metadata and metadata.get("truncated"):
        raise ProviderError("OpenRouter analytics response was truncated")
    if not isinstance(rows, list):
        raise ProviderError("OpenRouter analytics response omitted daily rows")
    total = sum(
        (as_decimal(row.get("total_usage") or 0, "OpenRouter daily usage") for row in rows),
        Decimal(0),
    )
    return total / Decimal(history_days)


def load_json(path, fallback):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return fallback


def update_openrouter_history(today, observed_at, credits):
    history = load_json(HISTORY_PATH, {"version": 1, "openrouter": []})
    samples = history.get("openrouter") or []
    cutoff = today - timedelta(days=30)
    kept = []
    for sample in samples:
        try:
            sample_date = date.fromisoformat(str(sample.get("date") or ""))
        except ValueError:
            continue
        if sample_date >= cutoff and sample_date != today:
            kept.append(sample)
    kept.append(
        {
            "date": today.isoformat(),
            "observedAt": observed_at,
            "totalUsageUsd": rounded(credits.get("totalUsage"), 6),
            "balanceUsd": rounded(credits.get("balance"), 6),
        }
    )
    kept.sort(key=lambda sample: sample["date"])
    output = {"version": 1, "openrouter": kept}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.atomic_write_json(HISTORY_PATH, output)
    return kept


def burn_from_local_history(samples):
    if len(samples) < 2:
        return None, 0
    latest = samples[-1]
    latest_date = date.fromisoformat(latest["date"])
    latest_usage = latest.get("totalUsageUsd")
    for earliest in samples:
        earliest_usage = earliest.get("totalUsageUsd")
        if latest_usage is None or earliest_usage is None:
            continue
        earliest_date = date.fromisoformat(earliest["date"])
        span = (latest_date - earliest_date).days
        if span < 1:
            continue
        delta = Decimal(str(latest_usage)) - Decimal(str(earliest_usage))
        if delta >= 0:
            return delta / Decimal(span), span
    return None, 0


def openrouter_provider(period, timeout, observed_at):
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is required")
    credits = fetch_openrouter_credits(api_key, timeout)
    balance_source = "openrouter-credits"

    samples = update_openrouter_history(
        period["today"], observed_at, credits
    )
    history_days = 0
    daily_burn = None
    try:
        daily_burn = fetch_openrouter_daily_burn(
            api_key, period["localNow"], timeout
        )
        history_days = 30
        burn_source = "openrouter-analytics-30d"
    except ProviderError as error:
        log_event(f"OpenRouter analytics unavailable; using local history: {clean_error(error)}")
    if daily_burn is None:
        daily_burn, history_days = burn_from_local_history(samples)
        burn_source = "local-observation-history"

    balance = credits["balance"]
    forecast_available = daily_burn is not None
    future_draw = (
        daily_burn * Decimal(period["daysRemaining"])
        if forecast_available
        else None
    )
    if not forecast_available:
        forecast_pressure = Decimal(0)
        projected_balance = balance
        detail = f"${float(balance):.2f} left · collecting burn history"
    elif balance > 0:
        forecast_pressure = future_draw / balance
        projected_balance = max(Decimal(0), balance - future_draw)
        detail = (
            f"${float(balance):.2f} left · ${float(daily_burn):.2f}/day · "
            f"${float(projected_balance):.2f} at EOM"
        )
    else:
        forecast_pressure = Decimal("1.12") if future_draw > 0 else Decimal(0)
        projected_balance = Decimal(0)
        detail = "$0.00 left"

    return {
        "id": "openrouter",
        "code": "OR",
        "name": "OpenRouter",
        "color": OPENROUTER_COLOR,
        "kind": "prepaid",
        "ok": True,
        "stale": False,
        "currentUsd": 0.0,
        "capUsd": rounded(balance, 2),
        "balanceUsd": rounded(balance, 2),
        "dailyBurnUsd": rounded(daily_burn, 4),
        "historyDays": history_days,
        "forecastUsd": rounded(future_draw, 2),
        "projectedBalanceUsd": rounded(projected_balance, 2),
        "currentPressure": 0.0,
        "forecastPressure": rounded(forecast_pressure),
        "forecastAvailable": forecast_available,
        "source": balance_source,
        "forecastSource": burn_source,
        "detail": detail,
    }


def github_api(path, timeout):
    return run_json(
        [
            "gh",
            "api",
            "--method",
            "GET",
            "-H",
            "Accept: application/vnd.github+json",
            "-H",
            f"X-GitHub-Api-Version: {GITHUB_API_VERSION}",
            path,
        ],
        timeout,
    )


def normalized_github_sku(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def github_actions_allowance(identity):
    plan = str(((identity.get("plan") or {}).get("name") or "")).lower()
    allowance = GITHUB_ACTIONS_PLAN_MINUTES.get(plan)
    if allowance is None:
        label = plan or "unknown"
        raise ProviderError(f"GitHub plan {label} has no known Actions allowance")
    return plan, allowance


def github_repository_path(login, repository_name):
    name = str(repository_name or "").strip().strip("/")
    if not name:
        return None
    parts = name.split("/", 1)
    if len(parts) == 1:
        owner, repository = login, parts[0]
    else:
        owner, repository = parts
    if not owner or not repository:
        return None
    return "/repos/{}/{}".format(
        urllib.parse.quote(owner, safe=""),
        urllib.parse.quote(repository, safe=""),
    )


def github_repository_is_public(login, repository_name, timeout):
    path = github_repository_path(login, repository_name)
    if path is None:
        raise ProviderError("GitHub usage row omitted its repository")
    repository = github_api(path, timeout)
    visibility = str(repository.get("visibility") or "").lower()
    if visibility:
        return visibility == "public"
    if "private" in repository:
        return not bool(repository["private"])
    raise ProviderError(
        f"GitHub repository metadata omitted visibility for {repository_name}"
    )


def github_actions_provider(period, timeout):
    identity = github_api("/user", timeout)
    login = str(identity.get("login") or "").strip()
    if not login:
        raise ProviderError("GitHub identity omitted login")
    plan, allowance = github_actions_allowance(identity)

    query = urllib.parse.urlencode(
        {"year": period["today"].year, "month": period["today"].month}
    )
    usage_path = (
        f"/users/{urllib.parse.quote(login, safe='')}/settings/billing/usage?{query}"
    )
    payload = github_api(usage_path, timeout)

    minutes_by_repository = {}
    current_payable = Decimal(0)
    for item in payload.get("usageItems") or []:
        if str(item.get("product") or "").lower() != "actions":
            continue
        current_payable += as_decimal(
            item.get("netAmount", 0), "GitHub Actions net amount"
        )
        if str(item.get("unitType") or "").lower() != "minutes":
            continue
        if normalized_github_sku(item.get("sku")) not in GITHUB_ACTIONS_STANDARD_SKUS:
            continue
        repository_name = str(item.get("repositoryName") or "").strip()
        quantity = max(
            Decimal(0),
            as_decimal(item.get("quantity", 0), "GitHub Actions minutes"),
        )
        minutes_by_repository[repository_name] = (
            minutes_by_repository.get(repository_name, Decimal(0)) + quantity
        )

    included_usage = Decimal(0)
    public_minutes = Decimal(0)
    visibility_unknown = []
    for repository_name in sorted(minutes_by_repository):
        quantity = minutes_by_repository[repository_name]
        try:
            is_public = github_repository_is_public(login, repository_name, timeout)
        except ProviderError:
            # Deleted or inaccessible repositories cannot be classified. Count
            # them conservatively so the warning map never understates risk.
            visibility_unknown.append(repository_name or "unknown")
            is_public = False
        if is_public:
            public_minutes += quantity
        else:
            included_usage += quantity

    forecast = max(included_usage, linear_month_forecast(included_usage, period))
    current_payable = max(Decimal(0), current_payable)
    detail = (
        f"{float(included_usage):,.0f} / {float(allowance):,.0f} min · "
        f"{float(forecast):,.0f} EOM · ${float(current_payable):.2f} due"
    )
    if visibility_unknown:
        detail += f" · {len(visibility_unknown)} repo visibility unknown"

    return {
        "id": "github_actions",
        "code": "GH",
        "name": "GitHub Actions",
        "color": GITHUB_ACTIONS_COLOR,
        "kind": "allowance",
        "ok": True,
        "stale": False,
        "plan": plan,
        "currentMinutes": rounded(included_usage, 2),
        "includedMinutes": rounded(allowance, 2),
        "forecastMinutes": rounded(forecast, 2),
        "publicMinutesExcluded": rounded(public_minutes, 2),
        "currentPayableUsd": rounded(current_payable, 2),
        "visibilityUnknownRepositories": visibility_unknown,
        "currentPressure": rounded(included_usage / allowance),
        "forecastPressure": rounded(forecast / allowance),
        "forecastAvailable": True,
        "source": "github-billing-usage",
        "forecastSource": "linear-month-pace",
        "detail": detail,
    }


def configured(*names):
    return any(os.environ.get(name, "").strip() for name in names)


def previous_providers():
    output = load_json(STATUS_PATH, {})
    return {
        str(item.get("id")): item
        for item in output.get("providers") or []
        if item.get("id")
    }


def stale_provider(previous, error):
    item = dict(previous)
    item["stale"] = True
    item["error"] = clean_error(error)
    return item


def collect(reference=None):
    common.load_env()
    period = month_period(reference)
    observed_at = utc_iso(datetime.now(timezone.utc))
    try:
        timeout = int(os.environ.get("BILLING_TIMEOUT_SECONDS", "30"))
    except ValueError:
        timeout = 30
    timeout = max(2, min(timeout, 120))

    providers = []
    errors = []
    old = previous_providers()

    def add_metered(provider_id, code, name, color, current_fetcher, config_names):
        if not configured(*config_names):
            return
        try:
            cap = env_decimal(f"BILLING_{provider_id.upper()}_CAP_USD", allow_zero=False)
            if cap is None:
                raise ValueError(
                    f"BILLING_{provider_id.upper()}_CAP_USD is required"
                )
            current = current_fetcher(period, timeout)
            providers.append(
                metered_provider(
                    provider_id,
                    code,
                    name,
                    color,
                    cap,
                    current,
                    period,
                    provider_id,
                )
            )
        except Exception as error:
            message = clean_error(error)
            errors.append({"provider": provider_id, "error": message})
            if provider_id in old:
                providers.append(stale_provider(old[provider_id], error))

    add_metered(
        "aws",
        "AWS",
        "AWS",
        AWS_COLOR,
        fetch_aws_current,
        (
            "BILLING_AWS_CAP_USD",
            "BILLING_AWS_PROFILE",
        ),
    )

    if env_flag("BILLING_AZURE_ENABLED") or configured("BILLING_AZURE_SUBSCRIPTION_ID"):
        try:
            providers.append(azure_provider(period, timeout))
        except Exception as error:
            message = clean_error(error)
            errors.append({"provider": "azure", "error": message})
            if "azure" in old:
                providers.append(stale_provider(old["azure"], error))

    anthropic_key = (
        os.environ.get("ANTHROPIC_ADMIN_KEY", "").strip()
        or os.environ.get("ANTHROPIC_ADMIN_API_KEY", "").strip()
    )
    if configured(
        "BILLING_ANTHROPIC_CAP_USD",
        "ANTHROPIC_ADMIN_KEY",
        "ANTHROPIC_ADMIN_API_KEY",
    ):
        try:
            cap = env_decimal("BILLING_ANTHROPIC_CAP_USD", allow_zero=False)
            if cap is None:
                raise ValueError("BILLING_ANTHROPIC_CAP_USD is required")
            if not anthropic_key:
                raise ValueError("ANTHROPIC_ADMIN_KEY is required")
            current = fetch_anthropic_current(period, anthropic_key, timeout)
            providers.append(
                metered_provider(
                    "anthropic",
                    "ANT",
                    "Anthropic",
                    ANTHROPIC_COLOR,
                    cap,
                    current,
                    period,
                    "anthropic-cost-report",
                )
            )
        except Exception as error:
            message = clean_error(error)
            errors.append({"provider": "anthropic", "error": message})
            if "anthropic" in old:
                providers.append(stale_provider(old["anthropic"], error))

    if configured("OPENROUTER_API_KEY"):
        try:
            providers.append(openrouter_provider(period, timeout, observed_at))
        except Exception as error:
            message = clean_error(error)
            errors.append({"provider": "openrouter", "error": message})
            if "openrouter" in old:
                providers.append(stale_provider(old["openrouter"], error))

    if env_flag("BILLING_GITHUB_ACTIONS_ENABLED"):
        try:
            providers.append(github_actions_provider(period, timeout))
        except Exception as error:
            message = clean_error(error)
            errors.append({"provider": "github_actions", "error": message})
            if "github_actions" in old:
                providers.append(stale_provider(old["github_actions"], error))

    provider_order = {
        "aws": 0,
        "anthropic": 1,
        "openrouter": 2,
        "github_actions": 3,
        "azure": 4,
    }
    providers.sort(key=lambda item: provider_order.get(item.get("id"), 99))
    if not providers and not errors:
        errors.append(
            {
                "provider": "configuration",
                "error": (
                    "No billing providers configured; set a provider cap, OpenRouter key, "
                    "or enable Azure / GitHub Actions"
                ),
            }
        )

    return {
        "ok": bool(providers),
        "updatedAt": observed_at,
        "periodStart": period["periodStart"].isoformat(),
        "periodEnd": period["periodEnd"].isoformat(),
        "periodEndExclusive": period["periodEndExclusive"].isoformat(),
        "periodLabel": period["periodLabel"],
        "endLabel": period["endLabel"],
        "day": period["day"],
        "daysInMonth": period["daysInMonth"],
        "daysRemaining": period["daysRemaining"],
        "elapsedFraction": rounded(period["elapsedFraction"], 6),
        "providers": providers,
        "errors": errors,
        "error": errors[0]["error"] if errors else "",
    }


def render_tsv(output):
    meta = [
        "meta",
        "ok",
        "1" if output.get("ok") else "0",
        "updatedAt",
        common.escape_tsv(output.get("updatedAt", "")),
        "periodStart",
        output.get("periodStart", ""),
        "periodEnd",
        output.get("periodEnd", ""),
        "day",
        str(output.get("day", 1)),
        "daysInMonth",
        str(output.get("daysInMonth", 31)),
        "daysRemaining",
        str(output.get("daysRemaining", 0)),
        "elapsedFraction",
        str(output.get("elapsedFraction", 0)),
        "error",
        common.escape_tsv(output.get("error", "")),
    ]
    lines = ["\t".join(meta)]
    for item in output.get("providers") or []:
        lines.append(
            "\t".join(
                [
                    "provider",
                    common.escape_tsv(item.get("id", "")),
                    common.escape_tsv(item.get("code", "")),
                    common.escape_tsv(item.get("color", "")),
                    common.escape_tsv(item.get("kind", "")),
                    "1" if item.get("ok") else "0",
                    "1" if item.get("stale") else "0",
                    str(item.get("currentPressure", 0)),
                    str(item.get("forecastPressure", 0)),
                    "1" if item.get("forecastAvailable") else "0",
                    common.escape_tsv(item.get("source", "")),
                    common.escape_tsv(item.get("detail", "")),
                ]
            )
        )
        for sample in item.get("history") or []:
            lines.append(
                "\t".join(
                    [
                        "history",
                        common.escape_tsv(item.get("id", "")),
                        str(sample.get("day", "")),
                        str(sample.get("pressure", 0)),
                    ]
                )
            )
    return "\n".join(lines) + "\n"


def write_output(output):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.atomic_write_json(STATUS_PATH, output)
    common.atomic_write_text(RENDER_PATH, render_tsv(output))


def main():
    try:
        output = collect()
        write_output(output)
        if output["ok"]:
            log_event(
                f"updated {len(output['providers'])} provider(s) for {output['periodEnd']}"
            )
            return 0
        log_event(output.get("error") or "no billing providers available")
        return 1
    except Exception as error:
        message = clean_error(error)
        log_event(message)
        period = month_period()
        output = {
            "ok": False,
            "updatedAt": utc_iso(datetime.now(timezone.utc)),
            "periodStart": period["periodStart"].isoformat(),
            "periodEnd": period["periodEnd"].isoformat(),
            "periodEndExclusive": period["periodEndExclusive"].isoformat(),
            "periodLabel": period["periodLabel"],
            "endLabel": period["endLabel"],
            "day": period["day"],
            "daysInMonth": period["daysInMonth"],
            "daysRemaining": period["daysRemaining"],
            "elapsedFraction": rounded(period["elapsedFraction"], 6),
            "providers": [],
            "errors": [{"provider": "fetcher", "error": message}],
            "error": message,
        }
        write_output(output)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

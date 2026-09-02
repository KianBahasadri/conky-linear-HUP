#!/usr/bin/env python3
"""Collect month-to-date billing data for the affine billing map.

Metered AWS spend is normalized against the live monthly COST budget.
OpenRouter is prepaid against remaining credit. Azure is prepaid against the
credit pool the current month started with: month-to-date spend is the
current point, and calendar pace projects that spend through the same month
end.

Every successful collect stores that day's observation. The map's solid past
trail is that growing series; missing days are not invented.
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
AWS_CACHE_PATH = CACHE_DIR / "billing-aws-cache.json"
AZURE_CACHE_PATH = CACHE_DIR / "billing-azure-cache.json"
LOG_PATH = CACHE_DIR / "conky-billing.log"
DEFAULT_AWS_CACHE_TTL_SECONDS = 86400  # 24 hours (AWS data updates once daily; $0.01 per query)
AZURE_DAILY_COST_COOLDOWN_SECONDS = 6 * 60 * 60

AWS_COLOR = "ffb454"
AZURE_COLOR = "38bdf8"
OPENROUTER_COLOR = "c8ff00"
GITHUB_ACTIONS_COLOR = "4ade80"
BLACKSMITH_COLOR = "f0fb29"
BLACKSMITH_FREE_MINUTES = Decimal("3000")
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


def is_rate_limited(error):
    text = str(error).lower()
    return any(
        signal in text
        for signal in (
            "429",
            "too many requests",
            "rate limit",
            "ratelimit",
            "throttl",
            "quota exceeded",
            "requestlimitexceeded",
            "provisionedthroughputexceeded",
            "bandwidth limit exceeded",
        )
    )


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
    if not result.stdout.strip():
        return {}
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
        if code == 429:
            suffix += " [Rate Limit / Too Many Requests]"
        elif code == 403:
            suffix += " [Forbidden / Rate Limit Exceeded]"
        raise ProviderError(f"request failed{suffix}: {error.__class__.__name__}") from error


def forecast_decay():
    raw = os.environ.get("BILLING_FORECAST_DECAY", "").strip()
    if raw:
        try:
            value = Decimal(raw)
            if Decimal(0) < value < Decimal(1):
                return value
        except (InvalidOperation, ValueError):
            pass
    raw_half = os.environ.get("BILLING_FORECAST_HALF_LIFE_DAYS", "").strip()
    half = None
    if raw_half:
        try:
            half = Decimal(raw_half)
            if half <= 0:
                half = None
        except (InvalidOperation, ValueError):
            half = None
    if half is None:
        half = Decimal(2)
    import math

    decay_float = math.pow(0.5, 1.0 / float(half))
    return Decimal(str(decay_float))


def _history_day_count(history, period):
    count = 0
    by_day = {}
    for sample in history:
        try:
            day = int(sample.get("day"))
            pressure = Decimal(str(sample.get("pressure")))
        except (TypeError, ValueError, InvalidOperation):
            continue
        if 1 <= day < period["day"]:
            by_day[day] = pressure
    count = len(by_day)
    if count:
        return count
    return 1 if not history else max(1, len(history))


def weighted_pressure_rate(current_pressure, history, period):
    if not history:
        return None
    if _history_day_count(history, period) < 3:
        return None
    try:
        cur = Decimal(str(current_pressure))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if cur < 0:
        cur = Decimal(0)
    pressure_by_day = {}
    for sample in history:
        try:
            day = int(sample.get("day"))
            pressure = Decimal(str(sample.get("pressure")))
        except (TypeError, ValueError, InvalidOperation):
            continue
        if 1 <= day < period["day"]:
            pressure_by_day[day] = pressure
    observed = [(0, Decimal(0))]
    for day in sorted(pressure_by_day):
        observed.append((day, pressure_by_day[day]))
    observed.append((period["day"], cur))
    observed.sort(key=lambda item: item[0])
    for idx in range(1, len(observed)):
        if observed[idx][1] < observed[idx - 1][1]:
            observed[idx] = (observed[idx][0], observed[idx - 1][1])
    decay = forecast_decay()
    try:
        decay_dec = Decimal(str(decay))
    except (InvalidOperation, ValueError):
        return None
    if not (Decimal(0) < decay_dec < Decimal(1)):
        return None
    weighted_sum = Decimal(0)
    weight_sum = Decimal(0)
    for idx in range(1, len(observed)):
        prev_day, prev_pressure = observed[idx - 1]
        cur_day, cur_pressure_point = observed[idx]
        gap = cur_day - prev_day
        if gap <= 0:
            continue
        delta = cur_pressure_point - prev_pressure
        if delta < 0:
            delta = Decimal(0)
        daily = delta / Decimal(gap)
        for offset in range(1, gap + 1):
            day_number = prev_day + offset
            days_ago = period["day"] - day_number
            weight = decay_dec ** days_ago if days_ago > 0 else Decimal(1)
            weighted_sum += daily * weight
            weight_sum += weight
    if weight_sum == 0:
        return None
    return weighted_sum / weight_sum


def weighted_month_forecast(current, period, history, cap):
    if cap is None or cap <= 0:
        return None
    try:
        cur_dec = Decimal(str(current))
        cap_dec = Decimal(str(cap))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if cap_dec <= 0:
        return None
    current_pressure = cur_dec / cap_dec if cap_dec != 0 else Decimal(0)
    rate = weighted_pressure_rate(current_pressure, history, period)
    if rate is None:
        return None
    forecast_pressure = current_pressure + rate * Decimal(period["daysRemaining"])
    if forecast_pressure < current_pressure:
        forecast_pressure = current_pressure
    return forecast_pressure * cap_dec


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
    history=None,
):
    if cap is None or cap <= 0:
        raise ValueError(f"{provider_id} cap must be greater than zero")
    current = max(Decimal(0), current)
    weighted = None
    if history is not None:
        try:
            weighted = weighted_month_forecast(current, period, history, cap)
        except Exception:
            weighted = None
    if weighted is not None:
        forecast = max(current, weighted)
        forecast_source = "weighted-daily-pace"
    else:
        forecast = linear_month_forecast(current, period)
        forecast = max(current, forecast)
        forecast_source = "linear-month-pace"
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
        "forecastSource": forecast_source,
        "detail": f"${float(current):.2f} now · ${float(forecast):.2f} EOM · ${float(cap):.2f} cap",
    }


AWS_BILLING_REGION = "us-east-1"


def aws_session_kwargs():
    """Explicit IAM keys win; otherwise an AWS profile; otherwise the default chain."""
    key = os.environ.get("BILLING_AWS_ACCESS_KEY_ID", "").strip()
    secret = os.environ.get("BILLING_AWS_SECRET_ACCESS_KEY", "").strip()
    profile = os.environ.get("BILLING_AWS_PROFILE", "").strip()
    if key and secret:
        return {
            "aws_access_key_id": key,
            "aws_secret_access_key": secret,
        }
    if profile:
        return {"profile_name": profile}
    return {}


def load_boto3():
    try:
        import boto3
        from botocore.config import Config
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as error:
        raise ProviderError(
            "boto3 is not installed; run uv sync from the repo root"
        ) from error
    return boto3, Config, (BotoCoreError, ClientError)


def aws_client(service, timeout, *, region=AWS_BILLING_REGION):
    boto3, Config, errors = load_boto3()
    config = Config(
        connect_timeout=timeout,
        read_timeout=timeout,
        retries={"max_attempts": 2, "mode": "standard"},
    )
    try:
        session = boto3.Session(**aws_session_kwargs())
        return session.client(service, region_name=region, config=config)
    except errors as error:
        raise ProviderError(
            f"AWS {service} client failed: {clean_error(error)}"
        ) from error


def aws_try(action, fn):
    try:
        return fn()
    except ProviderError:
        raise
    except Exception as error:
        raise ProviderError(f"AWS {action} failed: {clean_error(error)}") from error


def aws_paginate(client, operation, result_key, **kwargs):
    def collect():
        can_paginate = getattr(client, "can_paginate", None)
        if callable(can_paginate) and can_paginate(operation):
            items = []
            for page in client.get_paginator(operation).paginate(**kwargs):
                items.extend(page.get(result_key) or [])
            return items
        payload = getattr(client, operation)(**kwargs)
        return payload.get(result_key) or []

    return aws_try(operation, collect)


def aws_account_id(timeout):
    client = aws_client("sts", timeout)
    payload = aws_try("get_caller_identity", client.get_caller_identity)
    account = str(payload.get("Account") or "").strip()
    if not re.fullmatch(r"\d{12}", account):
        raise ProviderError("AWS identity omitted a 12-digit account id")
    return account


def aws_budget_is_account_wide(budget):
    """True for an unfiltered monthly cost budget, including the console default.

    The Billing console's default COST budget excludes Credit and Refund
    record types and is still an account-wide surprise-bill ceiling.
    """
    cost_filters = budget.get("CostFilters") or {}
    if any(cost_filters.values()):
        return False
    expression = budget.get("FilterExpression") or {}
    if not expression:
        return True
    extra = set(expression) - {"Not"}
    if extra:
        return False
    dimensions = (expression.get("Not") or {}).get("Dimensions") or {}
    key = str(dimensions.get("Key") or "")
    values = {str(value) for value in (dimensions.get("Values") or [])}
    return key == "RECORD_TYPE" and values and values <= {"Credit", "Refund"}


def select_aws_monthly_cost_budget(budgets, named=""):
    """Pick a monthly COST USD budget. Named wins; otherwise the smallest account-wide limit."""
    rows = [item for item in budgets or [] if isinstance(item, dict)]
    if named:
        match = next((item for item in rows if item.get("BudgetName") == named), None)
        if match is None:
            raise ProviderError(f"AWS budget {named!r} was not found")
        rows = [match]
    else:
        rows = [item for item in rows if aws_budget_is_account_wide(item)]

    candidates = []
    for item in rows:
        if str(item.get("BudgetType") or "").upper() != "COST":
            continue
        if str(item.get("TimeUnit") or "").upper() != "MONTHLY":
            continue
        limit = item.get("BudgetLimit") or {}
        unit = str(limit.get("Unit") or "USD").upper()
        if unit != "USD":
            continue
        amount = as_decimal(limit.get("Amount"), "AWS budget")
        if amount <= 0:
            continue
        name = str(item.get("BudgetName") or "").strip()
        candidates.append((amount, name))

    if named and not candidates:
        raise ProviderError(f"AWS budget {named!r} is not a monthly COST USD budget")
    if not candidates:
        raise ProviderError("no monthly account-wide COST budget in USD")
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0]


def select_aws_billing_alarm_threshold(alarms):
    """Smallest account-wide CloudWatch EstimatedCharges GreaterThan threshold."""
    thresholds = []
    for alarm in alarms or []:
        if not isinstance(alarm, dict):
            continue
        if str(alarm.get("Namespace") or "") != "AWS/Billing":
            continue
        if str(alarm.get("MetricName") or "") != "EstimatedCharges":
            continue
        comparison = str(alarm.get("ComparisonOperator") or "")
        if comparison not in {
            "GreaterThanThreshold",
            "GreaterThanOrEqualToThreshold",
        }:
            continue
        dimensions = {
            str(item.get("Name") or ""): str(item.get("Value") or "")
            for item in (alarm.get("Dimensions") or [])
            if isinstance(item, dict)
        }
        if "ServiceName" in dimensions:
            continue
        currency = str(dimensions.get("Currency") or "USD").upper()
        if currency != "USD":
            continue
        threshold = as_decimal(alarm.get("Threshold"), "AWS billing alarm")
        if threshold > 0:
            thresholds.append(threshold)
    if not thresholds:
        raise ProviderError("no account-wide CloudWatch billing alarm in USD")
    return min(thresholds)


def fetch_aws_budget_cap(timeout):
    named = os.environ.get("BILLING_AWS_BUDGET_NAME", "").strip()
    client = aws_client("budgets", timeout)
    budgets = aws_paginate(
        client,
        "describe_budgets",
        "Budgets",
        AccountId=aws_account_id(timeout),
    )
    return select_aws_monthly_cost_budget(budgets, named)


def fetch_aws_billing_alarm_cap(timeout):
    client = aws_client("cloudwatch", timeout, region=AWS_BILLING_REGION)
    alarms = aws_paginate(client, "describe_alarms", "MetricAlarms")
    return select_aws_billing_alarm_threshold(alarms)


def resolve_aws_cap(timeout):
    try:
        amount, name = fetch_aws_budget_cap(timeout)
        return amount, "aws-budgets", name
    except ProviderError as budget_error:
        try:
            return fetch_aws_billing_alarm_cap(timeout), "aws-billing-alarm", ""
        except ProviderError as alarm_error:
            raise ProviderError(
                f"{clean_error(budget_error)}; {clean_error(alarm_error)}"
            ) from alarm_error


def fetch_aws_current(period, timeout):
    query_end = min(period["today"] + timedelta(days=1), period["periodEndExclusive"])
    client = aws_client("ce", timeout)
    payload = aws_try(
        "get_cost_and_usage",
        lambda: client.get_cost_and_usage(
            TimePeriod={
                "Start": period["periodStart"].isoformat(),
                "End": query_end.isoformat(),
            },
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        ),
    )
    rows = payload.get("ResultsByTime") or []
    if not rows:
        return Decimal(0)
    value = ((rows[0].get("Total") or {}).get("UnblendedCost") or {})
    unit = str(value.get("Unit") or "USD").upper()
    if unit != "USD":
        raise ProviderError(f"AWS returned {unit}; only USD caps are supported")
    return as_decimal(value.get("Amount", 0), "AWS amount")


def aws_enabled():
    return env_flag("BILLING_AWS_ENABLED") or configured(
        "BILLING_AWS_ACCESS_KEY_ID",
        "BILLING_AWS_SECRET_ACCESS_KEY",
        "BILLING_AWS_PROFILE",
        "BILLING_AWS_BUDGET_NAME",
    )


def aws_cache_ttl_seconds():
    raw = os.environ.get("BILLING_AWS_CACHE_TTL_SECONDS", "").strip()
    if not raw:
        raw = os.environ.get("BILLING_AWS_REFRESH_SECONDS", "").strip()
    if raw:
        try:
            return max(60, int(raw))
        except ValueError:
            pass
    return DEFAULT_AWS_CACHE_TTL_SECONDS


def load_aws_cache():
    return load_json(AWS_CACHE_PATH, {})


def save_aws_cache(data):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.atomic_write_json(AWS_CACHE_PATH, data)


def aws_provider(period, timeout, force=False):
    cache = load_aws_cache() if not force else {}
    ttl = aws_cache_ttl_seconds()
    now_epoch = int(period["localNow"].astimezone(timezone.utc).timestamp())
    today_iso = period["today"].isoformat()

    cached_epoch = cache.get("fetchedEpoch")
    cached_start = cache.get("periodStart")
    cached_date = cache.get("date")
    cached_current = cache.get("currentUsd")
    cached_cap = cache.get("capUsd")
    cached_cap_source = cache.get("capSource", "aws-budgets")
    cached_budget_name = cache.get("budgetName", "")

    is_valid_cache = (
        not force
        and isinstance(cached_epoch, (int, float))
        and (now_epoch - cached_epoch) < ttl
        and cached_start == period["periodStart"].isoformat()
        and cached_date == today_iso
        and cached_current is not None
        and cached_cap is not None
    )

    if is_valid_cache:
        cap = Decimal(str(cached_cap))
        current = Decimal(str(cached_current))
        age_seconds = max(0, now_epoch - int(cached_epoch))
        log_event(
            f"AWS: using daily cached usage from {cached_date} "
            f"(TTL {ttl}s, age {age_seconds}s; ${float(current):.2f} / ${float(cap):.2f})"
        )
        store = load_observation_history()
        history = map_history_from_store(store, "aws", period)
        provider = metered_provider(
            "aws",
            "AWS",
            "AWS",
            AWS_COLOR,
            cap,
            current,
            period,
            "aws-cached",
            history=history,
        )
        provider["capSource"] = cached_cap_source
        if cached_budget_name:
            provider["budgetName"] = cached_budget_name
        return provider

    log_event("AWS: daily refresh needed or no cache; fetching fresh cost & budget data from AWS APIs...")
    cap, cap_source, budget_name = resolve_aws_cap(timeout)
    current = fetch_aws_current(period, timeout)
    store = load_observation_history()
    history = map_history_from_store(store, "aws", period)
    provider = metered_provider(
        "aws",
        "AWS",
        "AWS",
        AWS_COLOR,
        cap,
        current,
        period,
        "aws",
        history=history,
    )
    provider["capSource"] = cap_source
    if budget_name:
        provider["budgetName"] = budget_name

    save_aws_cache(
        {
            "fetchedAt": utc_iso(period["localNow"].astimezone(timezone.utc)),
            "fetchedEpoch": now_epoch,
            "date": today_iso,
            "periodStart": period["periodStart"].isoformat(),
            "capUsd": rounded(cap, 2),
            "capSource": cap_source,
            "budgetName": budget_name,
            "currentUsd": rounded(current, 2),
        }
    )
    log_event(
        f"AWS: fresh fetch succeeded: current spend ${provider['currentUsd']} / cap ${provider['capUsd']} ({cap_source})"
    )
    return provider


def azure_throttled(error):
    return is_rate_limited(error)


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


def azure_daily_cost_management_in_cooldown(subscription_id, now_epoch=None):
    state = load_json(AZURE_CACHE_PATH, {})
    if state.get("subscriptionId") != subscription_id:
        return False
    now_epoch = now_epoch or int(datetime.now(timezone.utc).timestamp())
    return common.as_int(state.get("dailyCostRetryAfterEpoch")) > now_epoch


def start_azure_daily_cost_cooldown(subscription_id, now_epoch=None):
    now_epoch = now_epoch or int(datetime.now(timezone.utc).timestamp())
    retry_after = now_epoch + AZURE_DAILY_COST_COOLDOWN_SECONDS
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        common.atomic_write_json(
            AZURE_CACHE_PATH,
            {
                "subscriptionId": subscription_id,
                "dailyCostThrottledAtEpoch": now_epoch,
                "dailyCostRetryAfterEpoch": retry_after,
            },
        )
    except OSError as error:
        log_event(f"Azure daily throttle cooldown cache write failed: {clean_error(error)}")
    return retry_after


def clear_azure_daily_cost_cooldown(subscription_id):
    state = load_json(AZURE_CACHE_PATH, {})
    if state.get("subscriptionId") == subscription_id:
        try:
            common.atomic_write_json(AZURE_CACHE_PATH, {})
        except OSError as error:
            log_event(f"Azure daily throttle cooldown cache clear failed: {clean_error(error)}")


def fetch_azure_daily_usd(period, timeout):
    subscription_id = azure_subscription_id(timeout)
    if azure_daily_cost_management_in_cooldown(subscription_id):
        return fetch_azure_usage_by_day(subscription_id, timeout, period)
    try:
        payload = azure_cost_management_payload(subscription_id, timeout, "Daily")
        daily, currency = parse_azure_daily_cost_query(payload)
        if currency != "USD" and daily:
            rate = azure_pricing_to_billing_rate(subscription_id, timeout)
            daily = {day: amount / rate for day, amount in daily.items()}
        if daily:
            clear_azure_daily_cost_cooldown(subscription_id)
            return daily
    except ProviderError as error:
        if is_rate_limited(error):
            retry_after = start_azure_daily_cost_cooldown(subscription_id)
            retry_at = datetime.fromtimestamp(retry_after, tz=timezone.utc).isoformat()
            log_event(
                "RATE LIMIT / THROTTLED: Azure daily Cost Management throttled: "
                f"{clean_error(error)}; using Usage Details until retry_at={retry_at}"
            )
        else:
            log_event(f"Azure daily Cost Management unavailable: {clean_error(error)}; falling back to Usage Details")
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
            log_event(f"RATE LIMIT / THROTTLED: Azure Cost Management throttled ({clean_error(error)}); falling back to Usage Details")
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
    log_event("Azure: fetching credit balance and usage data...")
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

    current_pressure = spent / starting if starting else Decimal(0)
    weighted_rate = weighted_pressure_rate(current_pressure, history, period)
    if weighted_rate is not None:
        forecast_pressure = current_pressure + weighted_rate * Decimal(period["daysRemaining"])
        if forecast_pressure < current_pressure:
            forecast_pressure = current_pressure
        forecast = forecast_pressure * starting
        forecast_source = "weighted-daily-pace"
    else:
        forecast = linear_month_forecast(spent, period)
        forecast = max(spent, forecast)
        forecast_pressure = forecast / starting if starting else Decimal(0)
        forecast_source = burn_source
    projected = max(Decimal(0), starting - forecast)
    provider = {
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
        "dailyBurnUsd": rounded(weighted_rate * starting if weighted_rate is not None else spent / Decimal(max(period["day"], 1)), 4) if starting else rounded(spent / Decimal(max(period["day"], 1)), 4),
        "forecastUsd": rounded(forecast, 2),
        "projectedBalanceUsd": rounded(projected, 2),
        "currentPressure": rounded(current_pressure),
        "forecastPressure": rounded(forecast_pressure),
        "forecastAvailable": True,
        "source": "azure-credits",
        "forecastSource": forecast_source,
        "history": history,
        "detail": (
            f"${float(spent):.2f} now · ${float(forecast):.2f} EOM · "
            f"${float(starting):.2f} at month start"
        ),
    }
    log_event(
        f"Azure: fresh fetch succeeded: spent ${provider['currentUsd']} / starting balance ${provider['capUsd']} (remaining ${provider['balanceUsd']})"
    )
    return provider


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


def history_retention_cutoff(today):
    return min(today.replace(day=1), today - timedelta(days=30))


def load_observation_history():
    raw = load_json(HISTORY_PATH, {})
    providers = {}
    stored = raw.get("providers")
    if isinstance(stored, dict):
        for provider_id, samples in stored.items():
            if isinstance(samples, list):
                providers[str(provider_id)] = [
                    dict(sample)
                    for sample in samples
                    if isinstance(sample, dict)
                ]
    # v1 files kept OpenRouter samples at the top level.
    if "openrouter" not in providers and isinstance(raw.get("openrouter"), list):
        providers["openrouter"] = [
            dict(sample) for sample in raw["openrouter"] if isinstance(sample, dict)
        ]
    return providers


def upsert_observation(store, provider_id, sample_date, observed_at, fields):
    samples = store.setdefault(provider_id, [])
    iso = sample_date.isoformat()
    existing = None
    for sample in samples:
        if str(sample.get("date") or "") == iso:
            existing = sample
            break
    if existing is None:
        existing = {"date": iso}
        samples.append(existing)
    existing["observedAt"] = observed_at
    existing.update(fields)
    return existing


def save_observation_history(store, today):
    cutoff = history_retention_cutoff(today)
    cleaned = {}
    for provider_id, samples in store.items():
        by_date = {}
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            try:
                sample_date = date.fromisoformat(str(sample.get("date") or ""))
            except ValueError:
                continue
            if sample_date < cutoff:
                continue
            kept = dict(sample)
            kept["date"] = sample_date.isoformat()
            by_date[kept["date"]] = kept
        if by_date:
            cleaned[str(provider_id)] = [by_date[key] for key in sorted(by_date)]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.atomic_write_json(
        HISTORY_PATH, {"version": 2, "providers": cleaned}
    )
    return cleaned


def map_history_from_store(store, provider_id, period):
    points = []
    for sample in store.get(provider_id) or []:
        try:
            sample_date = date.fromisoformat(str(sample.get("date") or ""))
        except ValueError:
            continue
        if sample_date < period["periodStart"] or sample_date >= period["today"]:
            continue
        if "pressure" not in sample:
            continue
        try:
            pressure = float(sample["pressure"])
        except (TypeError, ValueError):
            continue
        day_number = (sample_date - period["periodStart"]).days + 1
        points.append({"day": day_number, "pressure": pressure})
    points.sort(key=lambda item: item["day"])
    return points


def record_collected_observations(period, observed_at, providers):
    store = load_observation_history()
    today = period["today"]
    for provider in providers:
        if not provider.get("ok") or provider.get("stale"):
            continue
        provider_id = str(provider.get("id") or "")
        if not provider_id:
            continue
        upsert_observation(
            store,
            provider_id,
            today,
            observed_at,
            {"pressure": provider.get("currentPressure", 0)},
        )
        for sample in provider.get("history") or []:
            try:
                day_number = int(sample.get("day") or 0)
            except (TypeError, ValueError):
                continue
            if day_number < 1:
                continue
            sample_date = period["periodStart"] + timedelta(days=day_number - 1)
            if sample_date >= today:
                continue
            upsert_observation(
                store,
                provider_id,
                sample_date,
                observed_at,
                {"pressure": sample.get("pressure", 0)},
            )
    return save_observation_history(store, today)


def attach_map_history(providers, store, period):
    for provider in providers:
        provider["history"] = map_history_from_store(
            store, str(provider.get("id") or ""), period
        )


def update_openrouter_history(today, observed_at, credits):
    store = load_observation_history()
    upsert_observation(
        store,
        "openrouter",
        today,
        observed_at,
        {
            "totalUsageUsd": rounded(credits.get("totalUsage"), 6),
            "balanceUsd": rounded(credits.get("balance"), 6),
        },
    )
    store = save_observation_history(store, today)
    return store.get("openrouter") or []


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


def weighted_openrouter_burn(samples, period):
    if len(samples) < 2:
        return None
    deltas = []
    sorted_samples = sorted(samples, key=lambda s: s.get("date") or "")
    for idx in range(1, len(sorted_samples)):
        prev = sorted_samples[idx - 1]
        cur = sorted_samples[idx]
        try:
            prev_val = Decimal(str(prev.get("totalUsageUsd")))
            cur_val = Decimal(str(cur.get("totalUsageUsd")))
            cur_date = date.fromisoformat(str(cur.get("date")))
            prev_date = date.fromisoformat(str(prev.get("date")))
        except (ValueError, TypeError, InvalidOperation):
            continue
        gap = (cur_date - prev_date).days
        if gap <= 0:
            continue
        delta = cur_val - prev_val
        if delta < 0:
            continue
        rate = delta / Decimal(gap)
        deltas.append((cur_date, rate, gap))
    if not deltas:
        return None
    decay = forecast_decay()
    weighted_sum = Decimal(0)
    weight_sum = Decimal(0)
    for cur_date, rate, gap in deltas:
        days_ago = (period["today"] - cur_date).days
        if days_ago < 0:
            continue
        segments = []
        for offset in range(1, gap + 1):
            day_ago = days_ago - (gap - offset)
            weight = (decay ** day_ago) if day_ago > 0 else Decimal(1)
            segments.append(weight)
        avg_weight = sum(segments, Decimal(0)) / Decimal(len(segments)) if segments else Decimal(1)
        weighted_sum += rate * avg_weight
        weight_sum += avg_weight
    if weight_sum == 0:
        return None
    span = (date.fromisoformat(sorted_samples[-1]["date"]) - date.fromisoformat(sorted_samples[0]["date"])).days
    if span < 1:
        span = 1
    return weighted_sum / weight_sum, span


def openrouter_provider(period, timeout, observed_at):
    log_event("OpenRouter: fetching credits and trailing usage...")
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
    weighted_local = None
    try:
        weighted_local = weighted_openrouter_burn(samples, period)
    except Exception:
        weighted_local = None
    if weighted_local is not None:
        daily_burn, history_days = weighted_local
        burn_source = "weighted-local-history"
    else:
        burn_source = "local-observation-history"
    try:
        daily_burn = fetch_openrouter_daily_burn(
            api_key, period["localNow"], timeout
        )
        history_days = 30
        burn_source = "openrouter-analytics-30d"
    except ProviderError as error:
        if is_rate_limited(error):
            log_event(f"RATE LIMIT / THROTTLED: OpenRouter analytics throttled: {clean_error(error)}; using local history")
        else:
            log_event(f"OpenRouter analytics unavailable: {clean_error(error)}; using local history")
        if daily_burn is None and weighted_local is not None:
            daily_burn, history_days = weighted_local
            burn_source = "weighted-local-history"
        elif daily_burn is None:
            fallback = burn_from_local_history(samples)
            if fallback[0] is not None:
                daily_burn, history_days = fallback
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

    provider = {
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
    log_event(
        f"OpenRouter: fresh fetch succeeded: balance ${provider['balanceUsd']}, "
        f"daily burn ${provider['dailyBurnUsd'] or 0:.4f}/day, projected ${provider['projectedBalanceUsd']} at EOM"
    )
    return provider


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
    log_event("GitHub Actions: querying user billing usage report and repo visibility...")
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
        except ProviderError as error:
            # Deleted or inaccessible repositories cannot be classified. Count
            # them conservatively so the warning map never understates risk.
            if is_rate_limited(error):
                log_event(
                    f"RATE LIMIT / THROTTLED: GitHub repository visibility check throttled for {repository_name}: {clean_error(error)}"
                )
            else:
                log_event(
                    f"GitHub repository visibility check failed for {repository_name}: {clean_error(error)}"
                )
            visibility_unknown.append(repository_name or "unknown")
            is_public = False
        if is_public:
            public_minutes += quantity
        else:
            included_usage += quantity

    store = load_observation_history()
    history_pressures = map_history_from_store(store, "github_actions", period)
    weighted = weighted_month_forecast(included_usage, period, history_pressures, allowance)
    if weighted is not None:
        forecast = max(included_usage, weighted)
        forecast_source = "weighted-daily-pace"
    else:
        forecast = max(included_usage, linear_month_forecast(included_usage, period))
        forecast_source = "linear-month-pace"
    current_payable = max(Decimal(0), current_payable)
    detail = (
        f"{float(included_usage):,.0f} / {float(allowance):,.0f} min · "
        f"{float(forecast):,.0f} EOM · ${float(current_payable):.2f} due"
    )
    if visibility_unknown:
        detail += f" · {len(visibility_unknown)} repo visibility unknown"

    provider = {
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
        "forecastSource": forecast_source,
        "detail": detail,
    }
    log_event(
        f"GitHub Actions: fresh fetch succeeded: {provider['currentMinutes']}/{provider['includedMinutes']} min ({plan} plan), forecast {provider['forecastMinutes']} min, ${provider['currentPayableUsd']} due"
    )
    return provider


def blacksmith_usage(period, timeout):
    tzinfo = period["localNow"].tzinfo
    start = datetime.combine(period["periodStart"], time.min, tzinfo=tzinfo)
    end = datetime.combine(period["periodEndExclusive"], time.min, tzinfo=tzinfo)
    command = [
        "blacksmith",
        "usage",
        "--format",
        "json",
        "--start-time",
        start.isoformat(timespec="seconds"),
        "--end-time",
        end.isoformat(timespec="seconds"),
    ]
    org = os.environ.get("BILLING_BLACKSMITH_ORG", "").strip()
    if org:
        command.extend(["--org", org])
    return run_json(command, timeout)


def blacksmith_history_pressures(daily_rows, period, allowance):
    """Cumulative 2vCPU minutes through each past day against the free allowance.

    Today's glyph already sits on the now line, so samples stop at yesterday.
    """
    if not daily_rows or allowance is None or allowance <= 0:
        return []
    by_day = {}
    for row in daily_rows:
        if not isinstance(row, dict):
            continue
        try:
            day_date = date.fromisoformat(str(row.get("date") or ""))
        except ValueError:
            continue
        billable = max(
            Decimal(0),
            as_decimal(
                row.get("billable_minutes", 0), "Blacksmith daily billable minutes"
            ),
        )
        by_day[day_date] = by_day.get(day_date, Decimal(0)) + billable
    points = []
    cumulative = Decimal(0)
    for offset in range(1, period["day"]):
        day_date = period["periodStart"] + timedelta(days=offset - 1)
        cumulative += by_day.get(day_date, Decimal(0))
        consumed = cumulative / Decimal(2)
        points.append({"day": offset, "pressure": rounded(consumed / allowance)})
    return points


def blacksmith_provider(period, timeout):
    log_event("Blacksmith: querying CLI usage...")
    payload = blacksmith_usage(period, timeout)
    summary = payload.get("summary") or {}
    billable = max(
        Decimal(0),
        as_decimal(summary.get("billable_minutes", 0), "Blacksmith billable minutes"),
    )
    allowance = BLACKSMITH_FREE_MINUTES
    # CLI billable_minutes are 1-vCPU weighted; the advertised free allowance
    # is x64 2vCPU minutes. Divide by 2 to plot the same unit the 3,000-minute
    # free tier is denominated in.
    consumed = billable / Decimal(2)
    history_points = blacksmith_history_pressures(
        payload.get("daily") or [], period, allowance
    )
    weighted = weighted_month_forecast(consumed, period, history_points, allowance)
    if weighted is not None:
        forecast = max(consumed, weighted)
        forecast_source = "weighted-daily-pace"
    else:
        forecast = max(consumed, linear_month_forecast(consumed, period))
        forecast_source = "linear-month-pace"
    org = str(
        ((payload.get("installation") or {}).get("installation_name") or "")
    ).strip() or os.environ.get("BILLING_BLACKSMITH_ORG", "").strip()
    provider = {
        "id": "blacksmith",
        "code": "BSM",
        "name": "Blacksmith",
        "color": BLACKSMITH_COLOR,
        "kind": "allowance",
        "ok": True,
        "stale": False,
        "org": org,
        "currentMinutes": rounded(consumed, 2),
        "includedMinutes": rounded(allowance, 2),
        "forecastMinutes": rounded(forecast, 2),
        "billableWeightedMinutes": rounded(billable, 2),
        "currentPressure": rounded(consumed / allowance),
        "forecastPressure": rounded(forecast / allowance),
        "forecastAvailable": True,
        "source": "blacksmith-usage",
        "forecastSource": forecast_source,
        "history": history_points,
        "detail": (
            f"{float(consumed):,.0f} / {float(allowance):,.0f} min · "
            f"{float(forecast):,.0f} EOM"
        ),
    }
    log_event(
        f"Blacksmith: fresh fetch succeeded: {provider['currentMinutes']}/{provider['includedMinutes']} min (org: {org or 'default'}), forecast {provider['forecastMinutes']} min"
    )
    return provider


def configured(*names):
    return any(os.environ.get(name, "").strip() for name in names)


def previous_providers(period_start=None):
    output = load_json(STATUS_PATH, {})
    if period_start is not None:
        expected_period = (
            period_start.isoformat()
            if hasattr(period_start, "isoformat")
            else str(period_start)
        )
        if output.get("periodStart") != expected_period:
            return {}
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
    old = previous_providers(period["periodStart"])

    if aws_enabled():
        try:
            providers.append(aws_provider(period, timeout))
        except Exception as error:
            message = clean_error(error)
            if is_rate_limited(error):
                log_event(f"RATE LIMIT / THROTTLED: AWS request was throttled: {message}")
            else:
                log_event(f"ERROR: AWS fetch failed: {message}")
            errors.append({"provider": "aws", "error": message})
            if "aws" in old:
                providers.append(stale_provider(old["aws"], error))

    if env_flag("BILLING_AZURE_ENABLED") or configured("BILLING_AZURE_SUBSCRIPTION_ID"):
        try:
            providers.append(azure_provider(period, timeout))
        except Exception as error:
            message = clean_error(error)
            if is_rate_limited(error):
                log_event(f"RATE LIMIT / THROTTLED: Azure request was throttled: {message}")
            else:
                log_event(f"ERROR: Azure fetch failed: {message}")
            errors.append({"provider": "azure", "error": message})
            if "azure" in old:
                providers.append(stale_provider(old["azure"], error))

    if configured("OPENROUTER_API_KEY"):
        try:
            providers.append(openrouter_provider(period, timeout, observed_at))
        except Exception as error:
            message = clean_error(error)
            if is_rate_limited(error):
                log_event(f"RATE LIMIT / THROTTLED: OpenRouter request was throttled: {message}")
            else:
                log_event(f"ERROR: OpenRouter fetch failed: {message}")
            errors.append({"provider": "openrouter", "error": message})
            if "openrouter" in old:
                providers.append(stale_provider(old["openrouter"], error))

    if env_flag("BILLING_GITHUB_ACTIONS_ENABLED"):
        try:
            providers.append(github_actions_provider(period, timeout))
        except Exception as error:
            message = clean_error(error)
            if is_rate_limited(error):
                log_event(f"RATE LIMIT / THROTTLED: GitHub Actions request was throttled/rate-limited: {message}")
            else:
                log_event(f"ERROR: GitHub Actions fetch failed: {message}")
            errors.append({"provider": "github_actions", "error": message})
            if "github_actions" in old:
                providers.append(stale_provider(old["github_actions"], error))

    if env_flag("BILLING_BLACKSMITH_ENABLED"):
        try:
            providers.append(blacksmith_provider(period, timeout))
        except Exception as error:
            message = clean_error(error)
            if is_rate_limited(error):
                log_event(f"RATE LIMIT / THROTTLED: Blacksmith request was throttled: {message}")
            else:
                log_event(f"ERROR: Blacksmith fetch failed: {message}")
            errors.append({"provider": "blacksmith", "error": message})
            if "blacksmith" in old:
                providers.append(stale_provider(old["blacksmith"], error))

    provider_order = {
        "aws": 0,
        "anthropic": 1,
        "openrouter": 2,
        "github_actions": 3,
        "blacksmith": 4,
        "azure": 5,
    }
    providers.sort(key=lambda item: provider_order.get(item.get("id"), 99))
    if not providers and not errors:
        msg = (
            "No billing providers configured; set an OpenRouter key "
            "or enable AWS / Azure / GitHub Actions / Blacksmith"
        )
        log_event(f"Configuration notice: {msg}")
        errors.append(
            {
                "provider": "configuration",
                "error": msg,
            }
        )

    store = record_collected_observations(period, observed_at, providers)
    attach_map_history(providers, store, period)

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
            active_names = [p.get("name", p.get("id")) for p in output["providers"]]
            log_event(
                f"updated {len(output['providers'])} provider(s) ({', '.join(active_names)}) for {output['periodEnd']}"
            )
            return 0
        log_event(f"ERROR: {output.get('error') or 'no billing providers available'}")
        return 1
    except Exception as error:
        message = clean_error(error)
        if is_rate_limited(error):
            log_event(f"RATE LIMIT / THROTTLED: fatal billing fetch error: {message}")
        else:
            log_event(f"ERROR: fatal billing fetch error: {message}")
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

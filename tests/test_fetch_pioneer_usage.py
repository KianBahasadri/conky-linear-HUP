import json
from datetime import datetime, timezone

import fetch_pioneer_usage as pioneer


def plan_info_payload(daily_used=1250.0, daily_limit=5000.0, payment_plan="pro"):
    return {
        "payment_plan": payment_plan,
        "credit_limit": daily_limit,
        "user_limit": None,
        "total_usage": daily_used,
        "remaining_credits": max(0.0, daily_limit - daily_used),
        "exceeds_limit": daily_used > daily_limit,
    }


def billing_status_payload(team_id="team-1"):
    return {"team_id": team_id}


def overage_settings_payload():
    return {
        "credit_limit": 5000.0,
        "usage_reset_hour": 0,
        "usage_reset_timezone": "UTC",
        "max_monthly_spend": None,
        "current_month_start": "2026-06-16T17:06:52.633385+00:00",
        "current_period_usage": 3253.0335,
    }


def timeseries_payload(points):
    return {"points": points}


def test_normalize_usage_creates_daily_and_monthly_windows():
    now = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
    overage = overage_settings_payload()
    account = pioneer.normalize_usage(
        plan_info_payload(daily_used=2500.0, daily_limit=5000.0),
        overage,
        pioneer.resolve_monthly_usage(overage, now),
        is_selected=True,
    )
    bars = pioneer.flatten_bars([account])

    assert account["ok"] is True
    assert account["usesBillingPeriod"] is True
    assert account["billingPeriodStart"] == "2026-06-16T17:06:52.633385+00:00"
    assert account["billingPeriodEnd"] == "2026-07-16T17:06:52.633385+00:00"
    assert account["label"] == "pioneer"
    assert account["planType"] == "pro"
    assert [bar["window"] for bar in bars] == ["daily", "monthly"]
    assert bars[0]["usedPercent"] == 50.0
    assert bars[1]["usedPercent"] == 2.2
    assert bars[0]["windowSeconds"] == pioneer.DAILY_WINDOW_SECONDS
    assert bars[0]["resetAfterSeconds"] > 0
    assert bars[1]["resetAfterSeconds"] > 0
    assert bars[1]["resetAtEpoch"] == int(datetime(2026, 7, 16, 17, 6, 52, 633385, tzinfo=timezone.utc).timestamp())


def test_resolve_monthly_usage_uses_current_period_usage_when_billing_period_present():
    now = datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc)
    usage = pioneer.resolve_monthly_usage(overage_settings_payload(), now)
    assert usage == 3253.0335


def test_resolve_monthly_credit_limit_uses_env_override(monkeypatch):
    monkeypatch.setenv("PIONEER_MONTHLY_CREDIT_LIMIT", "9999")
    assert pioneer.resolve_monthly_credit_limit("pro", {}) == 9999.0


def test_fetch_account_reads_plan_billing_and_timeseries(monkeypatch):
    seen_paths = []

    def fake_request(path, query=""):
        seen_paths.append((path, query))
        if path == "/billing/plan-info":
            return 200, plan_info_payload()
        if path == "/billing/billing-status":
            return 200, billing_status_payload()
        if path == "/billing/team/team-1/overage-settings":
            return 200, overage_settings_payload()
        if path == "/billing/usage/timeseries":
            return 200, timeseries_payload(
                [
                    {"bucket_date": "2026-06-16", "total_credits": 281.823, "request_count": 155},
                    {"bucket_date": "2026-06-17", "total_credits": 2971.2105, "request_count": 121},
                ]
            )
        raise AssertionError((path, query))

    monkeypatch.setenv("PIONEER_API_KEY", "test-key")
    monkeypatch.setattr(pioneer, "pioneer_request", fake_request)

    account = pioneer.fetch_account(True)

    assert account["ok"] is True
    assert account["monthlyUsedCredits"] == 3253.0335
    assert account["usesBillingPeriod"] is True
    assert account["windows"][0]["label"] == "daily"
    assert account["windows"][1]["label"] == "monthly"
    assert not any(path == "/billing/usage/timeseries" for path, _ in seen_paths)


def test_fetch_account_requires_api_key(monkeypatch):
    monkeypatch.delenv("PIONEER_API_KEY", raising=False)
    account = pioneer.fetch_account(True)
    assert account["ok"] is False
    assert "PIONEER_API_KEY" in account["error"]

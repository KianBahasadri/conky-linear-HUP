import json
from datetime import date, datetime, timezone
from decimal import Decimal

import fetch_billing_usage as billing


def isolate_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(billing, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(billing, "STATUS_PATH", tmp_path / "billing-usage.json")
    monkeypatch.setattr(
        billing, "RENDER_PATH", tmp_path / "billing-usage-render.tsv"
    )
    monkeypatch.setattr(billing, "HISTORY_PATH", tmp_path / "billing-history.json")
    monkeypatch.setattr(billing, "log_event", lambda _message: None)


def test_month_period_uses_one_inclusive_calendar_eom():
    period = billing.month_period(date(2026, 8, 19))

    assert period["periodStart"] == date(2026, 8, 1)
    assert period["periodEnd"] == date(2026, 8, 31)
    assert period["periodEndExclusive"] == date(2026, 9, 1)
    assert period["day"] == 19
    assert period["daysInMonth"] == 31
    assert period["daysRemaining"] == 12
    assert period["elapsedFraction"] == 19 / 31


def test_month_period_handles_leap_february():
    period = billing.month_period(date(2028, 2, 12))

    assert period["periodEnd"] == date(2028, 2, 29)
    assert period["daysInMonth"] == 29
    assert period["daysRemaining"] == 17


def test_metered_provider_projects_current_pace_to_eom():
    period = billing.month_period(date(2026, 8, 19))
    provider = billing.metered_provider(
        "aws",
        "AWS",
        "AWS",
        billing.AWS_COLOR,
        Decimal("25"),
        Decimal("8.41"),
        period,
        "aws",
    )

    assert provider["currentPressure"] == 0.3364
    assert provider["forecastUsd"] == 13.72
    assert provider["forecastPressure"] == 0.5489
    assert provider["forecastSource"] == "linear-month-pace"


def test_live_openrouter_uses_balance_as_ceiling_and_common_eom(monkeypatch, tmp_path):
    isolate_cache(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "management-key")
    monkeypatch.setattr(
        billing,
        "fetch_openrouter_credits",
        lambda *_args: {
            "balance": Decimal("12.44"),
            "totalUsage": Decimal("25.75"),
            "totalCredits": Decimal("38.19"),
        },
    )
    monkeypatch.setattr(
        billing, "fetch_openrouter_daily_burn", lambda *_args: Decimal("0.43")
    )

    period = billing.month_period(date(2026, 8, 19))
    provider = billing.openrouter_provider(period, 5, "2026-08-19T12:00:00Z")

    assert provider["currentPressure"] == 0
    assert provider["forecastUsd"] == 5.16
    assert provider["forecastPressure"] == 0.4148
    assert provider["projectedBalanceUsd"] == 7.28
    assert provider["forecastSource"] == "openrouter-analytics-30d"


def test_openrouter_local_history_fallback_uses_usage_delta(monkeypatch, tmp_path):
    isolate_cache(monkeypatch, tmp_path)
    (tmp_path / "billing-history.json").write_text(
        json.dumps(
            {
                "version": 1,
                "openrouter": [
                    {
                        "date": "2026-08-09",
                        "observedAt": "2026-08-09T12:00:00Z",
                        "totalUsageUsd": 21.0,
                        "balanceUsd": 16.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "management-key")
    monkeypatch.setattr(
        billing,
        "fetch_openrouter_credits",
        lambda *_args: {
            "balance": Decimal("12"),
            "totalUsage": Decimal("25"),
            "totalCredits": Decimal("37"),
        },
    )
    monkeypatch.setattr(
        billing,
        "fetch_openrouter_daily_burn",
        lambda *_args: (_ for _ in ()).throw(billing.ProviderError("unavailable")),
    )

    period = billing.month_period(date(2026, 8, 19))
    provider = billing.openrouter_provider(period, 5, "2026-08-19T12:00:00Z")

    assert provider["dailyBurnUsd"] == 0.4
    assert provider["historyDays"] == 10
    assert provider["forecastUsd"] == 4.8
    assert provider["forecastPressure"] == 0.4
    assert provider["forecastSource"] == "local-observation-history"


def test_openrouter_without_enough_history_keeps_bead_but_no_forecast(
    monkeypatch, tmp_path
):
    isolate_cache(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "management-key")
    monkeypatch.setattr(
        billing,
        "fetch_openrouter_credits",
        lambda *_args: {
            "balance": Decimal("12"),
            "totalUsage": Decimal("25"),
            "totalCredits": Decimal("37"),
        },
    )
    monkeypatch.setattr(
        billing,
        "fetch_openrouter_daily_burn",
        lambda *_args: (_ for _ in ()).throw(billing.ProviderError("unavailable")),
    )

    period = billing.month_period(date(2026, 8, 19))
    provider = billing.openrouter_provider(period, 5, "2026-08-19T12:00:00Z")

    assert provider["forecastAvailable"] is False
    assert provider["forecastPressure"] == 0
    assert "collecting burn history" in provider["detail"]


def test_openrouter_analytics_averages_the_full_trailing_window(monkeypatch):
    captured = {}

    def fake_request(url, **kwargs):
        captured.update(kwargs["payload"])
        return {
            "data": {
                "data": [
                    {"created_at__day": "2026-08-17", "total_usage": 3},
                    {"created_at__day": "2026-08-18", "total_usage": "6"},
                ],
                "metadata": {"truncated": False},
            }
        }

    monkeypatch.setattr(billing, "request_json", fake_request)
    now = datetime(2026, 8, 19, 12, tzinfo=timezone.utc)

    burn = billing.fetch_openrouter_daily_burn("secret", now, 5)

    assert burn == Decimal("0.3")
    assert captured["granularity"] == "day"
    assert captured["time_range"]["end"] == "2026-08-19T12:00:00Z"


def test_anthropic_cost_report_converts_fractional_cents(monkeypatch):
    responses = [
        {
            "data": [
                {"results": [{"amount": "123.45", "currency": "USD"}]}
            ],
            "has_more": True,
            "next_page": "page-2",
        },
        {
            "data": [
                {"results": [{"amount": "76.55", "currency": "USD"}]}
            ],
            "has_more": False,
        },
    ]
    monkeypatch.setattr(
        billing, "request_json", lambda *_args, **_kwargs: responses.pop(0)
    )

    current = billing.fetch_anthropic_current(
        billing.month_period(date(2026, 8, 19)), "admin-key", 5
    )

    assert current == Decimal("2.00")


def test_collect_live_providers_share_one_period_end(monkeypatch, tmp_path):
    isolate_cache(monkeypatch, tmp_path)
    monkeypatch.setenv("BILLING_AWS_CAP_USD", "25")
    monkeypatch.setenv("BILLING_AZURE_CAP_USD", "20")
    monkeypatch.setenv("BILLING_ANTHROPIC_CAP_USD", "20")
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "admin-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "management-key")
    monkeypatch.setattr(
        billing, "fetch_aws_current", lambda *_args: Decimal("8.41")
    )
    monkeypatch.setattr(
        billing, "fetch_azure_current", lambda *_args: Decimal("4.27")
    )
    monkeypatch.setattr(
        billing, "fetch_anthropic_current", lambda *_args: Decimal("6.04")
    )
    monkeypatch.setattr(
        billing,
        "fetch_openrouter_credits",
        lambda *_args: {
            "balance": Decimal("12.44"),
            "totalUsage": Decimal("25.75"),
            "totalCredits": Decimal("38.19"),
        },
    )
    monkeypatch.setattr(
        billing, "fetch_openrouter_daily_burn", lambda *_args: Decimal("0.43")
    )

    output = billing.collect(date(2026, 8, 19))

    assert output["ok"] is True
    assert output["periodEnd"] == "2026-08-31"
    assert output["daysRemaining"] == 12
    assert [item["id"] for item in output["providers"]] == [
        "aws",
        "anthropic",
        "openrouter",
        "azure",
    ]
    openrouter = output["providers"][2]
    assert openrouter["forecastUsd"] == 5.16
    assert openrouter["forecastPressure"] == 0.4148


def test_render_tsv_contains_only_renderer_fields():
    output = {
        "ok": True,
        "updatedAt": "2026-08-19T12:00:00Z",
        "periodStart": "2026-08-01",
        "periodEnd": "2026-08-31",
        "day": 19,
        "daysInMonth": 31,
        "daysRemaining": 12,
        "elapsedFraction": 0.612903,
        "error": "",
        "providers": [
            {
                "id": "openrouter",
                "code": "OR",
                "color": billing.OPENROUTER_COLOR,
                "kind": "prepaid",
                "ok": True,
                "stale": False,
                "currentPressure": 0,
                "forecastPressure": 0.4148,
                "forecastAvailable": True,
                "source": "openrouter-credits",
                "detail": "$12.44 left",
            }
        ],
    }

    rendered = billing.render_tsv(output)

    assert "periodEnd\t2026-08-31" in rendered
    assert "provider\topenrouter\tOR\ta78bfa\tprepaid\t1\t0\t0\t0.4148\t1" in rendered
    assert "OPENROUTER_API_KEY" not in rendered

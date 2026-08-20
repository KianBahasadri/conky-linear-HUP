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
    monkeypatch.setenv("BILLING_BLACKSMITH_ENABLED", "0")


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


def test_github_actions_uses_private_standard_runner_minutes(monkeypatch):
    usage = {
        "usageItems": [
            {
                "product": "actions",
                "sku": "Actions Linux",
                "unitType": "Minutes",
                "quantity": 69,
                "repositoryName": "private-app",
                "netAmount": 0,
            },
            {
                "product": "actions",
                "sku": "Actions Windows",
                "unitType": "Minutes",
                "quantity": 816,
                "repositoryName": "private-app",
                "netAmount": 0,
            },
            {
                "product": "actions",
                "sku": "Actions Linux",
                "unitType": "Minutes",
                "quantity": 352,
                "repositoryName": "private-tool",
                "netAmount": 0,
            },
            {
                "product": "actions",
                "sku": "Actions Linux",
                "unitType": "Minutes",
                "quantity": 264,
                "repositoryName": "public-tool",
                "netAmount": 0,
            },
            {
                "product": "actions",
                "sku": "Actions storage",
                "unitType": "GigabyteHours",
                "quantity": 1200,
                "repositoryName": "private-app",
                "netAmount": 0.25,
            },
            {
                "product": "actions",
                "sku": "Actions Linux 4-core",
                "unitType": "Minutes",
                "quantity": 10,
                "repositoryName": "private-app",
                "netAmount": 0.10,
            },
        ]
    }

    def fake_github_api(path, _timeout):
        if path == "/user":
            return {"login": "octocat", "plan": {"name": "pro"}}
        if path.startswith("/users/octocat/settings/billing/usage?"):
            return usage
        if path == "/repos/octocat/public-tool":
            return {"visibility": "public"}
        if path in {
            "/repos/octocat/private-app",
            "/repos/octocat/private-tool",
        }:
            return {"visibility": "private"}
        raise AssertionError(f"unexpected GitHub API path: {path}")

    monkeypatch.setattr(billing, "github_api", fake_github_api)

    provider = billing.github_actions_provider(
        billing.month_period(date(2026, 8, 19)), 5
    )

    assert provider["currentMinutes"] == 1237
    assert provider["includedMinutes"] == 3000
    assert provider["forecastMinutes"] == 2018.26
    assert provider["publicMinutesExcluded"] == 264
    assert provider["currentPayableUsd"] == 0.35
    assert provider["currentPressure"] == 0.4123
    assert provider["forecastPressure"] == 0.6728
    assert provider["forecastSource"] == "linear-month-pace"


def test_blacksmith_plots_2vcpu_minutes_against_live_free_allowance(monkeypatch):
    def fake_blacksmith_api(path, _timeout):
        if path == "/user":
            return {"active_org_name": "klever-lab"}
        if path.startswith("/user/github/orgs/klever-lab/usage?"):
            return {"billable_minutes": 1050, "free_minutes": 3000}
        raise AssertionError(f"unexpected Blacksmith API path: {path}")

    monkeypatch.setattr(billing, "blacksmith_api", fake_blacksmith_api)

    provider = billing.blacksmith_provider(
        billing.month_period(date(2026, 8, 19)), 5
    )

    assert provider["id"] == "blacksmith"
    assert provider["kind"] == "allowance"
    assert provider["org"] == "klever-lab"
    assert provider["currentMinutes"] == 525
    assert provider["includedMinutes"] == 3000
    assert provider["forecastMinutes"] == 856.58
    assert provider["currentPressure"] == 0.175
    assert provider["forecastPressure"] == 0.2855
    assert provider["forecastSource"] == "linear-month-pace"
    assert provider["source"] == "blacksmith-usage"


def test_collect_live_providers_share_one_period_end(monkeypatch, tmp_path):
    isolate_cache(monkeypatch, tmp_path)
    monkeypatch.setenv("BILLING_AWS_CAP_USD", "25")
    monkeypatch.setenv("BILLING_AZURE_ENABLED", "1")
    monkeypatch.setenv("BILLING_ANTHROPIC_CAP_USD", "20")
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "admin-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "management-key")
    monkeypatch.setenv("BILLING_GITHUB_ACTIONS_ENABLED", "0")
    monkeypatch.setattr(
        billing, "fetch_aws_current", lambda *_args: Decimal("8.41")
    )
    monkeypatch.setattr(
        billing,
        "fetch_azure_credit_balance",
        lambda *_args: {
            "remaining": Decimal("74.26"),
            "starting": Decimal("98.72"),
            "spent": Decimal("24.46"),
        },
    )
    monkeypatch.setattr(billing, "fetch_azure_daily_usd", lambda *_args: {})
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
    azure = output["providers"][3]
    assert azure["kind"] == "prepaid"
    assert azure["currentUsd"] == 24.46
    assert azure["capUsd"] == 98.72
    assert azure["currentPressure"] == round(24.46 / 98.72, 4)


def _stub_collect_providers(monkeypatch, tmp_path, *, azure_daily=None):
    isolate_cache(monkeypatch, tmp_path)
    monkeypatch.setenv("BILLING_AWS_CAP_USD", "25")
    monkeypatch.setenv("BILLING_AZURE_ENABLED", "1")
    monkeypatch.setenv("BILLING_ANTHROPIC_CAP_USD", "20")
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "admin-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "management-key")
    monkeypatch.setenv("BILLING_GITHUB_ACTIONS_ENABLED", "0")
    monkeypatch.setattr(
        billing, "fetch_aws_current", lambda *_args: Decimal("8.41")
    )
    monkeypatch.setattr(
        billing,
        "fetch_azure_credit_balance",
        lambda *_args: {
            "remaining": Decimal("74.26"),
            "starting": Decimal("98.72"),
            "spent": Decimal("24.46"),
        },
    )
    monkeypatch.setattr(
        billing, "fetch_azure_daily_usd", lambda *_args: azure_daily or {}
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


def test_collect_stores_each_observation_and_plots_it_the_next_day(
    monkeypatch, tmp_path
):
    _stub_collect_providers(monkeypatch, tmp_path)

    first = billing.collect(date(2026, 8, 18))
    stored = json.loads((tmp_path / "billing-history.json").read_text(encoding="utf-8"))

    assert stored["version"] == 2
    by_id = {item["id"]: item for item in first["providers"]}
    for provider_id, provider in by_id.items():
        samples = stored["providers"][provider_id]
        assert samples[-1]["date"] == "2026-08-18"
        assert samples[-1]["pressure"] == provider["currentPressure"]
        assert provider["history"] == []

    second = billing.collect(date(2026, 8, 19))
    for provider in second["providers"]:
        assert provider["history"] == [
            {"day": 18, "pressure": by_id[provider["id"]]["currentPressure"]}
        ]


def test_collect_does_not_store_stale_observations(monkeypatch, tmp_path):
    _stub_collect_providers(monkeypatch, tmp_path)
    billing.write_output(billing.collect(date(2026, 8, 18)))

    def fail_aws(*_args):
        raise billing.ProviderError("aws unavailable")

    monkeypatch.setattr(billing, "fetch_aws_current", fail_aws)
    second = billing.collect(date(2026, 8, 19))
    aws = next(item for item in second["providers"] if item["id"] == "aws")
    stored = json.loads((tmp_path / "billing-history.json").read_text(encoding="utf-8"))

    assert aws["stale"] is True
    assert [sample["date"] for sample in stored["providers"]["aws"]] == ["2026-08-18"]
    assert aws["history"] == [
        {"day": 18, "pressure": 0.3364}
    ]


def test_collect_seeds_azure_store_from_daily_api(monkeypatch, tmp_path):
    _stub_collect_providers(
        monkeypatch,
        tmp_path,
        azure_daily={
            date(2026, 8, 1): Decimal("4.00"),
            date(2026, 8, 3): Decimal("6.00"),
        },
    )

    output = billing.collect(date(2026, 8, 19))
    azure = next(item for item in output["providers"] if item["id"] == "azure")
    stored = json.loads((tmp_path / "billing-history.json").read_text(encoding="utf-8"))
    azure_dates = [sample["date"] for sample in stored["providers"]["azure"]]

    assert azure["history"][0] == {"day": 1, "pressure": round(4.00 / 98.72, 4)}
    assert azure["history"][2] == {"day": 3, "pressure": round(10.00 / 98.72, 4)}
    assert azure["history"][-1]["day"] == 18
    assert "2026-08-01" in azure_dates
    assert "2026-08-03" in azure_dates
    assert "2026-08-19" in azure_dates


def test_collect_keeps_openrouter_v1_samples_when_migrating_the_store(
    monkeypatch, tmp_path
):
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
    monkeypatch.setenv("BILLING_AWS_CAP_USD", "25")
    monkeypatch.setenv("BILLING_AZURE_ENABLED", "0")
    monkeypatch.setenv("BILLING_AZURE_SUBSCRIPTION_ID", "")
    monkeypatch.setenv("BILLING_GITHUB_ACTIONS_ENABLED", "0")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", "")
    monkeypatch.setenv("ANTHROPIC_ADMIN_API_KEY", "")
    monkeypatch.setenv("BILLING_ANTHROPIC_CAP_USD", "")
    monkeypatch.setattr(
        billing, "fetch_aws_current", lambda *_args: Decimal("8.41")
    )

    billing.collect(date(2026, 8, 19))
    stored = json.loads((tmp_path / "billing-history.json").read_text(encoding="utf-8"))

    assert stored["version"] == 2
    assert stored["providers"]["openrouter"][0]["date"] == "2026-08-09"
    assert stored["providers"]["openrouter"][0]["totalUsageUsd"] == 21.0
    assert stored["providers"]["aws"][-1]["date"] == "2026-08-19"


def _azure_url(command):
    return command[command.index("--url") + 1]


def test_azure_converts_cad_cost_to_usd(monkeypatch):
    monkeypatch.setenv("BILLING_AZURE_SUBSCRIPTION_ID", "sub-1")

    def fake_run_json(command, _timeout):
        url = _azure_url(command)
        if "CostManagement/query" in url:
            return {
                "properties": {
                    "columns": [
                        {"name": "PreTaxCost"},
                        {"name": "Currency"},
                    ],
                    "rows": [[34.2355702355251, "CAD"]],
                }
            }
        if "usageDetails" in url:
            return {
                "value": [
                    {
                        "properties": {
                            "costInUSD": 0.05,
                            "exchangeRatePricingToBilling": 1.40905,
                        }
                    }
                ]
            }
        raise AssertionError(url)

    monkeypatch.setattr(billing, "run_json", fake_run_json)

    amount = billing.fetch_azure_current(5)

    assert round(float(amount), 2) == round(34.2355702355251 / 1.40905, 2)


def test_azure_usage_details_fallback_on_cost_management_throttle(monkeypatch):
    monkeypatch.setenv("BILLING_AZURE_SUBSCRIPTION_ID", "sub-1")
    versions = []

    def fake_run_json(command, _timeout):
        url = _azure_url(command)
        if "CostManagement/query" in url:
            versions.append(url)
            raise billing.ProviderError("az failed: Too Many Requests (429)")
        if "usageDetails" in url:
            next_link = None if "page=2" in url else url + "&page=2"
            rows = (
                [{"properties": {"costInUSD": "2.00"}}]
                if next_link is None
                else [{"properties": {"costInUSD": "10.25"}}]
            )
            payload = {"value": rows}
            if next_link:
                payload["nextLink"] = next_link
            return payload
        raise AssertionError(url)

    monkeypatch.setattr(billing, "run_json", fake_run_json)

    amount = billing.fetch_azure_current(5)

    assert amount == Decimal("12.25")
    assert any("2025-03-01" in url for url in versions)
    assert any("2023-11-01" in url for url in versions)


def test_azure_credit_balance_uses_estimated_usd(monkeypatch):
    monkeypatch.setenv("BILLING_AZURE_SUBSCRIPTION_ID", "sub-1")
    urls = []

    def fake_run_json(command, _timeout):
        url = _azure_url(command)
        urls.append(url)
        if url.endswith("billingAccounts?api-version=2024-04-01"):
            return {
                "value": [
                    {
                        "name": (
                            "b6cda2e3-d773-4a54-9a82-854549866a6b:"
                            "963985be-33e3-4f26-91bc-01a4ababbf51_2019-05-31"
                        )
                    }
                ]
            }
        if "billingProfiles?api-version=2024-04-01" in url:
            assert "%3A" in url
            return {
                "value": [
                    {
                        "name": "KX5Y-D2GQ-BG7-PGB",
                        "properties": {"spendingLimit": "On"},
                    }
                ]
            }
        if "credits/balanceSummary" in url:
            return {
                "properties": {
                    "balanceSummary": {
                        "currentBalance": {"currency": "USD", "value": 98.72},
                        "estimatedBalance": {"currency": "USD", "value": 74.26},
                    },
                    "pendingEligibleCharges": {"currency": "USD", "value": -24.46},
                }
            }
        raise AssertionError(url)

    monkeypatch.setattr(billing, "run_json", fake_run_json)

    credits = billing.fetch_azure_credit_balance(5)

    assert credits["remaining"] == Decimal("74.26")
    assert credits["starting"] == Decimal("98.72")
    assert credits["spent"] == Decimal("24.46")


def test_azure_history_pressures_fill_past_days_only():
    period = billing.month_period(date(2026, 8, 19))
    points = billing.azure_history_pressures(
        {
            date(2026, 8, 1): Decimal("4"),
            date(2026, 8, 3): Decimal("6"),
        },
        period,
        Decimal("100"),
    )

    assert points[0] == {"day": 1, "pressure": 0.04}
    assert points[1] == {"day": 2, "pressure": 0.04}
    assert points[2] == {"day": 3, "pressure": 0.1}
    assert points[-1]["day"] == 18
    assert len(points) == 18


def test_parse_azure_daily_cost_query_groups_cad_days():
    daily, currency = billing.parse_azure_daily_cost_query(
        {
            "properties": {
                "columns": [
                    {"name": "PreTaxCost"},
                    {"name": "UsageDate"},
                    {"name": "Currency"},
                ],
                "rows": [
                    [4.0, 20260801, "CAD"],
                    [6.0, 20260803, "CAD"],
                ],
            }
        }
    )

    assert currency == "CAD"
    assert daily[date(2026, 8, 1)] == Decimal("4.0")
    assert daily[date(2026, 8, 3)] == Decimal("6.0")


def test_azure_plots_month_spend_against_starting_credits(monkeypatch, tmp_path):
    isolate_cache(monkeypatch, tmp_path)
    monkeypatch.setattr(
        billing,
        "fetch_azure_credit_balance",
        lambda *_args: {
            "remaining": Decimal("74.26"),
            "starting": Decimal("98.72"),
            "spent": Decimal("24.46"),
        },
    )
    monkeypatch.setattr(
        billing,
        "fetch_azure_daily_usd",
        lambda *_args: {
            date(2026, 8, 1): Decimal("4.00"),
            date(2026, 8, 3): Decimal("6.00"),
        },
    )

    period = billing.month_period(date(2026, 8, 19))
    provider = billing.azure_provider(period, 5)

    spent = Decimal("24.46")
    starting = Decimal("98.72")
    forecast = spent * Decimal(31) / Decimal(19)
    assert provider["kind"] == "prepaid"
    assert provider["currentUsd"] == 24.46
    assert provider["capUsd"] == 98.72
    assert provider["balanceUsd"] == 74.26
    assert provider["currentPressure"] == round(float(spent / starting), 4)
    assert provider["forecastUsd"] == round(float(forecast), 2)
    assert provider["forecastPressure"] == round(float(forecast / starting), 4)
    assert provider["source"] == "azure-credits"
    assert provider["history"][0] == {"day": 1, "pressure": round(4.00 / 98.72, 4)}
    assert provider["history"][1]["day"] == 2
    assert provider["history"][1]["pressure"] == round(4.00 / 98.72, 4)
    assert provider["history"][2] == {"day": 3, "pressure": round(10.00 / 98.72, 4)}
    assert provider["history"][-1]["day"] == 18


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
            },
            {
                "id": "azure",
                "code": "AZR",
                "color": billing.AZURE_COLOR,
                "kind": "prepaid",
                "ok": True,
                "stale": False,
                "currentPressure": 0.2478,
                "forecastPressure": 0.4042,
                "forecastAvailable": True,
                "source": "azure-credits",
                "detail": "$24.46 now",
                "history": [
                    {"day": 1, "pressure": 0.0405},
                    {"day": 3, "pressure": 0.1013},
                ],
            },
        ],
    }

    rendered = billing.render_tsv(output)

    assert "periodEnd\t2026-08-31" in rendered
    assert (
        f"provider\topenrouter\tOR\t{billing.OPENROUTER_COLOR}\tprepaid\t1\t0\t0\t0.4148\t1"
        in rendered
    )
    assert "history\tazure\t1\t0.0405" in rendered
    assert "history\tazure\t3\t0.1013" in rendered
    assert "OPENROUTER_API_KEY" not in rendered

import json
from datetime import datetime, timezone

import fetch_commandcode_usage as commandcode


def write_auth(path, api_key="user_test_key", user_name="kian", user_id="user-1"):
    path.write_text(
        json.dumps(
            {
                "apiKey": api_key,
                "userId": user_id,
                "userName": user_name,
                "keyName": "cli",
                "authenticatedAt": "2026-08-18T00:00:00.000Z",
            }
        ),
        encoding="utf-8",
    )


def whoami_payload():
    return {
        "success": True,
        "user": {
            "id": "user-1",
            "name": "kian",
            "email": "kian@example.com",
            "userName": "kian",
        },
        "org": None,
    }


def credits_payload():
    return {
        "credits": {
            "belowThreshold": False,
            "creditThreshold": 0,
            "monthlyCredits": 9.899,
            "purchasedCredits": 0,
            "freeCredits": 0,
        },
        "windowLimits": {
            "limited": True,
            "exceeded": None,
            "fiveHour": {
                "used": 0.101,
                "cap": 3,
                "exceeded": False,
                "resetAt": 1_787_043_638_147,
            },
            "weekly": {
                "used": 0.101,
                "cap": 6,
                "exceeded": False,
                "resetAt": 1_787_630_438_147,
            },
        },
    }


def subscription_payload():
    return {
        "success": True,
        "data": {
            "status": "active",
            "planId": "individual-go",
            "currentPeriodStart": "2026-08-18T04:00:11.000Z",
            "currentPeriodEnd": "2026-09-18T04:00:11.000Z",
        },
    }


def summary_payload():
    return {
        "totalCount": 150,
        "totalCost": 0.074,
        "totalMonthlyCredits": 0.074,
        "periodBasis": "billing-period",
    }


def test_discover_auth_files_prefers_suffixed_files_and_marks_selected(monkeypatch, tmp_path):
    work = tmp_path / "auth.json.ida"
    personal = tmp_path / "auth.json.kian"
    write_auth(work, api_key="ida-key")
    write_auth(personal, api_key="kian-key")
    (tmp_path / "auth.json").symlink_to(work)
    monkeypatch.setenv("COMMAND_CODE_HOME", str(tmp_path))

    discovered = commandcode.discover_auth_files()

    assert [(label, selected, env_key) for label, _, selected, env_key in discovered] == [
        ("ida", True, None),
        ("kian", False, None),
    ]


def test_discover_auth_files_uses_env_api_key(monkeypatch, tmp_path):
    write_auth(tmp_path / "auth.json")
    monkeypatch.setenv("COMMAND_CODE_HOME", str(tmp_path))
    monkeypatch.setenv("COMMAND_CODE_API_KEY", "env-key")
    monkeypatch.setenv("COMMAND_CODE_USAGE_LABEL", "ci")

    discovered = commandcode.discover_auth_files()

    assert discovered == [("ci", None, True, "env-key")]


def test_plan_info_maps_known_ids():
    assert commandcode.plan_info("individual-go") == {
        "id": "individual-go",
        "name": "Go",
        "monthlyCredits": 10,
    }
    assert commandcode.plan_info("individual-pro-v1")["name"] == "Pro"
    assert commandcode.plan_info("individual-pro-v1")["monthlyCredits"] == 80
    assert commandcode.plan_info("") is None


def test_normalize_usage_creates_rolling_and_monthly_windows():
    fetched_at = datetime(2026, 8, 18, 5, 0, tzinfo=timezone.utc)
    monkeypatch_now = fetched_at

    original = commandcode.datetime

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return monkeypatch_now if tz is None else monkeypatch_now.astimezone(tz)

    commandcode.datetime = FrozenDateTime
    try:
        account = commandcode.normalize_usage(
            {"label": "cmd", "userId": "user-1"},
            whoami_payload(),
            credits_payload(),
            subscription_payload(),
            summary_payload(),
            True,
        )
    finally:
        commandcode.datetime = original

    bars = commandcode.flatten_bars([account])
    assert account["ok"] is True
    assert account["planType"] == "Go"
    assert account["email"] == "kian@example.com"
    assert [bar["window"] for bar in bars] == ["5h", "weekly", "monthly"]
    assert bars[0]["usedPercent"] == 3.4
    assert bars[1]["usedPercent"] == 1.7
    assert bars[2]["usedPercent"] == 1.0
    assert bars[0]["resetAtEpoch"] == 1787043638
    assert bars[1]["resetAtEpoch"] == 1787630438
    assert bars[2]["windowSeconds"] == 31 * 24 * 60 * 60


def test_fetch_account_reads_whoami_credits_subscription_and_summary(monkeypatch, tmp_path):
    auth_path = tmp_path / "auth.json"
    write_auth(auth_path)
    seen = []

    def fake_request(auth, endpoint, query=None):
        seen.append((endpoint, query))
        if endpoint == "/alpha/whoami":
            return 200, whoami_payload()
        if endpoint == "/alpha/billing/credits":
            return 200, credits_payload()
        if endpoint == "/alpha/billing/subscriptions":
            return 200, subscription_payload()
        if endpoint == "/alpha/usage/summary":
            assert query == {"since": "2026-08-18T04:00:11.000Z"}
            return 200, summary_payload()
        raise AssertionError((endpoint, query))

    monkeypatch.setattr(commandcode, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(commandcode, "commandcode_request", fake_request)

    account = commandcode.fetch_account("cmd", auth_path, True)

    assert [endpoint for endpoint, _ in seen] == [
        "/alpha/whoami",
        "/alpha/billing/credits",
        "/alpha/billing/subscriptions",
        "/alpha/usage/summary",
    ]
    assert account["ok"] is True
    assert account["planType"] == "Go"
    assert [window["label"] for window in account["windows"]] == ["5h", "weekly", "monthly"]


def test_fetch_account_uses_stale_cache_after_auth_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(commandcode, "CACHE_DIR", tmp_path)
    cached = {
        "ok": True,
        "label": "cmd",
        "planType": "Go",
        "isSelected": False,
        "windows": [{"label": "monthly", "usedPercent": 4.0, "remainingPercent": 96.0}],
    }
    commandcode.write_account_cache(cached)
    monkeypatch.setattr(
        commandcode,
        "read_auth",
        lambda label, path, env_key=None: (_ for _ in ()).throw(RuntimeError("expired key")),
    )

    account = commandcode.fetch_account("cmd", tmp_path / "auth.json", True)

    assert account["ok"] is True
    assert account["isSelected"] is True
    assert account["staleCache"] is True
    assert "expired key" in account["error"]
    assert account["windows"][0]["usedPercent"] == 4.0

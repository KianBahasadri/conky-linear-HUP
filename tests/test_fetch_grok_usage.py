import json
from datetime import datetime, timezone

import fetch_grok_usage as grok


def write_auth(path, token="token", email="grok@example.com", tier=1):
    path.write_text(
        json.dumps(
            {
                "https://auth.x.ai::client": {
                    "key": token,
                    "refresh_token": "refresh",
                    "email": email,
                    "tier": tier,
                }
            }
        ),
        encoding="utf-8",
    )


def billing_payload(now):
    return {
        "config": {
            "monthlyLimit": {"val": 15000},
            "used": {"val": 1500},
            "onDemandCap": {"val": 0},
            "billingPeriodStart": datetime.fromtimestamp(now - 3600, tz=timezone.utc).isoformat(),
            "billingPeriodEnd": datetime.fromtimestamp(now + 86400 * 20, tz=timezone.utc).isoformat(),
        }
    }


def billing_credits_payload(now):
    return {
        "config": {
            "currentPeriod": {
                "type": "USAGE_PERIOD_TYPE_MONTHLY",
                "start": datetime.fromtimestamp(now - 3600, tz=timezone.utc).isoformat(),
                "end": datetime.fromtimestamp(now + 86400 * 20, tz=timezone.utc).isoformat(),
            },
            "creditUsagePercent": 17.96,
            "onDemandCap": {"val": 0},
            "onDemandUsed": {"val": 0},
            "billingPeriodStart": datetime.fromtimestamp(now - 3600, tz=timezone.utc).isoformat(),
            "billingPeriodEnd": datetime.fromtimestamp(now + 86400 * 20, tz=timezone.utc).isoformat(),
        }
    }


def test_discover_auth_files_prefers_standalone_default_over_stale_suffixed_copy(monkeypatch, tmp_path):
    default_auth = tmp_path / "auth.json"
    stale_copy = tmp_path / "auth.json.kian"
    write_auth(default_auth, token="fresh-token", email="grok@example.com")
    write_auth(stale_copy, token="stale-token", email="grok@example.com")
    monkeypatch.setenv("GROK_HOME", str(tmp_path))

    discovered = grok.discover_auth_files()

    assert [(label, path.name, selected) for label, path, selected in discovered] == [
        ("grok", "auth.json", True),
    ]


def test_discover_auth_files_prefers_suffixed_files_and_marks_selected(monkeypatch, tmp_path):
    work = tmp_path / "auth.json.ida"
    personal = tmp_path / "auth.json.kian"
    write_auth(work, token="ida-token")
    write_auth(personal, token="kian-token")
    (tmp_path / "auth.json").symlink_to(work)
    monkeypatch.setenv("GROK_HOME", str(tmp_path))

    discovered = grok.discover_auth_files()

    assert [(label, selected) for label, _, selected in discovered] == [
        ("ida", True),
        ("kian", False),
    ]


def test_normalize_usage_creates_monthly_credit_window():
    now = int(datetime.now(timezone.utc).timestamp())
    account = grok.normalize_usage(
        {"label": "ida", "email": "ida@example.com", "tier": 1},
        billing_payload(now),
        {"email": "ida@example.com", "userId": "user-1", "hasGrokCodeAccess": True},
        True,
    )
    bars = grok.flatten_bars([account])

    assert account["ok"] is True
    assert account["email"] == "ida@example.com"
    assert account["planType"] == "tier-1"
    assert account["usedCredits"] == 1500
    assert account["monthlyLimitCredits"] == 15000
    assert [bar["window"] for bar in bars] == ["monthly"]
    assert bars[0]["usedPercent"] == 10.0
    assert bars[0]["resetAfterSeconds"] > 0
    assert bars[0]["windowSeconds"] == 86400 * 20 + 3600


def test_normalize_usage_accepts_credit_usage_percent_payload():
    now = int(datetime.now(timezone.utc).timestamp())
    account = grok.normalize_usage(
        {"label": "grok", "email": "grok@example.com", "tier": 0},
        billing_credits_payload(now),
        {"email": "grok@example.com", "userId": "user-1", "hasGrokCodeAccess": True},
        True,
    )
    bars = grok.flatten_bars([account])

    assert account["ok"] is True
    assert account["planType"] == "build"
    assert account["usedCredits"] == 0
    assert account["monthlyLimitCredits"] == 0
    assert bars[0]["usedPercent"] == 18.0
    assert bars[0]["remainingPercent"] == 82.0


def test_fetch_account_reads_billing_and_optional_metadata(monkeypatch, tmp_path):
    now = int(datetime.now(timezone.utc).timestamp())
    auth_path = tmp_path / "auth.json.ida"
    write_auth(auth_path)
    seen_requests = []

    def fake_grok_request(auth, resource, query=None):
        seen_requests.append((resource, query))
        if resource == "billing" and query == "format=credits":
            return 200, billing_credits_payload(now)
        if resource == "user":
            return 200, {"email": "ida@example.com", "userId": "user-1", "hasGrokCodeAccess": True}
        raise AssertionError((resource, query))

    monkeypatch.setattr(grok, "grok_request", fake_grok_request)

    account = grok.fetch_account("ida", auth_path, True)

    assert seen_requests == [("billing", "format=credits"), ("user", None)]
    assert account["ok"] is True
    assert account["label"] == "ida"
    assert account["windows"][0]["label"] == "monthly"
    assert account["windows"][0]["usedPercent"] == 18.0


def test_fetch_account_falls_back_to_legacy_billing_payload(monkeypatch, tmp_path):
    now = int(datetime.now(timezone.utc).timestamp())
    auth_path = tmp_path / "auth.json.ida"
    write_auth(auth_path)
    seen_requests = []

    def fake_grok_request(auth, resource, query=None):
        seen_requests.append((resource, query))
        if resource == "billing" and query == "format=credits":
            return 400, {"error": "Timeout expired"}
        if resource == "billing":
            return 200, billing_payload(now)
        if resource == "user":
            return 200, {"email": "ida@example.com", "userId": "user-1", "hasGrokCodeAccess": True}
        raise AssertionError((resource, query))

    monkeypatch.setattr(grok, "grok_request", fake_grok_request)

    account = grok.fetch_account("ida", auth_path, True)

    assert seen_requests == [("billing", "format=credits"), ("billing", None), ("user", None)]
    assert account["ok"] is True
    assert account["usedCredits"] == 1500
    assert account["monthlyLimitCredits"] == 15000

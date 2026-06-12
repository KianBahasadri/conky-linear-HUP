import json
from datetime import datetime, timezone

import fetch_cursor_usage as cursor


def write_auth(path, token="token", refresh_token="refresh"):
    path.write_text(json.dumps({"accessToken": token, "refreshToken": refresh_token}), encoding="utf-8")


def usage_payload(now):
    return {
        "billingCycleStart": str((now - 3600) * 1000),
        "billingCycleEnd": str((now + 86400) * 1000),
        "planUsage": {
            "autoPercentUsed": 12.888,
            "apiPercentUsed": 1.066,
            "totalPercentUsed": 6.977,
        },
        "displayMessage": "You've used 31% of your included usage",
    }


def test_discover_auth_files_prefers_suffixed_files_and_marks_selected(monkeypatch, tmp_path):
    work = tmp_path / "auth.json.ida"
    personal = tmp_path / "auth.json.kian"
    write_auth(work, token="ida-token")
    write_auth(personal, token="kian-token")
    (tmp_path / "auth.json").symlink_to(work)
    monkeypatch.setenv("CURSOR_HOME", str(tmp_path))

    discovered = cursor.discover_auth_files()

    assert [(label, selected) for label, _, selected in discovered] == [
        ("ida", True),
        ("kian", False),
    ]


def test_normalize_usage_creates_monthly_auto_and_api_buckets():
    now = int(datetime.now(timezone.utc).timestamp())
    account = cursor.normalize_usage(
        {"label": "ida"},
        usage_payload(now),
        {"email": "ida@example.com", "userId": 123},
        {"planInfo": {"planName": "Pro", "includedAmountCents": 2000}},
        True,
    )
    bars = cursor.flatten_bars([account])

    assert account["ok"] is True
    assert account["email"] == "ida@example.com"
    assert account["planType"] == "Pro"
    assert [bar["window"] for bar in bars] == ["auto", "api"]
    assert bars[0]["usedPercent"] == 12.9
    assert bars[1]["usedPercent"] == 1.1
    assert bars[0]["resetAfterSeconds"] > 0
    assert bars[0]["windowSeconds"] == 90000


def test_fetch_account_reads_usage_and_optional_metadata(monkeypatch, tmp_path):
    now = int(datetime.now(timezone.utc).timestamp())
    auth_path = tmp_path / "auth.json.ida"
    write_auth(auth_path)
    seen_methods = []

    def fake_cursor_request(auth, method):
        seen_methods.append(method)
        if method == "GetCurrentPeriodUsage":
            return 200, usage_payload(now)
        if method == "GetMe":
            return 200, {"email": "ida@example.com", "userId": 123}
        if method == "GetPlanInfo":
            return 200, {"planInfo": {"planName": "Pro", "includedAmountCents": 2000}}
        raise AssertionError(method)

    monkeypatch.setattr(cursor, "cursor_request", fake_cursor_request)

    account = cursor.fetch_account("ida", auth_path, True)

    assert seen_methods == ["GetCurrentPeriodUsage", "GetMe", "GetPlanInfo"]
    assert account["ok"] is True
    assert account["isSelected"] is True
    assert account["planType"] == "Pro"

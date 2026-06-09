import json
from datetime import datetime, timezone

import fetch_claude_usage as claude


def write_credentials(path, token="token", subscription="pro"):
    path.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": token,
                    "subscriptionType": subscription,
                }
            }
        ),
        encoding="utf-8",
    )


def test_discover_credentials_prefers_suffixed_files(monkeypatch, tmp_path):
    work = tmp_path / ".credentials.json.kian"
    personal = tmp_path / ".credentials.json.sepehr"
    write_credentials(work)
    write_credentials(personal)
    (tmp_path / ".credentials.json").symlink_to(personal)
    monkeypatch.setenv("CLAUDE_HOME", str(tmp_path))

    discovered = claude.discover_credentials()

    assert [(label, selected) for label, _, selected in discovered] == [
        ("kian", False),
        ("sepehr", True),
    ]


def test_usage_from_headers_normalizes_unified_limits():
    now = int(datetime.now(timezone.utc).timestamp())
    headers = {
        "anthropic-ratelimit-unified-5h-utilization": "0.424",
        "anthropic-ratelimit-unified-5h-reset": str(now + 3600),
        "anthropic-ratelimit-unified-7d-utilization": "0.7",
        "anthropic-ratelimit-unified-7d-reset": str(now + 86400),
    }

    usage = claude.usage_from_headers(headers)
    account = claude.account_from_usage(
        {
            "label": "work",
            "email": "",
            "plan_type": "pro",
        },
        usage,
        True,
    )
    bars = claude.flatten_bars([account])

    assert account["ok"] is True
    assert account["label"] == "work"
    assert account["planType"] == "pro"
    assert [bar["window"] for bar in bars] == ["5h", "weekly"]
    assert bars[0]["usedPercent"] == 42.4
    assert bars[1]["remainingPercent"] == 30


def test_fetches_multiple_accounts(monkeypatch, tmp_path):
    now = int(datetime.now(timezone.utc).timestamp())
    write_credentials(tmp_path / ".credentials.json.kian", token="kian-token")
    write_credentials(tmp_path / ".credentials.json.sepehr", token="sepehr-token")
    (tmp_path / ".credentials.json").symlink_to(tmp_path / ".credentials.json.sepehr")
    monkeypatch.setenv("CLAUDE_HOME", str(tmp_path))
    monkeypatch.setattr(claude, "CACHE_DIR", tmp_path / "cache")

    seen_tokens = []

    def fake_fetch_quota_usage(auth):
        seen_tokens.append(auth["access_token"])
        return (
            {
                "five_hour": {"used_percentage": 10, "resets_at": now + 3600},
                "seven_day": {"used_percentage": 20, "resets_at": now + 86400},
            },
            200,
        )

    monkeypatch.setattr(claude, "fetch_quota_usage", fake_fetch_quota_usage)

    accounts = [claude.fetch_account(label, path, selected) for label, path, selected in claude.discover_credentials()]

    assert [account["label"] for account in accounts] == ["kian", "sepehr"]
    assert [account["isSelected"] for account in accounts] == [False, True]
    assert [account["ok"] for account in accounts] == [True, True]
    assert seen_tokens == ["kian-token", "sepehr-token"]
    assert [bar["account"] for bar in claude.flatten_bars(accounts)] == ["kian", "kian", "sepehr", "sepehr"]


def test_fetch_account_uses_fresh_cache(monkeypatch, tmp_path):
    now = int(datetime.now(timezone.utc).timestamp())
    credentials_path = tmp_path / ".credentials.json.kian"
    write_credentials(credentials_path)
    monkeypatch.setattr(claude, "CACHE_DIR", tmp_path / "cache")
    claude.write_account_cache(
        "kian",
        {
            "five_hour": {"used_percentage": 12, "resets_at": now + 3600},
            "seven_day": {"used_percentage": 34, "resets_at": now + 86400},
        },
        200,
    )
    monkeypatch.setattr(
        claude,
        "fetch_quota_usage",
        lambda auth: (_ for _ in ()).throw(AssertionError("should not fetch")),
    )

    account = claude.fetch_account("kian", credentials_path, True)

    assert account["ok"] is True
    assert [window["usedPercent"] for window in account["windows"]] == [12.0, 34.0]

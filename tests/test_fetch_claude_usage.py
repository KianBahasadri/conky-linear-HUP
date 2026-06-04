from datetime import datetime, timezone

import fetch_claude_usage as claude


def test_normalize_usage_with_statusline_rate_limits(monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp())
    monkeypatch.setenv("CLAUDE_PLAN_TYPE", "max")
    monkeypatch.setenv("CLAUDE_USAGE_LABEL", "work")
    monkeypatch.setattr(
        claude,
        "read_auth_status",
        lambda: {"email": "user@example.com", "subscriptionType": "pro"},
    )

    output = claude.normalize_usage(
        {
            "rate_limits": {
                "five_hour": {"used_percentage": 42.4, "resets_at": now + 3600},
                "seven_day": {"used_percentage": 70, "resets_at": now + 86400},
            }
        }
    )

    assert output["ok"] is True
    assert output["provider"] == "Claude"
    assert output["accounts"][0]["label"] == "work"
    assert output["accounts"][0]["planType"] == "max"
    assert [bar["window"] for bar in output["bars"]] == ["5h", "weekly"]
    assert output["bars"][0]["usedPercent"] == 42.4
    assert output["bars"][1]["remainingPercent"] == 30


def test_normalize_usage_waiting_for_rate_limits(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLAN_TYPE", raising=False)
    monkeypatch.delenv("CLAUDE_USAGE_LABEL", raising=False)
    monkeypatch.setattr(
        claude,
        "read_auth_status",
        lambda: {"email": "user@example.com", "subscriptionType": "pro"},
    )

    output = claude.normalize_usage({})

    assert output["ok"] is False
    assert output["accounts"][0]["ok"] is False
    assert output["accounts"][0]["label"] == "claude"
    assert "Waiting for Claude Code statusline rate_limits" in output["error"]
    assert output["bars"] == []

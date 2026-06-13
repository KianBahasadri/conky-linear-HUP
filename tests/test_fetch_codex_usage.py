from datetime import datetime, timezone
from pathlib import Path

import fetch_codex_usage as codex


def window(label, used_percent, reset_at, window_seconds):
    return {
        "label": label,
        "usedPercent": used_percent,
        "remainingPercent": 100 - used_percent,
        "resetsAt": datetime.fromtimestamp(reset_at, tz=timezone.utc).isoformat(),
        "resetAtEpoch": reset_at,
        "resetAfterSeconds": 3600,
        "windowSeconds": window_seconds,
    }


def local_rate_limits(now):
    return {
        "eventEpoch": now,
        "path": Path("/tmp/rollout-aryk.jsonl"),
        "rateLimits": {
            "plan_type": "plus",
            "primary": {
                "used_percent": 82,
                "window_minutes": 300,
                "resets_at": now + 12000,
            },
            "secondary": {
                "used_percent": 39,
                "window_minutes": 10080,
                "resets_at": now + 520000,
            },
        },
    }


def test_local_rate_limits_follow_matching_account_after_profile_switch():
    now = int(datetime.now(timezone.utc).timestamp())
    aryk_primary_reset = now + 12000
    aryk_secondary_reset = now + 520000
    accounts = [
        {
            "ok": True,
            "label": "aryk",
            "planType": "plus",
            "isSelected": False,
            "windows": [
                window("5h", 80, aryk_primary_reset, codex.FIVE_HOUR_WINDOW_SECONDS),
                window("weekly", 39, aryk_secondary_reset, codex.WEEKLY_WINDOW_SECONDS),
            ],
        },
        {
            "ok": True,
            "label": "ryan",
            "planType": "plus",
            "isSelected": True,
            "windows": [
                window("5h", 1, now + 17000, codex.FIVE_HOUR_WINDOW_SECONDS),
                window("weekly", 1, now + 600000, codex.WEEKLY_WINDOW_SECONDS),
            ],
        },
    ]

    codex.apply_local_rate_limits(accounts, local_rate_limits(now))

    assert accounts[0]["localRateLimits"] is True
    assert [item["usedPercent"] for item in accounts[0]["windows"]] == [82.0, 39.0]
    assert "localRateLimits" not in accounts[1]
    assert [item["usedPercent"] for item in accounts[1]["windows"]] == [1, 1]


def test_unmatched_local_rate_limits_are_ignored():
    now = int(datetime.now(timezone.utc).timestamp())
    accounts = [
        {
            "ok": True,
            "label": "ryan",
            "planType": "plus",
            "isSelected": True,
            "windows": [
                window("5h", 1, now + 17000, codex.FIVE_HOUR_WINDOW_SECONDS),
                window("weekly", 1, now + 600000, codex.WEEKLY_WINDOW_SECONDS),
            ],
        }
    ]

    codex.apply_local_rate_limits(accounts, local_rate_limits(now))

    assert "localRateLimits" not in accounts[0]
    assert [item["usedPercent"] for item in accounts[0]["windows"]] == [1, 1]


def test_ambiguous_local_rate_limit_match_is_ignored():
    now = int(datetime.now(timezone.utc).timestamp())
    matching_windows = [
        window("5h", 10, now + 12000, codex.FIVE_HOUR_WINDOW_SECONDS),
        window("weekly", 20, now + 520000, codex.WEEKLY_WINDOW_SECONDS),
    ]
    accounts = [
        {
            "ok": True,
            "label": label,
            "planType": "plus",
            "isSelected": False,
            "windows": [dict(item) for item in matching_windows],
        }
        for label in ("one", "two")
    ]

    codex.apply_local_rate_limits(accounts, local_rate_limits(now))

    assert all("localRateLimits" not in account for account in accounts)
    assert all([item["usedPercent"] for item in account["windows"]] == [10, 20] for account in accounts)

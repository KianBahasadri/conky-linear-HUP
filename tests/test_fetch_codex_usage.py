import json
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


def test_format_usage_windows_includes_values_and_reset_details():
    reset_at = 1_800_000_000
    values = codex.format_usage_windows(
        [window("weekly", 93.0, reset_at, codex.WEEKLY_WINDOW_SECONDS)]
    )

    assert values == (
        "weekly(used=93.0%,remaining=7.0%,reset=2027-01-15T08:00:00+00:00,"
        "reset_after=3600s,window=604800s)"
    )


def test_local_rate_limit_log_includes_before_and_after_values(monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp())
    accounts = [
        {
            "ok": True,
            "label": "aryk",
            "planType": "plus",
            "windows": [
                window("5h", 80, now + 12000, codex.FIVE_HOUR_WINDOW_SECONDS),
                window("weekly", 39, now + 520000, codex.WEEKLY_WINDOW_SECONDS),
            ],
        }
    ]
    events = []
    monkeypatch.setattr(codex, "log_event", events.append)

    codex.apply_local_rate_limits(accounts, local_rate_limits(now))

    assert any(
        "previous_values=5h(used=80.0%,remaining=20.0%" in event
        and "local_values=5h(used=82.0%,remaining=18.0%" in event
        and "final_values=5h(used=82.0%,remaining=18.0%" in event
        for event in events
    )


def test_fresh_endpoint_data_is_authoritative_for_every_account(monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp())
    accounts = [
        {
            "ok": True,
            "endpointFresh": True,
            "label": "aryk",
            "planType": "plus",
            "windows": [
                window("5h", 100, now + 12000, codex.FIVE_HOUR_WINDOW_SECONDS),
                window("weekly", 100, now + 520000, codex.WEEKLY_WINDOW_SECONDS),
            ],
        },
        {
            "ok": True,
            "endpointFresh": True,
            "label": "ryan",
            "planType": "plus",
            "windows": [
                window("5h", 20, now + 17000, codex.FIVE_HOUR_WINDOW_SECONDS),
                window("weekly", 30, now + 600000, codex.WEEKLY_WINDOW_SECONDS),
            ],
        },
    ]
    ryan_local_sample = {
        "eventEpoch": now,
        "path": Path("/tmp/rollout-ryan.jsonl"),
        "rateLimits": {
            "plan_type": "plus",
            "primary": {
                "used_percent": 90,
                "window_minutes": 300,
                "resets_at": now + 17000,
            },
            "secondary": {
                "used_percent": 80,
                "window_minutes": 10080,
                "resets_at": now + 600000,
            },
        },
    }
    events = []
    monkeypatch.setattr(codex, "log_event", events.append)

    codex.apply_local_rate_limits(accounts, [local_rate_limits(now), ryan_local_sample])

    assert [item["usedPercent"] for item in accounts[0]["windows"]] == [100, 100]
    assert [item["usedPercent"] for item in accounts[1]["windows"]] == [20, 30]
    assert all("localRateLimits" not in account for account in accounts)
    assert sum("endpoint data is authoritative" in event for event in events) == 2


def test_final_account_log_includes_source_and_values(monkeypatch):
    events = []
    monkeypatch.setattr(codex, "log_event", events.append)
    account = {
        "ok": True,
        "label": "ricky",
        "planType": "plus",
        "isSelected": True,
        "windows": [window("weekly", 1.0, 1_800_000_000, codex.WEEKLY_WINDOW_SECONDS)],
        "localRateLimits": True,
        "localRateLimitsPath": "/tmp/rollout-ricky.jsonl",
        "localRateLimitsUpdatedAt": "2027-01-15T07:00:00+00:00",
    }

    codex.log_final_account(account)

    assert len(events) == 1
    assert "stage=final" in events[0]
    assert "source=local" in events[0]
    assert "values=weekly(used=1.0%,remaining=99.0%" in events[0]
    assert "local_path=rollout-ricky.jsonl" in events[0]


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


def test_reached_api_quota_overrides_stale_window_percentage():
    now = int(datetime.now(timezone.utc).timestamp())
    auth = {"label": "ahmad", "email": "", "account_id": ""}
    usage = {
        "plan_type": "plus",
        "rate_limit": {
            "allowed": False,
            "limit_reached": True,
            "primary_window": {
                "used_percent": 47,
                "limit_window_seconds": codex.WEEKLY_WINDOW_SECONDS,
                "reset_after_seconds": 3600,
                "reset_at": now + 3600,
            },
            "secondary_window": None,
        },
    }

    account = codex.normalize_usage(auth, usage, False)

    assert account["endpointFresh"] is True
    assert account["windows"][0]["usedPercent"] == 100.0
    assert account["windows"][0]["remainingPercent"] == 0


def test_reached_limit_pins_only_the_blocking_window():
    now = int(datetime.now(timezone.utc).timestamp())
    primary_reset = now + 2700
    weekly_reset = now + 589000
    auth = {"label": "ricky", "email": "", "account_id": ""}
    usage = {
        "plan_type": "plus",
        "rate_limit": {
            "allowed": False,
            "limit_reached": True,
            "primary_window": {
                "used_percent": 100,
                "limit_window_seconds": codex.FIVE_HOUR_WINDOW_SECONDS,
                "reset_after_seconds": 2700,
                "reset_at": primary_reset,
            },
            "secondary_window": {
                "used_percent": 16,
                "limit_window_seconds": codex.WEEKLY_WINDOW_SECONDS,
                "reset_after_seconds": 589000,
                "reset_at": weekly_reset,
            },
        },
        "rate_limit_upsell": {
            "banner_type": "plus_rate_limit_reached",
            "reset_at": primary_reset,
        },
    }

    account = codex.normalize_usage(auth, usage, False)

    assert [item["usedPercent"] for item in account["windows"]] == [100.0, 16.0]
    assert account["windows"][1]["remainingPercent"] == 84.0


def test_reached_limit_without_upsell_pins_the_fullest_window():
    now = int(datetime.now(timezone.utc).timestamp())
    auth = {"label": "ricky", "email": "", "account_id": ""}
    usage = {
        "plan_type": "plus",
        "rate_limit": {
            "allowed": False,
            "limit_reached": True,
            "primary_window": {
                "used_percent": 100,
                "limit_window_seconds": codex.FIVE_HOUR_WINDOW_SECONDS,
                "reset_after_seconds": 2700,
                "reset_at": now + 2700,
            },
            "secondary_window": {
                "used_percent": 16,
                "limit_window_seconds": codex.WEEKLY_WINDOW_SECONDS,
                "reset_after_seconds": 589000,
                "reset_at": now + 589000,
            },
        },
    }

    account = codex.normalize_usage(auth, usage, False)

    assert [item["usedPercent"] for item in account["windows"]] == [100.0, 16.0]


def test_local_weekly_primary_window_matches_api_weekly_window():
    now = int(datetime.now(timezone.utc).timestamp())
    reset_at = now + 3600
    accounts = [
        {
            "ok": True,
            "label": "ahmad",
            "planType": "plus",
            "windows": [window("weekly", 47, reset_at, codex.WEEKLY_WINDOW_SECONDS)],
        }
    ]
    local_sample = {
        "eventEpoch": now,
        "path": Path("/tmp/rollout-ahmad.jsonl"),
        "rateLimits": {
            "plan_type": "plus",
            "primary": {"used_percent": 47, "window_minutes": 10080, "resets_at": reset_at},
            "secondary": None,
        },
        "exhausted": True,
    }

    codex.apply_local_rate_limits(accounts, [local_sample])

    assert accounts[0]["localRateLimits"] is True
    assert accounts[0]["windows"][0]["label"] == "weekly"
    assert accounts[0]["windows"][0]["usedPercent"] == 100.0


def test_normalize_usage_includes_gpt_reserve_as_third_window():
    now = int(datetime.now(timezone.utc).timestamp())
    auth = {"label": "ricky", "email": "", "account_id": ""}
    usage = {
        "plan_type": "plus",
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {
                "used_percent": 0,
                "limit_window_seconds": codex.FIVE_HOUR_WINDOW_SECONDS,
                "reset_after_seconds": 17631,
                "reset_at": now + 17631,
            },
            "secondary_window": {
                "used_percent": 16,
                "limit_window_seconds": codex.WEEKLY_WINDOW_SECONDS,
                "reset_after_seconds": 586334,
                "reset_at": now + 586334,
            },
        },
        "additional_rate_limits": [
            {
                "limit_name": "gpt-reserve",
                "metered_feature": "base_model_inference",
                "rate_limit": {
                    "allowed": True,
                    "limit_reached": False,
                    "primary_window": {
                        "used_percent": 0,
                        "limit_window_seconds": codex.WEEKLY_WINDOW_SECONDS,
                        "reset_after_seconds": 604800,
                        "reset_at": now + 604800,
                    },
                    "secondary_window": None,
                },
            }
        ],
    }

    account = codex.normalize_usage(auth, usage, False)

    assert [item["label"] for item in account["windows"]] == ["5h", "weekly", "reserve"]
    assert account["windows"][2]["usedPercent"] == 0.0
    assert account["windows"][2]["remainingPercent"] == 100.0
    assert account["windows"][2]["windowSeconds"] == codex.WEEKLY_WINDOW_SECONDS


def test_reserve_window_prefers_weekly_when_both_windows_exist():
    now = int(datetime.now(timezone.utc).timestamp())
    auth = {"label": "ricky", "email": "", "account_id": ""}
    usage = {
        "plan_type": "plus",
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {
                "used_percent": 10,
                "limit_window_seconds": codex.FIVE_HOUR_WINDOW_SECONDS,
                "reset_after_seconds": 3600,
                "reset_at": now + 3600,
            },
            "secondary_window": {
                "used_percent": 20,
                "limit_window_seconds": codex.WEEKLY_WINDOW_SECONDS,
                "reset_after_seconds": 86400,
                "reset_at": now + 86400,
            },
        },
        "additional_rate_limits": [
            {
                "limit_name": "gpt-reserve",
                "metered_feature": "base_model_inference",
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 5,
                        "limit_window_seconds": codex.FIVE_HOUR_WINDOW_SECONDS,
                        "reset_after_seconds": 1800,
                        "reset_at": now + 1800,
                    },
                    "secondary_window": {
                        "used_percent": 8,
                        "limit_window_seconds": codex.WEEKLY_WINDOW_SECONDS,
                        "reset_after_seconds": 500000,
                        "reset_at": now + 500000,
                    },
                },
            }
        ],
    }

    account = codex.normalize_usage(auth, usage, False)

    assert [item["label"] for item in account["windows"]] == ["5h", "weekly", "reserve"]
    assert account["windows"][2]["usedPercent"] == 8.0
    assert account["windows"][2]["windowSeconds"] == codex.WEEKLY_WINDOW_SECONDS


def test_non_reserve_additional_limits_are_ignored():
    now = int(datetime.now(timezone.utc).timestamp())
    auth = {"label": "ahmad", "email": "", "account_id": ""}
    usage = {
        "plan_type": "plus",
        "rate_limit": {
            "allowed": True,
            "limit_reached": False,
            "primary_window": {
                "used_percent": 10,
                "limit_window_seconds": codex.FIVE_HOUR_WINDOW_SECONDS,
                "reset_after_seconds": 3600,
                "reset_at": now + 3600,
            },
            "secondary_window": {
                "used_percent": 20,
                "limit_window_seconds": codex.WEEKLY_WINDOW_SECONDS,
                "reset_after_seconds": 86400,
                "reset_at": now + 86400,
            },
        },
        "additional_rate_limits": [
            {
                "limit_name": "codex_other",
                "metered_feature": "codex_other",
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 70,
                        "limit_window_seconds": 900,
                        "reset_after_seconds": 900,
                        "reset_at": now + 900,
                    }
                },
            }
        ],
    }

    account = codex.normalize_usage(auth, usage, False)

    assert [item["label"] for item in account["windows"]] == ["5h", "weekly"]


def test_reached_limit_does_not_pin_reserve_window():
    now = int(datetime.now(timezone.utc).timestamp())
    primary_reset = now + 2700
    weekly_reset = now + 589000
    reserve_reset = now + 604800
    auth = {"label": "ricky", "email": "", "account_id": ""}
    usage = {
        "plan_type": "plus",
        "rate_limit": {
            "allowed": False,
            "limit_reached": True,
            "primary_window": {
                "used_percent": 100,
                "limit_window_seconds": codex.FIVE_HOUR_WINDOW_SECONDS,
                "reset_after_seconds": 2700,
                "reset_at": primary_reset,
            },
            "secondary_window": {
                "used_percent": 16,
                "limit_window_seconds": codex.WEEKLY_WINDOW_SECONDS,
                "reset_after_seconds": 589000,
                "reset_at": weekly_reset,
            },
        },
        "rate_limit_upsell": {
            "banner_type": "plus_rate_limit_reached",
            "reset_at": primary_reset,
        },
        "additional_rate_limits": [
            {
                "limit_name": "gpt-reserve",
                "metered_feature": "base_model_inference",
                "rate_limit": {
                    "allowed": True,
                    "limit_reached": False,
                    "primary_window": {
                        "used_percent": 0,
                        "limit_window_seconds": codex.WEEKLY_WINDOW_SECONDS,
                        "reset_after_seconds": 604800,
                        "reset_at": reserve_reset,
                    },
                    "secondary_window": None,
                },
            }
        ],
    }

    account = codex.normalize_usage(auth, usage, False)

    assert [item["usedPercent"] for item in account["windows"]] == [100.0, 16.0, 0.0]
    assert account["windows"][2]["label"] == "reserve"


def test_local_rate_limits_preserve_reserve_window():
    now = int(datetime.now(timezone.utc).timestamp())
    reserve = window("reserve", 0, now + 604800, codex.WEEKLY_WINDOW_SECONDS)
    accounts = [
        {
            "ok": True,
            "label": "ricky",
            "planType": "plus",
            "windows": [
                window("5h", 80, now + 12000, codex.FIVE_HOUR_WINDOW_SECONDS),
                window("weekly", 39, now + 520000, codex.WEEKLY_WINDOW_SECONDS),
                reserve,
            ],
        }
    ]

    codex.apply_local_rate_limits(accounts, local_rate_limits(now))

    assert [item["label"] for item in accounts[0]["windows"]] == ["5h", "weekly", "reserve"]
    assert [item["usedPercent"] for item in accounts[0]["windows"]] == [82.0, 39.0, 0]
    assert accounts[0]["windows"][2] is reserve


def test_exhausted_local_sample_pins_only_the_blocking_window():
    now = int(datetime.now(timezone.utc).timestamp())
    sample = {
        "eventEpoch": now,
        "path": Path("/tmp/rollout-ricky.jsonl"),
        "rateLimits": {
            "plan_type": "plus",
            "primary": {"used_percent": 100, "window_minutes": 300, "resets_at": now + 2700},
            "secondary": {"used_percent": 16, "window_minutes": 10080, "resets_at": now + 589000},
        },
        "exhausted": True,
    }

    windows = codex.local_rate_limit_windows(sample)

    assert [window["label"] for window in windows] == ["5h", "weekly"]
    assert [window["usedPercent"] for window in windows] == [100.0, 16.0]


def test_rollout_usage_limit_error_marks_latest_sample_exhausted(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    reset_at = int(now.timestamp()) + 3600
    path = tmp_path / "rollout-ahmad.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": now.isoformat(),
                            "rate_limits": {
                                "plan_type": "plus",
                                "primary": {
                                    "used_percent": 47,
                                    "window_minutes": 10080,
                                    "resets_at": reset_at,
                                },
                                "secondary": None,
                            },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": datetime.fromtimestamp(
                            now.timestamp() + 1, tz=timezone.utc
                        ).isoformat(),
                        "payload": {
                            "type": "task_complete",
                            "error": {"codex_error_info": "usage_limit_exceeded"},
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(codex, "latest_rollout_paths", lambda: [path])

    samples = codex.read_local_rate_limit_samples()

    assert len(samples) == 1
    assert samples[0]["exhausted"] is True
    assert codex.local_rate_limit_windows(samples[0])[0]["usedPercent"] == 100.0

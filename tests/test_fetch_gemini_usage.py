import json
from datetime import datetime, timezone

import fetch_gemini_usage as gemini


def credential(token):
    return json.dumps(
        {
            "token": {
                "access_token": token,
                "refresh_token": "refresh",
                "token_type": "Bearer",
                "expiry": "2026-06-12T17:07:19-04:00",
            },
            "auth_method": "consumer",
        }
    )


def test_discover_profiles_marks_rotation_current(monkeypatch, tmp_path):
    (tmp_path / "profiles").write_text("kian\nbaba\ninvalid profile\n", encoding="utf-8")
    (tmp_path / "current").write_text("baba\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_ANTIGRAVITY_STATE_DIR", str(tmp_path))

    assert gemini.discover_profiles() == [("baba", True), ("kian", False)]


def test_read_auth_uses_active_item_for_selected_profile(monkeypatch):
    calls = []

    def fake_lookup(service, username):
        calls.append((service, username))
        return credential(f"{service}-{username}")

    monkeypatch.setattr(gemini, "lookup_keyring_secret", fake_lookup)

    selected = gemini.read_auth("baba", True)
    inactive = gemini.read_auth("kian", False)

    assert calls == [
        ("gemini", "antigravity"),
        ("rotate-antigravity", "kian"),
    ]
    assert selected["access_token"] == "gemini-antigravity"
    assert inactive["access_token"] == "rotate-antigravity-kian"


def test_normalize_windows_groups_flash_and_pro_and_skips_unavailable():
    now = datetime(2026, 6, 12, 20, 0, tzinfo=timezone.utc)
    payload = {
        "buckets": [
            {
                "modelId": "gemini-2.5-flash",
                "tokenType": "WTUS",
                "remainingFraction": 0.8,
                "resetTime": "2026-06-13T20:00:00Z",
            },
            {
                "modelId": "gemini-3-flash-preview",
                "tokenType": "REQUESTS",
                "remainingFraction": 0.6,
                "resetTime": "2026-06-13T20:00:00Z",
            },
            {
                "modelId": "gemini-3.1-pro-preview",
                "tokenType": "REQUESTS",
                "remainingFraction": 0.9,
                "resetTime": "2026-06-13T18:00:00Z",
            },
            {
                "modelId": "gemini-2.5-pro",
                "tokenType": "REQUESTS",
                "remainingFraction": 0,
                "resetTime": "1970-01-01T00:00:00Z",
            },
            {
                "modelId": "claude-sonnet-4-6",
                "tokenType": "WTUS",
                "remainingFraction": 0.1,
                "resetTime": "2026-06-13T20:00:00Z",
            },
        ]
    }

    windows = gemini.normalize_windows(payload, now)

    assert [window["label"] for window in windows] == ["flash", "pro"]
    assert windows[0]["usedPercent"] == 40
    assert windows[1]["remainingPercent"] == 90
    assert windows[0]["windowSeconds"] == gemini.DAY_SECONDS


def test_normalize_windows_uses_fixed_week_for_long_reset():
    now = datetime(2026, 6, 12, 20, 0, tzinfo=timezone.utc)
    payload = {
        "buckets": [
            {
                "modelId": "gemini-2.5-flash",
                "tokenType": "WTUS",
                "remainingFraction": 0.2,
                "resetTime": "2026-06-19T17:12:01Z",
            }
        ]
    }

    windows = gemini.normalize_windows(payload, now)

    assert windows[0]["windowSeconds"] == gemini.WEEK_SECONDS


def test_fetch_account_uses_stale_cache_after_auth_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(gemini, "CACHE_DIR", tmp_path)
    cached = {
        "ok": True,
        "label": "kian",
        "planType": "pro",
        "isSelected": False,
        "windows": [{"label": "flash", "usedPercent": 25}],
    }
    gemini.write_account_cache(cached)
    monkeypatch.setattr(
        gemini,
        "read_auth",
        lambda label, selected: (_ for _ in ()).throw(RuntimeError("expired token")),
    )

    account = gemini.fetch_account("kian", True)

    assert account["ok"] is True
    assert account["isSelected"] is True
    assert account["staleCache"] is True
    assert "expired token" in account["error"]

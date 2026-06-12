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


def test_normalize_windows_combines_flash_and_pro_separately_from_other_quotas():
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
                "modelId": "gemini-embedding-001",
                "tokenType": "REQUESTS",
                "remainingFraction": 0.1,
                "resetTime": "2026-06-13T20:00:00Z",
            },
            {
                "modelId": "claude-sonnet-4-6",
                "tokenType": "WTUS",
                "remainingFraction": 0.5,
                "resetTime": "2026-06-13T20:00:00Z",
            },
        ]
    }

    windows = gemini.normalize_windows(payload, now)

    assert [window["label"] for window in windows] == ["gemini", "other"]
    assert windows[0]["usedPercent"] == 23.3
    assert windows[0]["models"] == [
        "gemini-2.5-flash",
        "gemini-3-flash-preview",
        "gemini-3.1-pro-preview",
    ]
    assert windows[1]["usedPercent"] == 70
    assert windows[1]["models"] == ["claude-sonnet-4-6", "gemini-embedding-001"]
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
        "windows": [{"label": "gemini", "usedPercent": 25}],
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


def test_selected_account_refreshes_through_agy_after_401(monkeypatch):
    auth_reads = []
    refreshes = []

    def fake_read_auth(label, selected):
        auth_reads.append((label, selected))
        return {"label": label, "access_token": f"token-{len(auth_reads)}"}

    def fake_load_code_assist(auth):
        if auth["access_token"] == "token-1":
            raise gemini.GeminiAuthError("HTTP 401")
        return "project", {"currentTier": {"id": "free-tier"}}

    monkeypatch.setattr(gemini, "read_auth", fake_read_auth)
    monkeypatch.setattr(gemini, "load_code_assist", fake_load_code_assist)
    monkeypatch.setattr(gemini, "fetch_quota", lambda auth, project: {})
    monkeypatch.setattr(
        gemini,
        "normalize_windows",
        lambda payload: [{"label": "gemini", "usedPercent": 10}],
    )
    monkeypatch.setattr(gemini, "write_account_cache", lambda account: None)
    monkeypatch.setattr(gemini, "refresh_selected_auth", refreshes.append)

    account = gemini.fetch_account("kian", True)

    assert account["ok"] is True
    assert auth_reads == [("kian", True), ("kian", True)]
    assert refreshes == ["kian"]


def test_inactive_account_does_not_refresh_through_agy(monkeypatch, tmp_path):
    monkeypatch.setattr(gemini, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(gemini, "read_auth", lambda label, selected: {"access_token": "expired"})
    monkeypatch.setattr(
        gemini,
        "load_code_assist",
        lambda auth: (_ for _ in ()).throw(gemini.GeminiAuthError("HTTP 401")),
    )
    monkeypatch.setattr(
        gemini,
        "refresh_selected_auth",
        lambda label: (_ for _ in ()).throw(AssertionError("inactive profile must not be refreshed")),
    )

    account = gemini.fetch_account("baba", False)

    assert account["ok"] is False
    assert "HTTP 401" in account["error"]


def test_refresh_selected_auth_runs_agy_models(monkeypatch, tmp_path):
    (tmp_path / "current").write_text("kian\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_ANTIGRAVITY_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(gemini.shutil, "which", lambda command: "/usr/bin/agy")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return gemini.subprocess.CompletedProcess(command, 0, stdout="models", stderr="")

    monkeypatch.setattr(gemini.subprocess, "run", fake_run)

    gemini.refresh_selected_auth("kian")

    assert calls[0][0] == ["/usr/bin/agy", "models"]
    assert calls[0][1]["timeout"] == gemini.DEFAULT_AUTH_REFRESH_TIMEOUT_SECONDS

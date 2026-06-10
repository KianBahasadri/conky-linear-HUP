import json
from datetime import datetime, timezone

import fetch_claude_usage as claude


def write_credentials(path, token="token", subscription="pro", refresh_token=None, expires_at_ms=None):
    oauth = {
        "accessToken": token,
        "subscriptionType": subscription,
    }
    if refresh_token is not None:
        oauth["refreshToken"] = refresh_token
    if expires_at_ms is not None:
        oauth["expiresAt"] = expires_at_ms
    path.write_text(json.dumps({"claudeAiOauth": oauth}), encoding="utf-8")


def usage_headers(now):
    return {
        "anthropic-ratelimit-unified-5h-utilization": "0.1",
        "anthropic-ratelimit-unified-5h-reset": str(now + 3600),
        "anthropic-ratelimit-unified-7d-utilization": "0.2",
        "anthropic-ratelimit-unified-7d-reset": str(now + 86400),
    }


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
    monkeypatch.setattr(claude, "fetch_profile_email", lambda token: f"{token}@example.com")

    accounts = [claude.fetch_account(label, path, selected) for label, path, selected in claude.discover_credentials()]

    assert [account["label"] for account in accounts] == ["kian", "sepehr"]
    assert [account["isSelected"] for account in accounts] == [False, True]
    assert [account["ok"] for account in accounts] == [True, True]
    assert seen_tokens == ["kian-token", "sepehr-token"]
    assert [bar["account"] for bar in claude.flatten_bars(accounts)] == ["kian", "kian", "sepehr", "sepehr"]


def test_refresh_credentials_persists_new_tokens(monkeypatch, tmp_path):
    credentials_path = tmp_path / ".credentials.json.kian"
    write_credentials(credentials_path, token="old", refresh_token="refresh-old", expires_at_ms=123000)
    auth = claude.read_credentials("kian", credentials_path)

    class FakeResponse:
        status = 200

        def read(self):
            return json.dumps(
                {"access_token": "new", "refresh_token": "refresh-new", "expires_in": 28800}
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(claude.urllib.request, "urlopen", fake_urlopen)

    claude.refresh_credentials(auth)

    saved = json.loads(credentials_path.read_text(encoding="utf-8"))["claudeAiOauth"]
    now_ms = int(datetime.now(timezone.utc).timestamp()) * 1000
    assert captured["url"] == claude.TOKEN_URL
    assert captured["body"]["grant_type"] == "refresh_token"
    assert captured["body"]["refresh_token"] == "refresh-old"
    assert captured["body"]["client_id"] == claude.OAUTH_CLIENT_ID
    assert auth["access_token"] == "new"
    assert saved["accessToken"] == "new"
    assert saved["refreshToken"] == "refresh-new"
    assert saved["expiresAt"] >= now_ms + 28000 * 1000
    assert saved["subscriptionType"] == "pro"
    assert credentials_path.stat().st_mode & 0o777 == 0o600


def test_fetch_account_refreshes_expired_token_before_request(monkeypatch, tmp_path):
    now = int(datetime.now(timezone.utc).timestamp())
    credentials_path = tmp_path / ".credentials.json.kian"
    write_credentials(credentials_path, token="expired", refresh_token="refresh-1", expires_at_ms=(now - 60) * 1000)
    monkeypatch.setattr(claude, "CACHE_DIR", tmp_path / "cache")

    def fake_refresh(auth):
        auth["access_token"] = "fresh"
        auth["expires_at"] = now + 28800
        return auth

    monkeypatch.setattr(claude, "refresh_credentials", fake_refresh)

    seen_tokens = []

    def fake_quota_request(auth):
        seen_tokens.append(auth["access_token"])
        return 200, usage_headers(now), ""

    monkeypatch.setattr(claude, "quota_request", fake_quota_request)
    monkeypatch.setattr(claude, "fetch_profile_email", lambda token: "kian@example.com")

    account = claude.fetch_account("kian", credentials_path, False)

    assert account["ok"] is True
    assert seen_tokens == ["fresh"]
    assert json.loads(claude.account_cache_path("kian").read_text(encoding="utf-8"))["email"] == "kian@example.com"


def test_fetch_account_refreshes_token_after_401(monkeypatch, tmp_path):
    now = int(datetime.now(timezone.utc).timestamp())
    credentials_path = tmp_path / ".credentials.json.kian"
    write_credentials(credentials_path, token="revoked", refresh_token="refresh-1", expires_at_ms=(now + 3600) * 1000)
    monkeypatch.setattr(claude, "CACHE_DIR", tmp_path / "cache")

    def fake_refresh(auth):
        auth["access_token"] = "fresh"
        auth["expires_at"] = now + 28800
        return auth

    monkeypatch.setattr(claude, "refresh_credentials", fake_refresh)

    seen_tokens = []

    def fake_quota_request(auth):
        seen_tokens.append(auth["access_token"])
        if auth["access_token"] == "revoked":
            return 401, {}, '{"type":"error","error":{"type":"authentication_error"}}'
        return 200, usage_headers(now), ""

    monkeypatch.setattr(claude, "quota_request", fake_quota_request)
    monkeypatch.setattr(claude, "fetch_profile_email", lambda token: "kian@example.com")

    account = claude.fetch_account("kian", credentials_path, False)

    assert account["ok"] is True
    assert "error" not in account
    assert seen_tokens == ["revoked", "fresh"]


def test_fetch_account_adopts_default_credentials_after_rotation(monkeypatch, tmp_path):
    now = int(datetime.now(timezone.utc).timestamp())
    snapshot_path = tmp_path / ".credentials.json.sepehr"
    write_credentials(snapshot_path, token="dead", refresh_token="refresh-dead", expires_at_ms=(now - 60) * 1000)
    write_credentials(
        tmp_path / ".credentials.json",
        token="active-token",
        refresh_token="active-refresh",
        expires_at_ms=(now + 7200) * 1000,
    )
    monkeypatch.setenv("CLAUDE_HOME", str(tmp_path))
    monkeypatch.setattr(claude, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setenv("CLAUDE_USAGE_TTL", "0")
    claude.write_account_cache(
        "sepehr",
        {"seven_day": {"used_percentage": 2, "resets_at": now + 86400}},
        200,
        email="sepehr@example.com",
    )

    def fake_refresh(auth):
        raise RuntimeError('Claude OAuth token refresh failed: HTTP 400: {"error": "invalid_grant"}')

    monkeypatch.setattr(claude, "refresh_credentials", fake_refresh)
    monkeypatch.setattr(claude, "fetch_profile_email", lambda token: "sepehr@example.com")

    def fake_quota_request(auth):
        if auth["access_token"] != "active-token":
            return 401, {}, '{"type":"error","error":{"type":"authentication_error"}}'
        return 200, usage_headers(now), ""

    monkeypatch.setattr(claude, "quota_request", fake_quota_request)

    account = claude.fetch_account("sepehr", snapshot_path, False)

    saved = json.loads(snapshot_path.read_text(encoding="utf-8"))["claudeAiOauth"]
    assert account["ok"] is True
    assert "error" not in account
    assert saved["accessToken"] == "active-token"
    assert saved["refreshToken"] == "active-refresh"


def test_adopt_default_credentials_rejects_other_account(monkeypatch, tmp_path):
    now = int(datetime.now(timezone.utc).timestamp())
    snapshot_path = tmp_path / ".credentials.json.sepehr"
    write_credentials(snapshot_path, token="dead", refresh_token="refresh-dead", expires_at_ms=(now - 60) * 1000)
    write_credentials(
        tmp_path / ".credentials.json",
        token="active-token",
        refresh_token="active-refresh",
        expires_at_ms=(now + 7200) * 1000,
    )
    monkeypatch.setenv("CLAUDE_HOME", str(tmp_path))
    monkeypatch.setattr(claude, "fetch_profile_email", lambda token: "kian@example.com")
    auth = claude.read_credentials("sepehr", snapshot_path)

    adopted = claude.adopt_default_credentials(
        auth, "sepehr@example.com", RuntimeError("HTTP 400: invalid_grant")
    )

    assert adopted is False
    assert json.loads(snapshot_path.read_text(encoding="utf-8"))["claudeAiOauth"]["accessToken"] == "dead"


def test_adopt_default_credentials_requires_known_email(monkeypatch, tmp_path):
    snapshot_path = tmp_path / ".credentials.json.sepehr"
    write_credentials(snapshot_path, token="dead", refresh_token="refresh-dead", expires_at_ms=123000)
    monkeypatch.setenv("CLAUDE_HOME", str(tmp_path))
    auth = claude.read_credentials("sepehr", snapshot_path)

    assert claude.adopt_default_credentials(auth, "", RuntimeError("HTTP 400: invalid_grant")) is False
    assert claude.adopt_default_credentials(auth, "sepehr@example.com", RuntimeError("HTTP 500")) is False


def test_fetch_account_falls_back_to_stale_cache_when_refresh_fails(monkeypatch, tmp_path):
    now = int(datetime.now(timezone.utc).timestamp())
    credentials_path = tmp_path / ".credentials.json.kian"
    write_credentials(credentials_path, token="revoked", refresh_token="refresh-1", expires_at_ms=(now + 3600) * 1000)
    monkeypatch.setattr(claude, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setenv("CLAUDE_USAGE_TTL", "0")
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
        "quota_request",
        lambda auth: (401, {}, '{"type":"error","error":{"type":"authentication_error"}}'),
    )

    def failing_refresh(auth):
        raise RuntimeError("Claude OAuth token refresh failed: HTTP 400: invalid_grant")

    monkeypatch.setattr(claude, "refresh_credentials", failing_refresh)

    account = claude.fetch_account("kian", credentials_path, False)

    assert account["ok"] is True
    assert account["staleCache"] is True
    assert "invalid_grant" in account["error"]
    assert [window["usedPercent"] for window in account["windows"]] == [12.0, 34.0]


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

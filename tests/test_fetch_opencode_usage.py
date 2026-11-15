import json
import sqlite3

import pytest

import fetch_opencode_usage as opencode


USAGE = {
    "usage": {
        "rolling": {"status": "ok", "percent": 12.5, "resetsAt": "2026-11-15T05:00:00Z"},
        "weekly": {"status": "ok", "percent": 40, "resetsAt": "2026-11-16T00:00:00.000Z"},
        "monthly": {"status": "rate-limited", "percent": 96, "resetsAt": "2026-12-14T02:03:33.000Z"},
    }
}
NOW = 1_794_700_000


def test_parse_usage_maps_go_meters():
    windows = opencode.parse_usage(USAGE, now_epoch=NOW)

    assert [window["label"] for window in windows] == ["5h", "weekly", "monthly"]
    assert windows[0]["usedPercent"] == 12.5
    assert windows[0]["remainingPercent"] == 87.5
    assert windows[0]["windowSeconds"] == opencode.common.FIVE_HOUR_WINDOW_SECONDS
    assert windows[0]["resetAtEpoch"] == int(
        opencode._parse_reset("2026-11-15T05:00:00Z").timestamp()
    )
    assert windows[0]["resetAfterSeconds"] == windows[0]["resetAtEpoch"] - NOW
    assert windows[1]["windowSeconds"] == opencode.common.WEEKLY_WINDOW_SECONDS
    assert windows[2]["usedPercent"] == 100.0
    assert windows[2]["remainingPercent"] == 0.0


def test_parse_usage_requires_each_meter():
    payload = json.loads(json.dumps(USAGE))
    del payload["usage"]["monthly"]

    with pytest.raises(RuntimeError, match="monthly"):
        opencode.parse_usage(payload, now_epoch=NOW)


def test_resolve_auth_prefers_env(monkeypatch):
    monkeypatch.setenv("OPENCODE_API_KEY", "env-key")
    monkeypatch.setenv("OPENCODE_WORKSPACE_ID", "wrk_env")
    monkeypatch.setattr(opencode, "stored_credentials", lambda data_dir=None: ("stored-key", "wrk_stored"))

    assert opencode.resolve_auth() == ("env-key", "wrk_env")


def test_resolve_auth_uses_stored_credentials(monkeypatch):
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.delenv("OPENCODE_WORKSPACE_ID", raising=False)
    monkeypatch.setattr(opencode, "stored_credentials", lambda data_dir=None: ("stored-key", "wrk_stored"))

    assert opencode.resolve_auth() == ("stored-key", "wrk_stored")


def test_stored_credentials_reads_active_key_and_workspace(tmp_path):
    db_path = tmp_path / "opencode.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE credential (
            integration_id TEXT,
            value TEXT,
            active INTEGER
        )
        """
    )
    connection.executemany(
        "INSERT INTO credential (integration_id, value, active) VALUES (?, ?, ?)",
        [
            (
                "opencode-go",
                json.dumps({"type": "key", "key": "old-key"}),
                0,
            ),
            (
                "opencode-go",
                json.dumps({"type": "key", "key": "live-key"}),
                1,
            ),
            (
                "opencode",
                json.dumps({"type": "oauth", "metadata": {"orgID": "wrk_live"}}),
                1,
            ),
        ],
    )
    connection.commit()
    connection.close()
    (tmp_path / "auth.json").write_text(
        json.dumps({"opencode-go": {"type": "api", "key": "legacy-key"}}),
        encoding="utf-8",
    )

    assert opencode.stored_credentials(tmp_path) == ("live-key", "wrk_live")


def test_stored_credentials_falls_back_to_legacy_auth_file(tmp_path):
    (tmp_path / "auth.json").write_text(
        json.dumps({"opencode-go": {"type": "api", "key": "legacy-key"}}),
        encoding="utf-8",
    )

    assert opencode.stored_credentials(tmp_path) == ("legacy-key", None)


class FakeResponse:
    def __init__(self, body):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def test_fetch_usage_sends_bearer_key_and_workspace(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["org"] = request.get_header("X-opencode-org-id")
        captured["accept"] = request.get_header("Accept")
        captured["timeout"] = timeout
        return FakeResponse(USAGE)

    monkeypatch.setattr(opencode.urllib.request, "urlopen", fake_urlopen)
    windows = opencode.fetch_usage("secret-key", "wrk_live", now_epoch=NOW)

    assert captured == {
        "url": opencode.USAGE_URL,
        "authorization": "Bearer secret-key",
        "org": "wrk_live",
        "accept": "application/json",
        "timeout": 15,
    }
    assert [window["label"] for window in windows] == ["5h", "weekly", "monthly"]


def test_usage_cache_is_scoped_to_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(opencode, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(opencode, "USAGE_CACHE_PATH", tmp_path / "opencode-usage-cache.json")
    windows = opencode.parse_usage(USAGE, now_epoch=NOW)

    opencode.save_usage_cache(windows, "wrk_a")

    assert opencode.load_usage_cache("wrk_a") == windows
    assert opencode.load_usage_cache("wrk_b") is None


def _isolate_output(monkeypatch, tmp_path):
    monkeypatch.setattr(opencode, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(opencode, "OUTPUT_PATH", tmp_path / "opencode-usage.json")
    monkeypatch.setattr(opencode, "RENDER_PATH", tmp_path / "opencode-usage-render.tsv")
    monkeypatch.setattr(opencode, "USAGE_CACHE_PATH", tmp_path / "opencode-usage-cache.json")
    monkeypatch.setattr(opencode, "log_event", lambda _message: None)
    monkeypatch.setattr(opencode.common, "load_env", lambda: None)
    monkeypatch.setenv("OPENCODE_API_KEY", "secret-key")
    monkeypatch.setenv("OPENCODE_WORKSPACE_ID", "wrk_live")
    monkeypatch.setenv("OPENCODE_USAGE_LABEL", "go")


def test_main_uses_fresh_usage(monkeypatch, tmp_path):
    _isolate_output(monkeypatch, tmp_path)
    monkeypatch.setattr(opencode, "fetch_usage", lambda *_args, **_kwargs: opencode.parse_usage(USAGE, NOW))

    assert opencode.main() == 0
    output = json.loads((tmp_path / "opencode-usage.json").read_text(encoding="utf-8"))
    assert output["ok"] is True
    assert output["accounts"][0]["label"] == "go"
    assert output["accounts"][0]["staleCache"] is False
    assert "secret-key" not in (tmp_path / "opencode-usage.json").read_text(encoding="utf-8")


def test_main_uses_matching_stale_cache(monkeypatch, tmp_path):
    _isolate_output(monkeypatch, tmp_path)

    def fail_fetch(*_args, **_kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(opencode, "fetch_usage", fail_fetch)
    opencode.save_usage_cache(opencode.parse_usage(USAGE, now_epoch=NOW), "wrk_live")

    assert opencode.main() == 0
    output = json.loads((tmp_path / "opencode-usage.json").read_text(encoding="utf-8"))
    assert output["accounts"][0]["staleCache"] is True
    assert "offline" in output["accounts"][0]["error"]


def test_main_keeps_empty_bars_when_cache_missing(monkeypatch, tmp_path):
    _isolate_output(monkeypatch, tmp_path)

    def fail_fetch(*_args, **_kwargs):
        raise RuntimeError("This API key has expired")

    monkeypatch.setattr(opencode, "fetch_usage", fail_fetch)

    assert opencode.main() == 1
    output = json.loads((tmp_path / "opencode-usage.json").read_text(encoding="utf-8"))
    assert output["ok"] is False
    account = output["accounts"][0]
    assert account["label"] == "go"
    assert account["staleCache"] is True
    assert [window["label"] for window in account["windows"]] == ["5h", "weekly", "monthly"]
    assert all(window["usedPercent"] == 0.0 for window in account["windows"])
    render = (tmp_path / "opencode-usage-render.tsv").read_text(encoding="utf-8")
    assert "account\tgo" in render
    assert "bar\tgo\tgo\t1\t5h\t0.0" in render

import json
import sqlite3

import pytest

import fetch_opencode_usage as opencode


USAGE_HTML = """
<main>
  <div class="usage-item">
    <span data-slot="usage-label">Rolling Usage</span>
    <span data-slot="usage-value">73.5%</span>
    <span data-slot="reset-time">Resets in 2 hours 43 minutes</span>
  </div>
  <div class="usage-item">
    <span data-slot="usage-label">Weekly Usage</span>
    <span data-slot="usage-value">44%</span>
    <span data-slot="reset-time">Resets in 2 days 19 hours</span>
  </div>
  <div class="usage-item">
    <span data-slot="usage-label">Monthly Usage</span>
    <span data-slot="usage-value">10%</span>
    <span data-slot="reset-time">Resets in 30 days 21 hours</span>
  </div>
</main>
"""

LEGACY_USAGE_HTML = """
<main>
  <div class="usage-item">
    <span data-slot="usage-label">5-hour rolling</span>
    <span data-slot="usage-value">12%</span>
    <span data-slot="reset-time">Resets in 15 minutes</span>
  </div>
  <div class="usage-item">
    <span data-slot="usage-label">Weekly</span>
    <span data-slot="usage-value">20%</span>
    <span data-slot="reset-time">Resets in 1 day</span>
  </div>
  <div class="usage-item">
    <span data-slot="usage-label">Monthly</span>
    <span data-slot="usage-value">30%</span>
    <span data-slot="reset-time">Resets in 10 days</span>
  </div>
</main>
"""


def test_parse_reset_time_to_seconds():
    assert opencode.parse_reset_time_to_seconds("2 hours 43 minutes") == 9780
    assert opencode.parse_reset_time_to_seconds("2 days 19 hours") == 241200
    assert opencode.parse_reset_time_to_seconds("30 days 21 hours") == 2667600
    assert opencode.parse_reset_time_to_seconds("15 minutes") == 900
    assert opencode.parse_reset_time_to_seconds("") == 0


def test_parse_usage_html_returns_dashboard_windows():
    windows = opencode.parse_usage_html(USAGE_HTML, now_epoch=1_800_000_000)

    assert [window["label"] for window in windows] == ["5h", "weekly", "monthly"]
    assert windows[0]["usedPercent"] == 73.5
    assert windows[0]["remainingPercent"] == 26.5
    assert windows[0]["resetAfterSeconds"] == 9780
    assert windows[0]["resetAtEpoch"] == 1_800_009_780
    assert windows[1]["costUsd"] == 13.2
    assert windows[2]["costUsd"] == 6.0


def test_parse_usage_html_accepts_legacy_5_hour_label():
    windows = opencode.parse_usage_html(LEGACY_USAGE_HTML, now_epoch=1_800_000_000)
    assert [window["label"] for window in windows] == ["5h", "weekly", "monthly"]
    assert windows[0]["usedPercent"] == 12.0


def test_parse_usage_html_requires_all_windows():
    with pytest.raises(RuntimeError, match="monthly"):
        opencode.parse_usage_html(USAGE_HTML.replace("Monthly", "Daily"))


def test_cookie_header_accepts_cookie_header_and_token(monkeypatch):
    monkeypatch.setenv("OPENCODE_COOKIE", "session=abc; theme=dark")
    assert opencode.cookie_header() == "session=abc; theme=dark"

    monkeypatch.setenv("OPENCODE_COOKIE", "abc")
    assert opencode.cookie_header() == "auth=abc"


def test_cookie_header_falls_back_to_firefox(monkeypatch):
    monkeypatch.delenv("OPENCODE_COOKIE", raising=False)
    monkeypatch.delenv("OPENCODE_AUTH_COOKIE", raising=False)
    monkeypatch.setattr(
        opencode,
        "cookie_header_from_firefox",
        lambda: "auth=from-firefox; oc_locale=en",
    )

    assert opencode.cookie_header() == "auth=from-firefox; oc_locale=en"


def test_cookie_header_requires_firefox_or_env(monkeypatch):
    monkeypatch.delenv("OPENCODE_COOKIE", raising=False)
    monkeypatch.delenv("OPENCODE_AUTH_COOKIE", raising=False)

    def boom():
        raise RuntimeError("no auth cookie")

    monkeypatch.setattr(opencode, "cookie_header_from_firefox", boom)

    with pytest.raises(RuntimeError, match="Firefox"):
        opencode.cookie_header()


def test_resolve_firefox_profile_prefers_install_default(tmp_path):
    home = tmp_path / "firefox"
    release = home / "upn9cnj5.default-release"
    legacy = home / "q47aeqo0.default"
    release.mkdir(parents=True)
    legacy.mkdir(parents=True)
    (home / "profiles.ini").write_text(
        "\n".join(
            [
                "[InstallABCD]",
                "Default=upn9cnj5.default-release",
                "",
                "[Profile0]",
                "Name=default",
                "IsRelative=1",
                "Path=q47aeqo0.default",
                "Default=1",
                "",
                "[Profile1]",
                "Name=default-release",
                "IsRelative=1",
                "Path=upn9cnj5.default-release",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert opencode.resolve_firefox_profile_dir(home) == release


def test_read_firefox_opencode_cookies(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    db_path = profile / "cookies.sqlite"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE moz_cookies (
            name TEXT,
            value TEXT,
            host TEXT,
            expiry INTEGER
        )
        """
    )
    connection.executemany(
        "INSERT INTO moz_cookies (name, value, host, expiry) VALUES (?, ?, ?, ?)",
        [
            ("auth", "token-value", "opencode.ai", 2_000_000_000_000),
            ("oc_locale", "en", "opencode.ai", 2_000_000_000_000),
            ("expired", "nope", "opencode.ai", 1_000),
            ("other", "x", "example.com", 2_000_000_000_000),
        ],
    )
    connection.commit()
    connection.close()

    cookies = opencode.read_firefox_opencode_cookies(profile)
    assert cookies == {"auth": "token-value", "oc_locale": "en"}
    assert opencode.cookie_header_from_firefox(profile).startswith("auth=token-value")


def test_workspace_url_accepts_url_or_id(monkeypatch):
    monkeypatch.setenv("OPENCODE_WORKSPACE_URL", "https://example.test/workspace/go")
    assert opencode.workspace_url() == "https://example.test/workspace/go"

    monkeypatch.delenv("OPENCODE_WORKSPACE_URL")
    monkeypatch.setenv("OPENCODE_WORKSPACE_ID", "wrk_test")
    assert opencode.workspace_url() == "https://opencode.ai/workspace/wrk_test/go"


class FakeResponse:
    def __init__(self, body, url="https://opencode.ai/workspace/wrk_test/go"):
        self.body = body.encode("utf-8")
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.url

    def read(self):
        return self.body


def test_fetch_usage_from_web_sends_cookie(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["cookie"] = request.get_header("Cookie")
        captured["timeout"] = timeout
        return FakeResponse(USAGE_HTML)

    monkeypatch.setattr(opencode.urllib.request, "urlopen", fake_urlopen)
    windows = opencode.fetch_usage_from_web("https://example.test/go", "session=abc")

    assert captured == {
        "url": "https://example.test/go",
        "cookie": "session=abc",
        "timeout": 10,
    }
    assert len(windows) == 3


def test_web_cache_is_scoped_to_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(opencode, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(opencode, "WEB_CACHE_PATH", tmp_path / "opencode-web-cache.json")
    windows = opencode.parse_usage_html(USAGE_HTML, now_epoch=1_800_000_000)

    opencode.save_web_cache(windows, "https://example.test/workspace/a/go")

    assert opencode.load_web_cache("https://example.test/workspace/a/go") == windows
    assert opencode.load_web_cache("https://example.test/workspace/b/go") is None


def test_main_uses_fresh_web_data(monkeypatch, tmp_path):
    output_path = tmp_path / "opencode-usage.json"
    render_path = tmp_path / "opencode-usage-render.tsv"
    monkeypatch.setattr(opencode, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(opencode, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(opencode, "RENDER_PATH", render_path)
    monkeypatch.setattr(opencode, "WEB_CACHE_PATH", tmp_path / "web-cache.json")
    monkeypatch.setattr(opencode, "log_event", lambda _message: None)
    monkeypatch.setattr(opencode.common, "load_env", lambda: None)
    monkeypatch.setenv("OPENCODE_WORKSPACE_URL", "https://example.test/workspace/go")
    monkeypatch.setenv("OPENCODE_USAGE_LABEL", "dashboard")
    monkeypatch.setattr(
        opencode,
        "fetch_usage_from_web",
        lambda _url: opencode.parse_usage_html(USAGE_HTML, 1_800_000_000),
    )

    assert opencode.main() == 0
    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert output["ok"] is True
    assert output["accounts"][0]["label"] == "dashboard"
    assert output["accounts"][0]["staleCache"] is False


def test_main_uses_matching_stale_web_cache(monkeypatch, tmp_path):
    output_path = tmp_path / "opencode-usage.json"
    render_path = tmp_path / "opencode-usage-render.tsv"
    monkeypatch.setattr(opencode, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(opencode, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(opencode, "RENDER_PATH", render_path)
    monkeypatch.setattr(opencode, "WEB_CACHE_PATH", tmp_path / "web-cache.json")
    monkeypatch.setattr(opencode, "log_event", lambda _message: None)
    monkeypatch.setattr(opencode.common, "load_env", lambda: None)
    monkeypatch.setenv("OPENCODE_WORKSPACE_URL", "https://example.test/workspace/go")
    def fail_fetch(_url):
        raise RuntimeError("offline")

    monkeypatch.setattr(opencode, "fetch_usage_from_web", fail_fetch)
    windows = opencode.parse_usage_html(USAGE_HTML, now_epoch=1_800_000_000)
    opencode.save_web_cache(windows, "https://example.test/workspace/go")

    assert opencode.main() == 0
    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert output["accounts"][0]["staleCache"] is True
    assert "offline" in output["accounts"][0]["error"]


def test_main_keeps_empty_bars_when_cache_missing(monkeypatch, tmp_path):
    output_path = tmp_path / "opencode-usage.json"
    render_path = tmp_path / "opencode-usage-render.tsv"
    monkeypatch.setattr(opencode, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(opencode, "OUTPUT_PATH", output_path)
    monkeypatch.setattr(opencode, "RENDER_PATH", render_path)
    monkeypatch.setattr(opencode, "WEB_CACHE_PATH", tmp_path / "web-cache.json")
    monkeypatch.setattr(opencode, "log_event", lambda _message: None)
    monkeypatch.setattr(opencode.common, "load_env", lambda: None)
    monkeypatch.setenv("OPENCODE_WORKSPACE_URL", "https://example.test/workspace/go")
    monkeypatch.setenv("OPENCODE_USAGE_LABEL", "dashboard")

    def fail_fetch(_url):
        raise RuntimeError("OpenCode dashboard session expired (redirected to login)")

    monkeypatch.setattr(opencode, "fetch_usage_from_web", fail_fetch)

    assert opencode.main() == 1
    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert output["ok"] is False
    assert len(output["accounts"]) == 1
    account = output["accounts"][0]
    assert account["label"] == "dashboard"
    assert account["ok"] is False
    assert account["staleCache"] is True
    assert [window["label"] for window in account["windows"]] == ["5h", "weekly", "monthly"]
    assert all(window["usedPercent"] == 0.0 for window in account["windows"])
    assert [bar["window"] for bar in output["bars"]] == ["5h", "weekly", "monthly"]
    render = render_path.read_text(encoding="utf-8")
    assert "account\tdashboard" in render
    assert "bar\tdashboard\tgo\t1\t5h\t0.0" in render

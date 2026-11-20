import base64
import hashlib
import json
import subprocess
from datetime import datetime, timezone

import pytest

import fetch_codex_usage as codex
import fetch_common as common
import fetch_cursor_usage as cursor


@pytest.fixture(params=[codex, cursor], ids=["codex", "cursor"])
def fetcher(request, monkeypatch, tmp_path):
    module = request.param
    provider = module.__name__.split("_")[1]
    home = tmp_path / "home"
    home.mkdir()
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv(f"{provider.upper()}_HOME", str(home))
    monkeypatch.setenv(f"{provider.upper()}_AUTH_STORE_DIR", str(store))
    monkeypatch.delenv(f"{provider.upper()}_AUTH_PATH", raising=False)
    if module is codex:
        monkeypatch.setattr(codex, "CODEX_HOME", home)
        monkeypatch.setattr(codex, "CODEX_SQLITE_HOME", home)
        monkeypatch.setattr(codex, "CODEX_AUTH_STORE_DIR", store)
    monkeypatch.setattr(common, "load_env", lambda: None)
    monkeypatch.setattr(module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(module, "OUTPUT_PATH", tmp_path / f"{provider}-usage.json")
    monkeypatch.setattr(module, "RENDER_PATH", tmp_path / f"{provider}-usage-render.tsv")
    monkeypatch.setattr(module, "log_event", lambda _: None)
    return module, provider, store, home


def write_auth(module, path, subject):
    if module is codex:
        auth = {"tokens": {"account_id": subject, "access_token": "fixture-token"}}
    else:
        claims = base64.urlsafe_b64encode(json.dumps({"sub": subject}).encode()).decode()
        auth = {"accessToken": f"fixture.{claims}.fixture-token"}
    path.write_text(json.dumps(auth), encoding="utf-8")


def test_main_polls_each_saved_account_once_and_updates_the_panel(fetcher, monkeypatch):
    module, provider, store, home = fetcher
    write_auth(module, store / "auth.json.work", "work-account")
    write_auth(module, store / "auth.json.work-copy", "work-account")
    write_auth(module, store / "auth.json.other", "another-account")
    (store / "current").symlink_to("auth.json.work-copy")
    (store / "auth.json.lock").touch()
    (store / "auth.json.json.lock").touch()
    (store / "auth.json.folder").mkdir()
    (home / "auth.json").write_text("unused legacy default", encoding="utf-8")

    identity = hashlib.sha256(b"work-account").hexdigest()
    module.OUTPUT_PATH.write_text(json.dumps({"accounts": [
        {"accountId": identity, "label": "work", "cloudAvailable": True},
        {"accountId": "b" * 64, "label": "cloud-only", "cloudAvailable": True},
    ]}), encoding="utf-8")

    def unexpected_snapshot(*_args, **_kwargs):
        pytest.fail("local usage should never invoke the retired account CLI")

    monkeypatch.setattr(subprocess, "run", unexpected_snapshot)
    polled = []
    now = int(datetime.now(timezone.utc).timestamp())
    if module is codex:
        def usage(auth):
            polled.append(auth["path"].name)
            return 200, {
                "plan_type": "plus",
                "rate_limit": {"primary_window": {
                    "used_percent": 30, "limit_window_seconds": 18000, "reset_at": now + 3600,
                }},
                "rate_limit_reset_credits": {"available_count": 2},
            }
        monkeypatch.setattr(codex, "codex_request", usage)
        monkeypatch.setattr(codex, "retry_degenerate_usage", lambda _auth, _label, payload: payload)
    else:
        def usage(auth, method):
            if method == "GetCurrentPeriodUsage":
                polled.append(auth["path"].name)
                return 200, {
                    "billingCycleStart": now - 86400, "billingCycleEnd": now + 86400,
                    "planUsage": {"autoPercentUsed": 30},
                }
            if method == "GetMe":
                return 200, {"userId": auth["account_id"]}
            assert method == "GetPlanInfo"
            return 200, {"planInfo": {"planName": "Pro"}}
        monkeypatch.setattr(cursor, "cursor_request", usage)

    assert module.main() == 0
    assert sorted(polled) == ["auth.json.other", "auth.json.work-copy"]
    output = json.loads(module.OUTPUT_PATH.read_text())
    assert output["ok"]
    assert [account["label"] for account in output["accounts"]] == ["other", "work"]
    other, work = output["accounts"]
    assert not other["isSelected"]
    assert work["isSelected"] and work["selectedLocalProfile"] == "work-copy"
    assert work["accountId"] == identity
    assert work["aliases"] == ["work", "work-copy"]
    assert work["usageSource"] == "local" and work["freshness"] == "fresh"
    assert work["localAvailable"] and not work["cloudAvailable"]
    assert work["availabilityGeneratedAt"] >= now and work["observedAt"] >= now
    assert output["bars"][-1]["accountId"] == identity
    assert output["bars"][-1]["usedPercent"] == 30
    fields = module.RENDER_PATH.read_text().splitlines()[2].split("\t")
    assert fields[7:9] == ["1", identity]
    assert fields[12:] == ["fresh", "0", "2" if module is codex else ""]
    history = common.load_usage_history(module.CACHE_DIR / common.RATE_LIMIT_USAGE_HISTORY_NAME)
    assert any(sample["provider"] == provider and sample["account"] == identity for sample in history)
    assert "fixture-token" not in module.OUTPUT_PATH.read_text()


def test_failed_poll_keeps_matching_cached_windows(fetcher, monkeypatch):
    module, provider, store, _home = fetcher
    path = store / "auth.json.work"
    write_auth(module, path, "work-account")
    now = int(datetime.now(timezone.utc).timestamp())
    cached = {
        "provider": provider,
        "accountId": hashlib.sha256(b"work-account").hexdigest(),
        "label": "work",
        "observedAt": now - 100,
        "planType": "pro",
        "usageSource": "local",
        "windows": [{"label": "5h", "usedPercent": 32, "resetAtEpoch": now + 600}],
    }
    if module is codex:
        cached["rateLimitResetsAvailable"] = 1
    module.OUTPUT_PATH.write_text(json.dumps({"accounts": [cached]}), encoding="utf-8")
    request = "codex_request" if module is codex else "cursor_request"
    monkeypatch.setattr(module, request, lambda *_: (503, {}))

    assert module.main() == 1
    output = json.loads(module.OUTPUT_PATH.read_text())
    account, = output["accounts"]
    assert not account["ok"] and account["staleCache"] and account["freshness"] == "stale"
    assert account["localAvailable"] and not account["cloudAvailable"]
    assert account["windows"] == cached["windows"]
    assert account["observedAt"] == cached["observedAt"]
    assert account["planType"] == "pro"
    assert account.get("rateLimitResetsAvailable") == cached.get("rateLimitResetsAvailable")
    assert account["error"].endswith("HTTP 503")

    write_auth(module, path, "replacement-account")
    assert module.main() == 1
    account, = json.loads(module.OUTPUT_PATH.read_text())["accounts"]
    assert account["accountId"] != cached["accountId"]
    assert account["windows"] == []


def test_auth_discovery_falls_back_and_honors_explicit_path(fetcher, monkeypatch):
    module, provider, store, home = fetcher
    default_path = home / "auth.json"
    write_auth(module, default_path, "default-account")
    (store / "auth.json.json.lock").touch()
    assert module.discover_auth_files() == [("default", default_path, True)]

    legacy = home / "auth.json.legacy"
    write_auth(module, legacy, "legacy-account")
    var = f"{provider.upper()}_AUTH_STORE_DIR"
    missing_store = store / "missing"
    monkeypatch.setenv(var, str(missing_store))
    if module is codex:
        module.configure_from_env()
    assert module.discover_auth_files() == [("legacy", legacy, False)]

    monkeypatch.setenv(f"{provider.upper()}_AUTH_PATH", str(default_path))
    assert module.discover_auth_files() == [("default", default_path, True)]

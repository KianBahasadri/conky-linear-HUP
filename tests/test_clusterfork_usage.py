import copy
import json
import subprocess
from pathlib import Path

import pytest

import clusterfork_usage as managed
import fetch_codex_usage as codex
import fetch_common as common
import fetch_cursor_usage as cursor


NOW = 1_800_000_000
IDENTITY = "a" * 64
OTHER_ID = "b" * 64


def snapshot(provider, *, local=False, selected=False):
    return {
        "schema_version": 1, "generated_at": NOW, "provider": provider,
        "local_scope": "host", "cloud_error": None,
        "accounts": [{
            "provider": provider, "account_id": IDENTITY,
            "aliases": ["work", "work-local"], "cloud_available": True,
            "local_available": local, "local_profiles": ["work-local"] if local else [],
            "selected_local_profile": "work-local" if selected else None,
            "usage": {
                "observed_at": NOW - 60, "attempted_at": NOW - 10,
                "age_seconds": 60, "max_age_seconds": 300,
                "freshness": "fresh", "error": None,
                "windows": [
                    {"name": "codex/primary" if provider == "codex" else "cursor/api",
                     "used_percent": 23, "resets_at": NOW + 1000, "duration_minutes": 300},
                    {"name": "codex/secondary" if provider == "codex" else "cursor/included",
                     "used_percent": 67, "resets_at": NOW + 30000, "duration_minutes": 10080},
                ],
            },
        }],
    }


def forbidden(*args, **kwargs):
    pytest.fail("managed polling crossed the provider credential boundary")


@pytest.mark.parametrize("provider", ["codex", "cursor"])
@pytest.mark.parametrize("local,selected", [(False, False), (True, False), (True, True)])
def test_identity_join_and_serialization(monkeypatch, tmp_path, provider, local, selected):
    source = snapshot(provider, local=local, selected=selected)
    alias = copy.deepcopy(source["accounts"][0])
    alias["aliases"] = ["another-alias"]
    source["accounts"].append(alias)
    monkeypatch.setattr(managed, "read_snapshot", lambda *_: source)

    accounts, error = managed.fetch_accounts(provider, tmp_path, tmp_path / "cache.json", forbidden, now=NOW)

    assert error is None
    assert len(accounts) == 1
    account = accounts[0]
    assert account["accountId"] == IDENTITY
    assert account["aliases"] == ["another-alias", "work", "work-local"]
    assert account["localAvailable"] is local
    assert account["isSelected"] is selected
    assert account["observedAt"] == NOW - 60
    assert account["attemptedAt"] == NOW - 10
    assert account["maxAgeSeconds"] == 300
    assert account["planType"] == ""  # Unknown tier uses the renderer's baseline weight.
    assert account["freshness"] == "fresh"
    assert len(account["windows"]) == 2
    assert account["windows"][0]["resetAfterSeconds"] == 1060  # Measured, not poll time.
    assert [w["label"] for w in account["windows"]] == (["5h", "weekly"] if provider == "codex" else ["api", "included"])
    bars = common.flatten_bars(accounts)
    assert sum(b["usedPercent"] for b in bars) == 90  # One contribution per account/window.
    common.write_usage_outputs(tmp_path / "usage.json", tmp_path / f"{provider}-usage-render.tsv",
                               {"ok": True, "accounts": accounts, "bars": bars})
    cached = json.loads((tmp_path / "usage.json").read_text())
    assert cached["accounts"] == accounts
    tsv = (tmp_path / f"{provider}-usage-render.tsv").read_text().splitlines()
    assert len([line for line in tsv if line.startswith("account\t")]) == 1
    fields = tsv[1].split("\t")
    assert fields[7:9] == [str(int(local)), IDENTITY]
    assert list(map(float, fields[9:12])) == [NOW, NOW - 60, 300]
    assert fields[12] == "fresh"
    assert tsv[2].split("\t")[11:] == [IDENTITY, source["accounts"][0]["usage"]["windows"][0]["name"]]
    history = common.load_usage_history(tmp_path / common.RATE_LIMIT_USAGE_HISTORY_NAME)
    assert {sample["t"] for sample in history} == {NOW - 60}
    assert {sample["account"] for sample in history} == {IDENTITY}


@pytest.mark.parametrize("provider,module", [("codex", codex), ("cursor", cursor)])
@pytest.mark.parametrize("source_status", [200, 401, 403, "expired", "timeout", "invalid"])
def test_entrypoint_never_reads_or_refreshes_managed_credentials(
    monkeypatch, tmp_path, provider, module, source_status, capsys
):
    # Leave a reserved credential and even a selector behind. Neither makes the
    # profile local; the actual cloud-only source needs no credential file at all.
    auth = tmp_path / "auth.json.work"
    auth.write_text("reserved credential contents")
    (tmp_path / "auth.json").symlink_to(auth.name)
    before = auth.stat()
    monkeypatch.setenv(provider.upper() + "_AUTH_PATH", str(auth))
    monkeypatch.setenv(provider.upper() + "_AUTH_STORE_DIR", str(tmp_path))
    monkeypatch.setattr(common, "load_env", lambda: None)
    monkeypatch.setattr(module, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(module, "OUTPUT_PATH", tmp_path / "usage.json")
    monkeypatch.setattr(module, "RENDER_PATH", tmp_path / f"{provider}-usage-render.tsv")
    monkeypatch.setattr(module, "read_auth", forbidden)
    monkeypatch.setattr(module, "discover_auth_files", forbidden)
    monkeypatch.setattr(module, "fetch_account", forbidden)
    monkeypatch.setattr(module.urllib.request, "urlopen", forbidden)
    if provider == "codex":
        monkeypatch.setattr(module, "refresh_token", forbidden)
        monkeypatch.setattr(module, "read_local_rate_limit_samples", forbidden)
    read_text = Path.read_text

    def guarded_read(path, *args, **kwargs):
        if path.name.startswith("auth.json"):
            forbidden()
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    source = snapshot(provider)
    monkeypatch.setattr(managed.time, "time", lambda: NOW)
    # First persist a successful contract response. It will remain available
    # when a later operator-auth, network, or metadata response fails.
    responding_status = 200
    def command(args, **kwargs):
        assert args[2:] == ["snapshot", "--provider", provider, "--store", str(tmp_path)]
        assert kwargs["timeout"] == 45
        if responding_status == "timeout":
            raise subprocess.TimeoutExpired(args, 45)
        if responding_status in (401, 403):
            return subprocess.CompletedProcess(args, 1, "", "private error that must not escape")
        if responding_status == "invalid":
            return subprocess.CompletedProcess(args, 0, '{"schema_version": 2}', "")
        if responding_status == "expired":
            source["cloud_error"] = "operator_authentication_unavailable"
            source["accounts"][0]["usage"].update(freshness="unknown", windows=[], observed_at=None)
        return subprocess.CompletedProcess(args, 0, json.dumps(source), "")

    monkeypatch.setattr(managed.subprocess, "run", command)
    assert module.main() == 0
    responding_status = source_status
    assert module.main() == (0 if source_status == 200 else 1)
    output = json.loads(read_text(tmp_path / "usage.json"))
    assert "private error" not in capsys.readouterr().out
    assert auth.stat().st_mtime_ns == before.st_mtime_ns
    assert auth.stat().st_ino == before.st_ino
    assert read_text(auth) == "reserved credential contents"
    assert len(output["accounts"]) == 1
    account = output["accounts"][0]
    assert not account["localAvailable"] and not account["isSelected"]
    assert account["observedAt"] == NOW - 60
    assert len(output["bars"]) == 2
    if source_status != 200:
        assert not account["ok"] and account["staleCache"]
        assert account["freshness"] == "stale"


@pytest.mark.parametrize("provider", ["codex", "cursor"])
def test_failure_retains_cloud_only_quota_and_drops_cached_availability(monkeypatch, tmp_path, provider):
    source = snapshot(provider, local=True, selected=True)
    monkeypatch.setattr(managed, "read_snapshot", lambda *_: source)
    cache = tmp_path / "usage.json"
    previous, _ = managed.fetch_accounts(provider, tmp_path, cache, forbidden, now=NOW)
    cache.write_text(json.dumps({"accounts": previous}))
    monkeypatch.setattr(managed, "read_snapshot", lambda *_: (_ for _ in ()).throw(RuntimeError("HTTP 403")))

    accounts, error = managed.fetch_accounts(provider, tmp_path, cache, forbidden, now=NOW + 600)

    assert error
    assert len(accounts) == 1
    account = accounts[0]
    assert account["windows"] == previous[0]["windows"]
    assert account["observedAt"] == NOW - 60
    assert account["freshness"] == "stale"
    assert account["staleCache"] and not account["ok"]
    assert not account["localAvailable"] and not account["isSelected"]


@pytest.mark.parametrize("change", ["old", "future", "reset", "unknown", "null", "bad-percent"])
def test_usage_freshness_is_recomputed_and_unknown_never_becomes_unused(monkeypatch, tmp_path, change):
    source = snapshot("codex")
    usage = source["accounts"][0]["usage"]
    if change == "old":
        usage["observed_at"] = NOW - 301
    elif change == "future":
        usage["observed_at"] = NOW + 1
    elif change == "reset":
        usage["windows"][0]["resets_at"] = NOW
    elif change == "unknown":
        usage["freshness"] = "unknown"
    elif change == "null":
        usage["observed_at"] = None
    else:
        for window in usage["windows"]:
            window["used_percent"] = "NaN"
    monkeypatch.setattr(managed, "read_snapshot", lambda *_: source)

    accounts, _ = managed.fetch_accounts("codex", tmp_path, tmp_path / "cache", forbidden, now=NOW)
    assert not accounts[0]["ok"]
    assert accounts[0]["staleCache"]
    assert accounts[0]["freshness"] == ("stale" if change in ("old", "future", "reset") else "unknown")
    if change in ("unknown", "null", "bad-percent"):
        assert accounts[0]["windows"] == []


@pytest.mark.parametrize("availability", [None, False, "true", True])
def test_stale_or_unknown_local_metadata_is_not_availability(monkeypatch, tmp_path, availability):
    source = snapshot("cursor", local=True, selected=True)
    source["accounts"][0]["local_available"] = availability
    if availability is True:
        source["generated_at"] = NOW - 301
    monkeypatch.setattr(managed, "read_snapshot", lambda *_: source)
    accounts, _ = managed.fetch_accounts("cursor", tmp_path, tmp_path / "cache", forbidden, now=NOW)
    assert not accounts[0]["localAvailable"]
    assert not accounts[0]["isSelected"]
    assert accounts[0]["ok"]  # Quota validity is independent of local metadata.


def test_only_explicit_unenrolled_local_account_can_use_provider_path(monkeypatch, tmp_path):
    source = snapshot("cursor", local=True, selected=True)
    source["accounts"][0]["cloud_available"] = False
    source["accounts"].append(copy.deepcopy(source["accounts"][0]))
    monkeypatch.setattr(managed, "read_snapshot", lambda *_: source)
    calls = []

    def fetch_local(label, path, selected):
        calls.append((path, selected))
        return {"ok": True, "planType": "Pro", "windows": [{"label": "auto", "usedPercent": 12}]}

    accounts, _ = managed.fetch_accounts("cursor", tmp_path, tmp_path / "cache", fetch_local, now=NOW)
    assert calls == [(tmp_path / "auth.json.work-local", True)]
    assert len(accounts) == 1
    assert accounts[0]["windows"][0]["usedPercent"] == 12
    source["cloud_error"] = "operator_authentication_unavailable"
    accounts, _ = managed.fetch_accounts("cursor", tmp_path, tmp_path / "cache", forbidden, now=NOW)
    assert not accounts[0]["ok"]
    source["cloud_error"] = None
    # Missing ownership is not permission to read credentials.
    for row in source["accounts"]:
        row.pop("cloud_available")
    accounts, _ = managed.fetch_accounts("cursor", tmp_path, tmp_path / "cache", forbidden, now=NOW)
    assert not accounts[0]["ok"]


def test_failed_collection_keeps_capture_time_and_new_attempt_error(monkeypatch, tmp_path):
    source = snapshot("codex")
    monkeypatch.setattr(managed, "read_snapshot", lambda *_: source)
    cache = tmp_path / "usage.json"
    previous, _ = managed.fetch_accounts("codex", tmp_path, cache, forbidden, now=NOW)
    cache.write_text(json.dumps({"accounts": previous}))
    source["accounts"][0]["usage"].update(
        windows=[], observed_at=None, attempted_at=NOW + 30, freshness="unknown", error="lease_lost"
    )
    accounts, _ = managed.fetch_accounts("codex", tmp_path, cache, forbidden, now=NOW + 40)
    assert accounts[0]["observedAt"] == NOW - 60
    assert accounts[0]["attemptedAt"] == NOW + 30
    assert accounts[0]["sourceError"] == "lease_lost"
    assert accounts[0]["sourceFreshness"] == "unknown"
    assert accounts[0]["error"] == "lease_lost"


def test_cloud_only_without_any_auth_copy_remains_visible(monkeypatch, tmp_path):
    monkeypatch.setattr(managed, "read_snapshot", lambda *_: snapshot("cursor"))
    assert not list(tmp_path.glob("auth.json*"))
    accounts, _ = managed.fetch_accounts("cursor", tmp_path, tmp_path / "cache", forbidden, now=NOW)
    assert len(accounts) == 1 and accounts[0]["ok"]
    assert not accounts[0]["localAvailable"]


def test_snapshot_generation_is_evaluated_after_the_command(monkeypatch, tmp_path):
    # Host metadata is generated during the command, after the fetch starts.
    monkeypatch.setattr(managed, "read_snapshot", lambda *_: snapshot("codex", local=True))
    monkeypatch.setattr(managed.time, "time", lambda: NOW + 1)
    accounts, _ = managed.fetch_accounts("codex", tmp_path, tmp_path / "cache", forbidden)
    assert accounts[0]["localAvailable"]


@pytest.mark.parametrize("quota_error", ["busy", "inspection_failed", "lease_lost"])
def test_failed_attempt_can_coexist_with_fresh_quota(monkeypatch, tmp_path, quota_error):
    source = snapshot("cursor")
    source["accounts"][0]["usage"]["error"] = quota_error
    monkeypatch.setattr(managed, "read_snapshot", lambda *_: source)
    accounts, _ = managed.fetch_accounts("cursor", tmp_path, tmp_path / "cache", forbidden, now=NOW)
    assert accounts[0]["ok"] and accounts[0]["freshness"] == "fresh"
    assert accounts[0]["sourceError"] == quota_error


def test_null_durations_and_resets_do_not_invent_quota_metadata(monkeypatch, tmp_path):
    source = snapshot("cursor")
    source["accounts"][0]["usage"]["windows"][0].update(duration_minutes=None, resets_at=None)
    monkeypatch.setattr(managed, "read_snapshot", lambda *_: source)
    accounts, _ = managed.fetch_accounts("cursor", tmp_path, tmp_path / "cache", forbidden, now=NOW)
    window = accounts[0]["windows"][0]
    assert window["usedPercent"] == 23
    assert window["windowSeconds"] == 0 and window["resetAtEpoch"] == 0
    assert window["resetsAt"] is None

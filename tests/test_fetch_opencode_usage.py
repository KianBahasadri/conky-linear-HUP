import json
import sqlite3

import fetch_opencode_usage as opencode


def write_auth(path, key="sk-test-key"):
    path.write_text(json.dumps({"opencode-go": {"type": "api", "key": key}}), encoding="utf-8")


def write_auth_no_go(path):
    path.write_text(json.dumps({"github-copilot": {"type": "oauth", "refresh": "r", "access": "a", "expires": 0}}), encoding="utf-8")


def create_test_db(path, sessions):
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE session (id TEXT PRIMARY KEY, model TEXT, cost REAL DEFAULT 0, tokens_input INTEGER DEFAULT 0, tokens_output INTEGER DEFAULT 0, time_created INTEGER DEFAULT 0)"
    )
    for session in sessions:
        conn.execute(
            "INSERT INTO session (id, model, cost, tokens_input, tokens_output, time_created) VALUES (?, ?, ?, ?, ?, ?)",
            session,
        )
    conn.commit()
    conn.close()


def test_discover_auth_files_only_includes_go_subscribers(monkeypatch, tmp_path):
    go_profile = tmp_path / "auth.json.alice"
    no_go_profile = tmp_path / "auth.json.bob"
    write_auth(go_profile)
    write_auth_no_go(no_go_profile)
    (tmp_path / "auth.json").symlink_to(go_profile)
    monkeypatch.setenv("OPENCODE_HOME", str(tmp_path))

    discovered = opencode.discover_auth_files()

    assert [(label, selected) for label, _, selected in discovered] == [("alice", True)]


def test_discover_auth_files_marks_selected_by_symlink(monkeypatch, tmp_path):
    profile_a = tmp_path / "auth.json.alice"
    profile_b = tmp_path / "auth.json.bob"
    write_auth(profile_a)
    write_auth(profile_b)
    (tmp_path / "auth.json").symlink_to(profile_b)
    monkeypatch.setenv("OPENCODE_HOME", str(tmp_path))

    discovered = opencode.discover_auth_files()

    assert [(label, selected) for label, _, selected in discovered] == [("alice", False), ("bob", True)]


def test_compute_usage_windows(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    now_ms = 1800000000000  # arbitrary fixed timestamp in ms
    five_h_ms = 5 * 3600 * 1000
    week_ms = 7 * 24 * 3600 * 1000

    sessions = [
        # Recent session within all windows
        ("s1", '{"id":"kimi-k3","providerID":"opencode-go"}', 2.0, 1000, 500, now_ms - 3600000),
        # Session from 6 hours ago (outside 5h, inside weekly/monthly)
        ("s2", '{"id":"qwen3.7-max","providerID":"opencode-go"}', 3.0, 2000, 800, now_ms - 6 * 3600000),
        # Session from 10 days ago (outside 5h and weekly, inside monthly)
        ("s3", '{"id":"kimi-k3","providerID":"opencode-go"}', 5.0, 3000, 1200, now_ms - 10 * 24 * 3600000),
        # Non-opencode-go session (should be excluded)
        ("s4", '{"id":"gpt-5.5","providerID":"openai"}', 99.0, 9999, 9999, now_ms - 3600000),
    ]
    create_test_db(db_path, sessions)

    windows = opencode.compute_usage_windows(str(db_path), now_ms)

    assert windows["5h"]["cost"] == 2.0
    assert windows["weekly"]["cost"] == 5.0
    assert windows["monthly"]["cost"] == 10.0
    assert windows["5h"]["oldest_session_ms"] == now_ms - 3600000
    assert windows["weekly"]["oldest_session_ms"] == now_ms - 6 * 3600000
    assert windows["monthly"]["oldest_session_ms"] == now_ms - 10 * 24 * 3600000


def test_normalize_window_computes_percentage():
    window = opencode.normalize_window("5h", 6.0, 12.0, 18000, 0)

    assert window["usedPercent"] == 50.0
    assert window["remainingPercent"] == 50.0
    assert window["costUsd"] == 6.0
    assert window["limitUsd"] == 12.0
    assert window["resetAtEpoch"] == 0


def test_normalize_window_caps_at_100_percent():
    window = opencode.normalize_window("weekly", 35.0, 30.0, 604800, 0)

    assert window["usedPercent"] == 100.0
    assert window["remainingPercent"] == 0.0


def test_normalize_window_computes_reset_in_seconds_from_oldest_session():
    oldest_session_ms = 1800000000000
    window = opencode.normalize_window("5h", 6.0, 12.0, 18000, oldest_session_ms)

    expected_reset_epoch = int(oldest_session_ms / 1000) + 18000
    from datetime import datetime, timezone
    now_epoch = int(datetime.now(timezone.utc).timestamp())

    assert window["resetAtEpoch"] == expected_reset_epoch
    assert window["resetAfterSeconds"] == max(0, expected_reset_epoch - now_epoch)
    assert window["resetsAt"] is not None
    assert window["windowSeconds"] == 18000


def test_normalize_usage_produces_three_windows():
    auth = {"label": "alice", "path": None, "api_key": "sk-test"}
    windows = {
        "5h": {"cost": 2.0, "oldest_session_ms": 1800000000000},
        "weekly": {"cost": 10.0, "oldest_session_ms": 1800000000000},
        "monthly": {"cost": 30.0, "oldest_session_ms": 1800000000000},
    }

    account = opencode.normalize_usage(auth, windows, True)

    assert account["ok"] is True
    assert account["planType"] == "go"
    assert account["isSelected"] is True
    assert len(account["windows"]) == 3
    assert account["windows"][0]["label"] == "5h"
    assert account["windows"][1]["label"] == "weekly"
    assert account["windows"][2]["label"] == "monthly"
    assert account["windows"][0]["usedPercent"] == 16.7
    assert account["windows"][1]["usedPercent"] == 33.3
    assert account["windows"][2]["usedPercent"] == 50.0


def test_fetch_account_with_missing_db(monkeypatch, tmp_path):
    auth_path = tmp_path / "auth.json.alice"
    write_auth(auth_path)
    monkeypatch.setenv("OPENCODE_HOME", str(tmp_path))
    monkeypatch.setenv("OPENCODE_DB", str(tmp_path / "nonexistent.db"))

    account = opencode.fetch_account("alice", auth_path, True)

    assert account["ok"] is False
    assert "not found" in account["error"]


def test_read_auth_rejects_missing_go_key(tmp_path):
    auth_path = tmp_path / "auth.json.bob"
    write_auth_no_go(auth_path)

    try:
        opencode.read_auth("bob", auth_path)
        assert False, "should have raised"
    except RuntimeError as e:
        assert "no opencode-go API key" in str(e)

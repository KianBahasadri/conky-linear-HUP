import os
from pathlib import Path

import fetch_sessions as sessions


WHO_OUTPUT = """\
kian     tty2         2026-08-20 14:17 (local)
kian     pts/6        2026-08-22 09:04 (100.94.58.124)
kian     pts/2        2026-08-22 17:23 (tmux(2082727).%0)
kian     pts/9        2026-08-22 17:30 (10.0.0.99)
"""


def test_logins_drops_tmux_pseudo_terminals(monkeypatch):
    # tmux registers each of its own panes with utmp. Counting them as logins
    # turns every device into an unidentified remote the moment tmux starts.
    monkeypatch.setattr(sessions, "run", lambda *args, **kwargs: WHO_OUTPUT)

    ttys = [login["tty"] for login in sessions.logins()]
    assert ttys == ["tty2", "pts/6", "pts/9"]


def test_device_for_resolves_a_tailnet_peer():
    peers = {"100.94.58.124": ("Pixel 8a", "android")}
    login = {"tty": "pts/6", "origin": "100.94.58.124", "since": None}

    assert sessions.device_for(login, peers, "kianWorkLaptop") == (
        "Pixel 8a", "android", "phone", False,
    )


def test_device_for_flags_a_remote_with_no_tailnet_identity():
    login = {"tty": "pts/9", "origin": "10.0.0.99", "since": None}

    name, os_name, glyph, unknown = sessions.device_for(login, {}, "kianWorkLaptop")
    assert (name, os_name, glyph) == ("10.0.0.99", "UNKNOWN", "alert")
    assert unknown is True


def test_device_for_treats_the_console_as_local():
    login = {"tty": "tty2", "origin": "local", "since": None}

    assert sessions.device_for(login, {}, "kianWorkLaptop") == (
        "tty2", "local", "terminal", False,
    )


def test_overlay_height_has_no_empty_sockets_and_expands_for_more_data():
    assert sessions.overlay_height(0, 0) == sessions.PANEL_MIN_HEIGHT
    assert sessions.overlay_height(3, 3) == sessions.PANEL_MIN_HEIGHT
    # No empty placeholder sockets: 1 or 2 sessions use exactly that many diamonds,
    # not a padded row of three. Height stays at one row until >3 sessions.
    assert sessions.overlay_height(0, 1) == sessions.PANEL_MIN_HEIGHT
    assert sessions.overlay_height(0, 2) == sessions.PANEL_MIN_HEIGHT
    assert sessions.overlay_height(0, 1) == sessions.overlay_height(0, 3)
    # Drift field is fixed height — extra ingress devices sink, they do not stretch the window.
    assert sessions.overlay_height(100, 3) == sessions.overlay_height(3, 3)
    # Constellation reserves a fixed diamond zone so the bay holds the same
    # footprint for a few sessions; only when rows exceed that zone does it
    # grow. 3 sessions (1 row) and 7 (3 rows) now share the same height;
    # growth is visible only once the zone is exceeded.
    assert sessions.overlay_height(3, 7) == sessions.overlay_height(3, 3)
    assert sessions.overlay_height(3, 10) > sessions.overlay_height(3, 3)


def test_relative_age_units():
    assert sessions.relative_age(8) == "8s"
    assert sessions.relative_age(12 * 60) == "12m"
    assert sessions.relative_age(3 * 3600) == "3h"
    assert sessions.relative_age(2 * 86400) == "2d"
    assert sessions.relative_age(None) == ""


def test_sshd_listening_reads_the_listener_table(monkeypatch):
    monkeypatch.setattr(
        sessions, "run",
        lambda *args, **kwargs: "LISTEN 0 128 0.0.0.0:22 0.0.0.0:*\n",
    )
    assert sessions.sshd_listening() is True

    monkeypatch.setattr(
        sessions, "run",
        lambda *args, **kwargs: "LISTEN 0 128 127.0.0.1:631 0.0.0.0:*\n",
    )
    assert sessions.sshd_listening() is False


def test_tailnet_peers_maps_every_address_and_ignores_account_identity(monkeypatch):
    payload = """
    {
      "Self": {"HostName": "kianWorkLaptop", "OS": "linux",
               "TailscaleIPs": ["100.123.102.71"], "UserID": 1},
      "User": {"1": {"LoginName": "someone@example.com"}},
      "Peer": {
        "k1": {"HostName": "Pixel 8a", "OS": "android",
               "TailscaleIPs": ["100.94.58.124", "fd7a:115c::1"]}
      }
    }
    """
    monkeypatch.setattr(sessions, "run", lambda *args, **kwargs: payload)

    peers, host = sessions.tailnet_peers()
    assert host == "kianWorkLaptop"
    assert peers["100.94.58.124"] == ("Pixel 8a", "android")
    assert peers["fd7a:115c::1"] == ("Pixel 8a", "android")
    assert peers["100.123.102.71"] == ("kianWorkLaptop", "linux")
    # Only names and OS strings are taken; nothing carries the account identity.
    assert all("@" not in value for pair in peers.values() for value in pair)


def make_codeview_repo(tmp_path, daemon='{"pid": 4242, "port": 48290}'):
    repo = Path(tmp_path)
    (repo / ".codeview" / "cache").mkdir(parents=True)
    (repo / ".codeview" / "daemon.json").write_text(daemon, encoding="utf-8")
    index_file = repo / ".codeview" / "cache" / "summary.json"
    index_file.write_text("{}", encoding="utf-8")
    os.utime(index_file, (997_000, 997_000))
    return repo


def test_codeview_state_reports_a_live_daemon(tmp_path, monkeypatch):
    repo = make_codeview_repo(tmp_path)
    monkeypatch.setattr(
        sessions, "proc_cmdline",
        lambda pid: "python3 /home/kian/.config/clusterfork/scripts/codeview/server.py --port 48290",
    )
    monkeypatch.setattr(sessions.os, "kill", lambda pid, sig: None)

    # A pane parked in a subdirectory still finds the repo root by walking up.
    state = sessions.codeview_state(str(repo / "scripts" / "deep"), now=1_000_000)
    assert state == {
        "present": True,
        "running": True,
        "port": 48290,
        "indexAgeSeconds": 3_000,
    }


def test_codeview_state_flags_a_dead_daemon_as_an_eclipse(tmp_path, monkeypatch):
    repo = make_codeview_repo(tmp_path)

    def dead(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(sessions.os, "kill", dead)
    state = sessions.codeview_state(str(repo), now=1_000_000)
    assert state == {
        "present": True,
        "running": False,
        "port": 48290,
        "indexAgeSeconds": 3_000,
    }


def test_codeview_state_rejects_a_recycled_pid(tmp_path, monkeypatch):
    repo = make_codeview_repo(tmp_path)
    monkeypatch.setattr(sessions.os, "kill", lambda pid, sig: None)
    monkeypatch.setattr(sessions, "proc_cmdline", lambda pid: "kitty pts")

    state = sessions.codeview_state(str(repo), now=1_000_000)
    assert state["present"] is True
    assert state["running"] is False


def test_codeview_state_absent_without_a_dashboard(tmp_path):
    assert sessions.codeview_state(str(tmp_path), now=1_000_000) is None


def test_tmux_sessions_attaches_codeview_fields(tmp_path, monkeypatch):
    repo = make_codeview_repo(tmp_path)
    listing = f"build\t1\t{repo}\t1234567890"

    def fake_tmux(*args):
        return listing if args[0] == "list-sessions" else ""

    monkeypatch.setattr(sessions, "tmux", fake_tmux)
    monkeypatch.setattr(
        sessions, "proc_cmdline",
        lambda pid: "python3 server.py --port 48290",
    )
    monkeypatch.setattr(sessions.os, "kill", lambda pid, sig: None)

    record = sessions.tmux_sessions()["build"]
    assert record["codeviewPresent"] is True
    assert record["codeviewRunning"] is True
    assert record["codeviewPort"] == 48290
    assert record["codeviewIndexAgeSeconds"] >= 0


def test_tmux_sessions_marks_repos_without_codeview_absent(tmp_path, monkeypatch):
    plain = tmp_path / "plain-repo"
    plain.mkdir()
    listing = f"notes\t2\t{plain}\t1234567890"

    def fake_tmux(*args):
        return listing if args[0] == "list-sessions" else ""

    monkeypatch.setattr(sessions, "tmux", fake_tmux)

    record = sessions.tmux_sessions()["notes"]
    assert record["codeviewPresent"] is False
    assert record["codeviewRunning"] is False
    assert record["codeviewPort"] == 0
    assert record["codeviewIndexAgeSeconds"] == -1


def test_fleet_repo_paths_uses_git_discovery_cache(monkeypatch, tmp_path):
    # The git panel already scans $HOME for repos; reuse its cache so a repo
    # with a codeview daemon is found even without a tmux session.
    cache = tmp_path / "git-repo-discovery.json"
    cache.write_text(
        '{"updatedAtEpoch": 1000000, "paths": ["/tmp/alpha", "/tmp/beta"]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(sessions, "GIT_DISCOVERY_PATH", cache)
    monkeypatch.setattr(sessions.time, "time", lambda: 1000000 + 60)

    paths = sessions.fleet_repo_paths()
    assert paths == [Path("/tmp/alpha"), Path("/tmp/beta")]


def test_fleet_repo_paths_uses_pinned_env_first(monkeypatch, tmp_path):
    cache = tmp_path / "git-repo-discovery.json"
    cache.write_text(
        '{"updatedAtEpoch": 1000000, "paths": ["/tmp/alpha"]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(sessions, "GIT_DISCOVERY_PATH", cache)
    monkeypatch.setattr(sessions.time, "time", lambda: 1000000 + 60)
    monkeypatch.setenv("SESSIONS_CODEVIEW_REPO_PATHS", "/tmp/pinned:/tmp/alpha")

    paths = sessions.fleet_repo_paths()
    # Pinned first, cache appended without duplicates.
    assert paths == [Path("/tmp/pinned"), Path("/tmp/alpha")]


def test_fleet_codeview_repos_lists_only_daemon_repos(tmp_path, monkeypatch):
    # Repos without a .codeview/daemon.json are skipped.
    with_daemon = make_codeview_repo(tmp_path / "with-daemon")
    (tmp_path / "plain-repo").mkdir()

    monkeypatch.setattr(
        sessions, "fleet_repo_paths",
        lambda: [with_daemon, tmp_path / "plain-repo"],
    )
    monkeypatch.setattr(
        sessions, "proc_cmdline",
        lambda pid: "python3 /home/kian/.config/clusterfork/scripts/codeview/server.py --port 48290",
    )
    monkeypatch.setattr(sessions.os, "kill", lambda pid, sig: None)

    repos = sessions.fleet_codeview_repos(now=1_000_000)
    assert [r["name"] for r in repos] == ["with-daemon"]
    assert repos[0]["codeviewRunning"] is True
    assert repos[0]["codeviewIndexAgeSeconds"] == 3_000


def test_fleet_codeview_repos_keeps_dead_daemons_as_eclipses(tmp_path, monkeypatch):
    repo = make_codeview_repo(tmp_path / "dead-daemon")
    monkeypatch.setattr(sessions, "fleet_repo_paths", lambda: [repo])

    def dead(pid, sig):
        raise ProcessLookupError

    monkeypatch.setattr(sessions.os, "kill", dead)

    repos = sessions.fleet_codeview_repos(now=1_000_000)
    assert repos[0]["name"] == "dead-daemon"
    assert repos[0]["codeviewRunning"] is False

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


def test_overlay_height_keeps_three_slots_and_expands_for_more_data():
    assert sessions.overlay_height(0, 0) == sessions.PANEL_MIN_HEIGHT
    assert sessions.overlay_height(3, 3) == sessions.PANEL_MIN_HEIGHT
    # Drift field is fixed height — extra ingress devices sink, they do not stretch the window.
    assert sessions.overlay_height(100, 3) == sessions.overlay_height(3, 3)
    # Extra tmux sessions beyond one row eventually push the bottom down.
    assert sessions.overlay_height(3, 7) > sessions.overlay_height(3, 3)


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

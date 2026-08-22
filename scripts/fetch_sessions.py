#!/usr/bin/env python3
"""Active tmux sessions and the logins driving them.

Remote access on this machine is Tailscale SSH, not `sshd`: there is no TCP
listener on port 22, so anything that greps for `sshd` children or watches that
port reports zero remote sessions while one is live. The join that actually
works is `who` (tty -> origin) x `tmux list-clients` (tty -> session), with
`tailscale status` turning a tailnet address into a device name.

Only device names and OS strings are taken from Tailscale. The tailnet account
identity in that payload is deliberately left alone.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
SESSIONS_PATH = CACHE_DIR / "sessions.json"
LOG_PATH = CACHE_DIR / "conky-sessions.log"

# Must match the layout math in conky/sessions-renderer.lua.
PANEL_ROW_HEIGHT = 52
PANEL_CHROME_HEIGHT = 78

# Tailscale OS strings -> the glyph the renderer draws.
OS_GLYPHS = {
    "android": "phone",
    "ios": "phone",
    "iOS": "phone",
    "macOS": "laptop",
    "linux": "laptop",
    "windows": "monitor",
}

log_event = common.make_logger(LOG_PATH, "fetch_sessions")
atomic_write_json = common.atomic_write_json


def run(args, timeout=5):
    try:
        result = subprocess.run(
            args, check=False, capture_output=True, text=True, timeout=timeout
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def tmux(*args):
    return run(["tmux", *args])


def relative_age(seconds):
    if seconds is None or seconds < 0:
        return ""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def shorten_path(path):
    home = str(Path.home())
    if path == home:
        return "~"
    if path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path


def tmux_sessions():
    """name -> session record. Empty when no tmux server is running."""
    listing = tmux(
        "list-sessions", "-F",
        "#{session_name}\t#{session_windows}\t#{session_path}\t#{session_activity}",
    )
    if not listing:
        return {}

    now = datetime.now(timezone.utc).timestamp()
    sessions = {}
    for line in listing.splitlines():
        fields = line.split("\t")
        if len(fields) < 4:
            continue
        name, windows, path, activity = fields[:4]
        sessions[name] = {
            "name": name,
            "windows": int(windows) if windows.isdigit() else 1,
            "panes": 0,
            "path": shorten_path(path),
            "attached": [],
            "idle": relative_age(now - float(activity)) if activity.isdigit() else "",
        }

    panes = tmux("list-panes", "-a", "-F", "#{session_name}")
    if panes:
        for line in panes.splitlines():
            if line in sessions:
                sessions[line]["panes"] += 1

    return sessions


def tmux_clients():
    """tty (without /dev/) -> session name."""
    listing = tmux("list-clients", "-F", "#{client_tty}\t#{session_name}")
    if not listing:
        return {}

    clients = {}
    for line in listing.splitlines():
        tty, _, session = line.partition("\t")
        if tty and session:
            clients[tty.replace("/dev/", "")] = session
    return clients


def logins():
    """One record per `who` line: tty, user, and where it came from."""
    listing = run(["who"])
    if not listing:
        return []

    entries = []
    for line in listing.splitlines():
        match = re.match(
            r"^(\S+)\s+(\S+)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})(?:\s+\((.*)\))?", line
        )
        if not match:
            continue
        user, tty, when, origin = match.groups()
        origin = (origin or "").strip()
        # tmux registers each of its own panes with utmp as `tmux(PID).%N`.
        # Those are not inbound logins; the session cards already stand for
        # them, and treating them as unidentified remotes lights the whole
        # panel red the moment a tmux server starts.
        if origin.startswith("tmux("):
            continue
        try:
            since = datetime.strptime(when, "%Y-%m-%d %H:%M").timestamp()
        except ValueError:
            since = None
        entries.append({
            "user": user,
            "tty": tty,
            "origin": origin,
            "since": since,
        })
    return entries


def tailnet_peers():
    """tailnet address -> (device name, OS). One call covers every peer."""
    payload = run(["tailscale", "status", "--json"], timeout=8)
    if not payload:
        return {}, None

    try:
        status = json.loads(payload)
    except ValueError:
        return {}, None

    peers = {}
    for node in list((status.get("Peer") or {}).values()) + [status.get("Self") or {}]:
        name = node.get("HostName")
        if not name:
            continue
        for address in node.get("TailscaleIPs") or []:
            peers[address] = (name, node.get("OS") or "")

    self_node = status.get("Self") or {}
    return peers, self_node.get("HostName")


def sshd_listening(port=22):
    listing = run(["ss", "-ltn"])
    if listing is None:
        return None
    return bool(re.search(rf"LISTEN.*[:.]{port}\b", listing))


def device_for(login, peers, local_host):
    """Resolve a login's origin into something worth putting on a panel."""
    origin = login["origin"]
    local = (
        origin in ("", "local", local_host or "")
        or origin.startswith(":")
    )

    if local:
        return login["tty"], "local", "terminal", False

    if origin in peers:
        name, os_name = peers[origin]
        return name, os_name or "tailnet", OS_GLYPHS.get(os_name, "monitor"), False

    # A remote login with no tailnet identity is the state worth making loud.
    return origin, "UNKNOWN", "alert", True


def collect():
    sessions = tmux_sessions()
    clients = tmux_clients()
    peers, local_host = tailnet_peers()
    now = datetime.now(timezone.utc).timestamp()

    devices = []
    for login in logins():
        name, os_name, glyph, unknown = device_for(login, peers, local_host)
        session = clients.get(login["tty"])
        age = relative_age(now - login["since"]) if login["since"] else ""

        if unknown:
            state = "alert"
        elif session:
            state = "live"
        else:
            state = "idle"

        if session and session in sessions:
            sessions[session]["attached"].append(name)

        devices.append({
            "name": name,
            "os": os_name,
            "glyph": glyph,
            "tty": login["tty"],
            "session": session,
            "age": age,
            "state": state,
        })

    # Alerts first, then live links, then idle: the panel reads top-down.
    order = {"alert": 0, "live": 1, "idle": 2}
    devices.sort(key=lambda device: (order.get(device["state"], 3), device["name"]))

    session_list = sorted(
        sessions.values(),
        key=lambda item: (not item["attached"], item["name"]),
    )
    for session in session_list:
        session["attached"] = ", ".join(session["attached"])

    return devices, session_list


def overlay_height(device_count, session_count):
    """Conky minimum_height for the panel.

    Must match the layout math in conky/sessions-renderer.lua.
    """
    rows = max(1, device_count, session_count)
    return PANEL_CHROME_HEIGHT + rows * PANEL_ROW_HEIGHT


def current_overlay_height():
    """Height for the state right now, falling back to the last written cache."""
    try:
        devices, sessions = collect()
        return overlay_height(len(devices), len(sessions))
    except (OSError, ValueError):
        pass
    try:
        payload = json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return overlay_height(0, 0)
    return overlay_height(
        len(payload.get("devices") or []), len(payload.get("sessions") or [])
    )


def main():
    common.load_env()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if "--print-overlay-height" in sys.argv:
        print(current_overlay_height())
        return 0

    try:
        devices, sessions = collect()
        listening = sshd_listening()
        payload = {
            "ok": True,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "sshdListening": listening,
            "devices": devices,
            "sessions": sessions,
        }
        atomic_write_json(SESSIONS_PATH, payload)
        log_event(
            f"updated devices={len(devices)} sessions={len(sessions)} "
            f"sshd_listening={listening} height={overlay_height(len(devices), len(sessions))}"
        )
        return 0
    except OSError as error:
        payload = {
            "ok": False,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "error": str(error),
        }
        atomic_write_json(SESSIONS_PATH, payload)
        log_event(f"error: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

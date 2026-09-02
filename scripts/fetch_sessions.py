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
import time
from datetime import datetime, timezone
from math import ceil
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
SESSIONS_PATH = CACHE_DIR / "sessions.json"
LOG_PATH = CACHE_DIR / "conky-sessions.log"

# codeview dashboard daemon marker (see clusterfork's bin/codeview). A session
# whose repo has <repo>/.codeview/daemon.json with a live pid gets a moon on
# its diamond in the patch bay renderer. Repos without a tmux session are
# discovered fleet-wide (via the git panel's discovery cache, plus a shallow
# home scan fallback) so a serving daemon keeps its moon even when the
# session it was opened from has closed.
CODEVIEW_DIR_NAME = ".codeview"
CODEVIEW_SCAN_DEPTH = 6
CODEVIEW_FLEET_SCAN_MAX_DEPTH = 3
CODEVIEW_FLEET_SCAN_TIMEOUT = 1.0

# Directories never descended into while scanning $HOME for codeview repos.
CODEVIEW_SKIP_DIRS = frozenset(
    {
        ".cache", ".cargo", ".config", ".cursor", ".docker", ".git",
        ".local", ".npm", ".nvm", ".pyenv", ".rustup", ".steam",
        ".thumbnails", ".Trash", ".var", ".venv", "__pycache__",
        "AppData", "Applications", "Library", "Movies", "Music",
        "node_modules", "Pictures", "snap", "target", "Trash", "venv",
        "Videos",
    }
)

# The git status fetcher already walks $HOME for repos and caches the list;
# reuse it instead of scanning the same tree twice.
GIT_DISCOVERY_PATH = CACHE_DIR / "git-repo-discovery.json"
GIT_DISCOVERY_MAX_AGE_SECONDS = 30 * 60

# Must match the layout math in conky/sessions-renderer.lua.
# Drift keeps a fixed sinking field for ingress origins and a fixed bottom row
# for tmux destinations. Height only grows when a second destination row is
# needed.
PANEL_MIN_HEIGHT = 790
PANEL_DRIFT_TOP = 0
PANEL_DRIFT_FULL_HEIGHT = 460
PANEL_DRIFT_MIN_HEIGHT = 430
PANEL_SOURCE_COLUMNS = 3
PANEL_DESTINATION_ROW_HEIGHT = 110
PANEL_FOOTER_HEIGHT = 0
PANEL_DIAMOND_ZONE_HEIGHT = 330

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


def repo_from_path(path):
    """Best-effort repo key from a session path."""
    if not path:
        return ""
    name = Path(path).expanduser().name
    if name and name != "." and name != "":
        return name
    try:
        expanded = str(Path(path).expanduser())
    except (OSError, ValueError, RuntimeError):
        return ""
    if expanded in ("", "/"):
        return expanded
    return Path(expanded).name or expanded


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def proc_cmdline(pid):
    """Space-joined cmdline, or None where /proc is unavailable."""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None
    return raw.replace(b"\x00", b" ").decode("utf-8", "replace")


def codeview_index_age(repo_dir, now):
    """Seconds since the newest file under <repo>/.codeview/cache, or None."""
    cache_dir = Path(repo_dir) / CODEVIEW_DIR_NAME / "cache"
    newest = None
    try:
        for path in cache_dir.glob("*.json"):
            mtime = path.stat().st_mtime
            newest = mtime if newest is None else max(newest, mtime)
    except OSError:
        return None
    if newest is None:
        return None
    return max(0, int(now - newest))


def codeview_state_from_daemon(repo_dir, daemon_path, now):
    """Flattened daemon state for the renderer's regex JSON parser."""
    try:
        info = json.loads(daemon_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(info, dict) or not isinstance(info.get("pid"), int):
        return None
    running = pid_alive(info["pid"])
    cmdline = proc_cmdline(info["pid"])
    if running and cmdline is not None and "server.py" not in cmdline:
        running = False
    port = info.get("port")
    index_age = codeview_index_age(repo_dir, now)
    return {
        "present": True,
        "running": running,
        "port": port if isinstance(port, int) else 0,
        "indexAgeSeconds": index_age if index_age is not None else -1,
    }


def codeview_state(start_dir, now):
    """codeview daemon state for a session's working directory, or None.

    The repo root is found by walking up from the pane's cwd, so a session
    parked in a subdirectory still finds <repo>/.codeview/daemon.json. A
    daemon counts as running only if the pid answers and its cmdline still
    looks like the codeview server — the same test bin/codeview status uses.
    """
    try:
        current = Path(start_dir).expanduser().resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    for _ in range(CODEVIEW_SCAN_DEPTH):
        daemon = current / CODEVIEW_DIR_NAME / "daemon.json"
        if daemon.is_file():
            return codeview_state_from_daemon(current, daemon, now)
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None


def codeview_fields(start_dir, now):
    """The four flat session fields the Lua side parses; absent-safe."""
    state = codeview_state(start_dir, now)
    if state is None:
        return {
            "codeviewPresent": False,
            "codeviewRunning": False,
            "codeviewPort": 0,
            "codeviewIndexAgeSeconds": -1,
        }
    return {
        "codeviewPresent": state["present"],
        "codeviewRunning": state["running"],
        "codeviewPort": state["port"],
        "codeviewIndexAgeSeconds": state["indexAgeSeconds"],
    }


def _git_discovery_paths():
    """Fleet repo list from the git panel's discovery cache, or None."""
    try:
        payload = json.loads(GIT_DISCOVERY_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    paths = payload.get("paths") or []
    if not paths:
        return None
    return [Path(path) for path in paths]


def _scan_home_for_codeview(timeout=CODEVIEW_FLEET_SCAN_TIMEOUT):
    """Shallow $HOME walk for dirs with a .codeview/daemon.json.

    Used when the git discovery cache is missing or stale. A bounded BFS
    over the same skip-list the git fetcher uses, so a deep or heavy tree
    cannot fan out.
    """
    root_raw = os.environ.get("SESSIONS_CODEVIEW_SCAN_ROOT", "").strip()
    root = Path(root_raw) if root_raw else Path.home()
    if not root.is_dir():
        return []
    queue = [(root, 0)]
    found = []
    deadline = _monotonic() + timeout
    while queue:
        if _monotonic() > deadline:
            break
        current, depth = queue.pop(0)
        if depth > CODEVIEW_FLEET_SCAN_MAX_DEPTH:
            continue
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                is_dir = entry.is_dir() and not entry.is_symlink()
            except OSError:
                continue
            if not is_dir:
                continue
            if entry.name in CODEVIEW_SKIP_DIRS:
                continue
            if (entry / CODEVIEW_DIR_NAME / "daemon.json").is_file():
                found.append(entry)
                continue
            if depth < CODEVIEW_FLEET_SCAN_MAX_DEPTH:
                queue.append((entry, depth + 1))
    found.sort(key=lambda path: str(path).lower())
    return found


def _monotonic():
    """Monotonic clock for scan deadlines (injectable for tests)."""
    return time.monotonic()


def fleet_repo_paths():
    """Repo roots worth probing for a codeview daemon.

    Uses the git panel's discovery cache (30 min TTL) so the fleet matches
    what the git panel shows; falls back to a shallow $HOME scan when the
    cache is missing or stale. Pinned codeview roots from the environment
    are always included first.
    """
    pinned = os.environ.get("SESSIONS_CODEVIEW_REPO_PATHS", "").strip()
    pinned_paths = [Path(p) for p in re.split(r"[:\n,]+", pinned) if p.strip()]

    cached = _git_discovery_paths()
    if cached is not None:
        try:
            updated = int(json.loads(GIT_DISCOVERY_PATH.read_text(encoding="utf-8")).get("updatedAtEpoch") or 0)
        except (OSError, ValueError):
            updated = 0
        if updated and time.time() - updated <= GIT_DISCOVERY_MAX_AGE_SECONDS:
            merged = list(pinned_paths)
            seen = {str(p).rstrip("/") for p in pinned_paths}
            for path in cached:
                key = str(path).rstrip("/")
                if key not in seen:
                    seen.add(key)
                    merged.append(path)
            return merged

    scanned = _scan_home_for_codeview()
    merged = list(pinned_paths)
    seen = {str(p).rstrip("/") for p in pinned_paths}
    for path in scanned:
        key = str(path).rstrip("/")
        if key not in seen:
            seen.add(key)
            merged.append(path)
    return merged


def fleet_codeview_repos(now=None):
    """One record per fleet repo with a .codeview/daemon.json.

    This is what keeps a moon alive after its tmux session closes: the repo
    is discovered from the fleet list rather than only from session paths,
    so a serving daemon still shows up as a star with a moon in the bay.
    """
    if now is None:
        now = time.time()
    records = []
    for repo in fleet_repo_paths():
        state = codeview_state(str(repo), now)
        if state is None:
            continue
        name = repo.name or str(repo)
        records.append({
            "name": name,
            "path": str(repo),
            "codeviewPresent": True,
            "codeviewRunning": state["running"],
            "codeviewPort": state["port"],
            "codeviewIndexAgeSeconds": state["indexAgeSeconds"],
        })
    records.sort(key=lambda record: record["name"].lower())
    return records


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
    codeview_by_path = {}
    for line in listing.splitlines():
        fields = line.split("\t")
        if len(fields) < 4:
            continue
        name, windows, path, activity = fields[:4]
        idle_seconds = None
        if activity.isdigit():
            try:
                idle_seconds = int(now - float(activity))
                if idle_seconds < 0:
                    idle_seconds = 0
            except (ValueError, OverflowError):
                idle_seconds = None
        record = {
            "name": name,
            "windows": int(windows) if windows.isdigit() else 1,
            "panes": 0,
            "path": shorten_path(path),
            "repo": repo_from_path(path),
            "attached": [],
            "idle": relative_age(idle_seconds) if idle_seconds is not None else "",
            "idleSeconds": idle_seconds if idle_seconds is not None else 0,
        }
        # One codeview probe per distinct session path per fetch cycle.
        if path not in codeview_by_path:
            codeview_by_path[path] = codeview_fields(path, now)
        record.update(codeview_by_path[path])
        sessions[name] = record

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


def session_matches_codeview(session, repo_name, resolved_cv_path):
    session_path = session.get("path") or ""
    if resolved_cv_path is not None and session_path:
        try:
            # A usable path is authoritative. Basenames alone are not
            # identities: two unrelated repos can share the same name.
            resolved_session_path = Path(session_path).expanduser().resolve()
            return (
                resolved_session_path == resolved_cv_path
                or resolved_session_path.is_relative_to(resolved_cv_path)
            )
        except (OSError, RuntimeError, ValueError):
            pass
    return (
        (session.get("repo") or "").lower() == repo_name.lower()
        or (session.get("name") or "").lower() == repo_name.lower()
        or repo_from_path(session_path).lower() == repo_name.lower()
    )


def add_fleet_codeview_sessions(sessions, codeview_repos):
    """Add fleet dashboards that do not already have a tmux destination."""
    for cv_repo in codeview_repos:
        repo_name = cv_repo["name"]
        repo_path = cv_repo["path"]
        try:
            resolved_cv_path = Path(repo_path).expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            resolved_cv_path = None

        if any(
            session_matches_codeview(session, repo_name, resolved_cv_path)
            for session in sessions.values()
        ):
            continue

        session_key = repo_name
        if session_key in sessions:
            session_key = f"codeview:{resolved_cv_path or repo_path}"
            suffix = 2
            base_key = session_key
            while session_key in sessions:
                session_key = f"{base_key}:{suffix}"
                suffix += 1
        sessions[session_key] = {
            "name": repo_name,
            "windows": 0,
            "panes": 0,
            "path": shorten_path(repo_path),
            "repo": repo_name,
            "attached": [],
            "idle": "",
            "idleSeconds": 0,
            "codeviewPresent": True,
            "codeviewRunning": cv_repo["codeviewRunning"],
            "codeviewPort": cv_repo["codeviewPort"],
            "codeviewIndexAgeSeconds": cv_repo["codeviewIndexAgeSeconds"],
        }

    return sessions


def collect():
    sessions = tmux_sessions()
    clients = tmux_clients()
    peers, local_host = tailnet_peers()
    now = datetime.now(timezone.utc).timestamp()

    devices = []
    seen_ttys = set()
    for login in logins():
        # Drop local VT logins (tty2 etc.) — they sink as 2-day-old idle dots and
        # never match a kitty tmux client (which lives on pts/N). The user's
        # laptop is instead represented by the pts/* kitty clients themselves.
        if login["tty"].startswith("tty"):
            continue
        name, os_name, glyph, unknown = device_for(login, peers, local_host)
        session = clients.get(login["tty"])
        seen_ttys.add(login["tty"])
        age_seconds = None
        if login["since"]:
            try:
                age_seconds = int(now - login["since"])
                if age_seconds < 0:
                    age_seconds = 0
            except (ValueError, OverflowError):
                age_seconds = None
        age = relative_age(age_seconds) if age_seconds is not None else ""

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
            "ageSeconds": age_seconds if age_seconds is not None else 0,
            "state": state,
        })

    # Local kitty tmux clients (e.g. pts/1, pts/8 via xterm-kitty) are not
    # registered in utmp, so `who` never shows them and the tty->session
    # join misses them. Treat any tmux client whose tty is not already a
    # login device as a synthetic laptop ingress — this replaces the stale
    # tty2 dot and makes kitty-driven sessions appear connected. A single
    # physical laptop may have multiple pts clients; group by HostName so the
    # device only shows up once at most and all its sessions are marked
    # attached to that one dot.
    orphans_by_host = {}
    for tty, session in clients.items():
        if tty in seen_ttys:
            continue
        if session not in sessions:
            continue
        base_name = local_host or "laptop"
        orphans_by_host.setdefault(base_name, []).append((tty, session))

    for base_name, pairs in orphans_by_host.items():
        # Pick the freshest session for the dot's vertical position.
        pairs.sort(key=lambda p: sessions[p[1]].get("idleSeconds", 0))
        freshest_tty, freshest_session = pairs[0]
        idle_seconds = sessions[freshest_session].get("idleSeconds", 0) or 0
        age_seconds = idle_seconds
        age = relative_age(age_seconds)
        # If a real login device already uses this name (unlikely), keep it;
        # otherwise the synthetic laptop is the sole entry for this host.
        if any(d["name"] == base_name for d in devices):
            continue
        devices.append({
            "name": base_name,
            "os": "local",
            "glyph": "laptop",
            "tty": freshest_tty,
            "session": freshest_session,
            "age": age,
            "ageSeconds": age_seconds,
            "state": "live",
        })
        seen_ttys.add(freshest_tty)
        for _, sess_name in pairs:
            # Mark every session that this host drives as attached to the
            # single laptop dot so its diamond fills and a thread can be drawn.
            if base_name not in sessions[sess_name]["attached"]:
                sessions[sess_name]["attached"].append(base_name)
        for t, _ in pairs:
            seen_ttys.add(t)

    # Alerts first, then live links, then idle: the panel reads top-down.
    order = {"alert": 0, "live": 1, "idle": 2}
    devices.sort(key=lambda device: (order.get(device["state"], 3), device["name"]))

    # Fleet repos with a codeview daemon appear as unattached destination diamonds
    # at the bottom so their moon remains visible even after tmux closes (or if
    # opened without tmux).
    add_fleet_codeview_sessions(sessions, fleet_codeview_repos(now))

    session_list = sorted(
        sessions.values(),
        key=lambda item: (
            not item["attached"],
            (item.get("repo") or "").lower(),
            item["name"].lower(),
        ),
    )
    for session in session_list:
        session["attached"] = ", ".join(session["attached"])

    return devices, session_list


def session_rows_for(sessions):
    """Rows needed when same-repo sessions stay next to each other.

    Packs repo groups left-to-right; a group that wouldn't fit in the
    remaining slots of the current row is bumped to the next row (leaving
    a gap) unless the group itself is larger than a row. Must stay in
    sync with conky/sessions-renderer.lua layout_for.
    """
    if not sessions:
        return 0
    n = len(sessions)
    row = 0
    col = 0
    i = 0
    while i < n:
        repo = (sessions[i].get("repo") or "").lower()
        j = i + 1
        while j < n and (sessions[j].get("repo") or "").lower() == repo:
            j += 1
        group_size = j - i
        if col != 0 and group_size <= PANEL_SOURCE_COLUMNS and group_size > (PANEL_SOURCE_COLUMNS - col):
            row += 1
            col = 0
        for k in range(i, j):
            if col >= PANEL_SOURCE_COLUMNS:
                row += 1
                col = 0
            col += 1
            if col >= PANEL_SOURCE_COLUMNS and k != n - 1:
                row += 1
                col = 0
        i = j
    if col == 0:
        return row
    return row + 1


def overlay_height(session_count, sessions=None):
    """Conky minimum_height for the panel.

    Must match conky/sessions-renderer.lua: a fixed constellation field
    (PANEL_DRIFT_FULL_HEIGHT) plus a diamond zone that always reserves
    PANEL_DIAMOND_ZONE_HEIGHT so the bay holds the same footprint even when
    only one row of diamonds is present. Only an extra diamond row beyond
    that grows the panel.
    """
    if session_count == 0:
        session_rows = 0
    elif sessions is not None:
        session_rows = session_rows_for(sessions)
    else:
        session_rows = ceil(session_count / PANEL_SOURCE_COLUMNS)
    diamond_reserved = max(PANEL_DIAMOND_ZONE_HEIGHT, session_rows * PANEL_DESTINATION_ROW_HEIGHT)
    needed = PANEL_DRIFT_TOP + PANEL_DRIFT_FULL_HEIGHT + diamond_reserved + PANEL_FOOTER_HEIGHT
    if PANEL_DRIFT_FULL_HEIGHT < PANEL_DRIFT_MIN_HEIGHT:
        needed = PANEL_DRIFT_TOP + PANEL_DRIFT_MIN_HEIGHT + diamond_reserved + PANEL_FOOTER_HEIGHT
    return max(PANEL_MIN_HEIGHT, needed)


def current_overlay_height():
    """Height for the state right now, falling back to the last written cache."""
    try:
        _devices, sessions = collect()
        return overlay_height(len(sessions), sessions)
    except (OSError, ValueError):
        pass
    try:
        payload = json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return overlay_height(0)
    payload_sessions = payload.get("sessions") or []
    return overlay_height(len(payload_sessions), payload_sessions)


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
            f"sshd_listening={listening} height={overlay_height(len(sessions), sessions)}"
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

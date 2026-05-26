#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
CACHE_DIR = ROOT / "cache"
CONTRIBUTIONS_PATH = CACHE_DIR / "github-contributions.json"
LOG_PATH = CACHE_DIR / "conky-github.log"


def load_env(path):
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def log_event(message):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] fetch_github_contributions: {message}\n")


def atomic_write_json(path, data):
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp_path, path)


def git_config_value(key):
    try:
        result = subprocess.run(
            ["git", "config", "--get", key],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    return result.stdout.strip()


def github_username():
    for key in ("GITHUB_USERNAME", "GH_USERNAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value

    value = git_config_value("github.user")
    if value:
        return value

    remote = git_config_value("remote.origin.url")
    match = re.search(r"github\.com[:/]([^/]+)/", remote)
    if match:
        return match.group(1)

    raise ValueError("Set GITHUB_USERNAME in .env")


def fetch_contributions(username):
    url = f"https://github.com/users/{username}/contributions"
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "conky-linear-HUP/1.0",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers, method="GET")
    timeout = float(os.environ.get("GITHUB_TIMEOUT_SECONDS", "10"))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_contributions(html):
    entries = []

    for tag in re.findall(r"<td\b[^>]*ContributionCalendar-day[^>]*>", html):
        date_match = re.search(r'data-date="([^"]+)"', tag)
        level_match = re.search(r'data-level="([0-4])"', tag)
        if not date_match or not level_match:
            continue

        entries.append({
            "date": unescape(date_match.group(1)),
            "level": int(level_match.group(1)),
        })

    if not entries:
        raise ValueError("No contribution squares found in GitHub response")

    entries.sort(key=lambda item: item["date"])
    return entries[-371:]


def main():
    load_env(ENV_PATH)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        username = github_username()
        html = fetch_contributions(username)
        entries = parse_contributions(html)
        payload = {
            "ok": True,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "username": username,
            "contributions": entries,
        }
        atomic_write_json(CONTRIBUTIONS_PATH, payload)
        log_event(f"updated username={username} days={len(entries)}")
        return 0
    except (OSError, urllib.error.URLError, ValueError) as error:
        payload = {
            "ok": False,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "error": str(error),
        }
        atomic_write_json(CONTRIBUTIONS_PATH, payload)
        log_event(f"error: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

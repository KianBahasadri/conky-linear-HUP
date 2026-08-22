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

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
CONTRIBUTIONS_PATH = CACHE_DIR / "github-contributions.json"
LOG_PATH = CACHE_DIR / "conky-github.log"


log_event = common.make_logger(LOG_PATH, "fetch_github_contributions")
atomic_write_json = common.atomic_write_json


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


def parse_counts(html):
    """Per-day contribution counts, keyed by each cell's id.

    `data-level` is only 0-4, which is too coarse to extrude into towers — a
    typical year is mostly level 1. The same page carries the real number in a
    <tool-tip> element pointed at each cell by id.
    """
    counts = {}
    pattern = r'<tool-tip[^>]*\bfor="([^"]+)"[^>]*>(.*?)</tool-tip>'
    for cell_id, text in re.findall(pattern, html, re.DOTALL):
        match = re.match(r"\s*(?:(\d[\d,]*)|No)\s+contribution", unescape(text).strip())
        if not match:
            continue
        counts[cell_id] = int(match.group(1).replace(",", "")) if match.group(1) else 0
    return counts


def parse_contributions(html):
    entries = []
    counts = parse_counts(html)

    for tag in re.findall(r"<td\b[^>]*ContributionCalendar-day[^>]*>", html):
        date_match = re.search(r'data-date="([^"]+)"', tag)
        level_match = re.search(r'data-level="([0-4])"', tag)
        if not date_match or not level_match:
            continue

        level = int(level_match.group(1))
        id_match = re.search(r'\bid="([^"]+)"', tag)
        count = counts.get(id_match.group(1)) if id_match else None
        if count is None:
            # Tooltip missing: keep the day, and let the level stand in so the
            # renderer still has a magnitude to extrude.
            count = 0 if level == 0 else level * 2

        entries.append({
            "date": unescape(date_match.group(1)),
            "level": level,
            "count": count,
        })

    if not entries:
        raise ValueError("No contribution squares found in GitHub response")

    entries.sort(key=lambda item: item["date"])
    return entries[-371:]


def main():
    common.load_env()
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
        total = sum(entry["count"] for entry in entries)
        log_event(f"updated username={username} days={len(entries)} contributions={total}")
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

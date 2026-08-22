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


def github_token_via_gh():
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            token = (result.stdout or "").strip().splitlines()[0].strip()
            if token and len(token) > 10:
                return token
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return ""


def effective_github_token():
    env_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if env_token:
        return env_token
    return github_token_via_gh()


def fetch_contributions(username):
    url = f"https://github.com/users/{username}/contributions"
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "User-Agent": "conky-linear-HUP/1.0",
    }
    token = effective_github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers, method="GET")
    timeout = float(os.environ.get("GITHUB_TIMEOUT_SECONDS", "10"))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


GRAPHQL_LEVEL_MAP = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}


def fetch_contributions_graphql(username, token, from_iso, to_iso):
    query = (
        "query($login:String!,$from:DateTime!,$to:DateTime!){"
        "user(login:$login){contributionsCollection(from:$from,to:$to)"
        "{contributionCalendar{weeks{contributionDays"
        "{date contributionCount contributionLevel}}}}}}"
    )
    body = json.dumps(
        {"query": query, "variables": {"login": username, "from": from_iso, "to": to_iso}}
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "conky-linear-HUP/1.0",
        },
        method="POST",
    )
    timeout = float(os.environ.get("GITHUB_TIMEOUT_SECONDS", "10"))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    if "errors" in payload and payload["errors"]:
        raise ValueError(payload["errors"][0].get("message", "graphql error"))
    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    entries = []
    for week in weeks:
        for day in week.get("contributionDays", []):
            entries.append(
                {
                    "date": day["date"],
                    "level": GRAPHQL_LEVEL_MAP.get(day.get("contributionLevel"), 0),
                    "count": int(day.get("contributionCount", 0)),
                }
            )
    return entries


def fetch_contributions_graphql_extended(username, token):
    raw_days = os.environ.get("GITHUB_HISTORY_DAYS", "401")
    try:
        want_days = int(str(raw_days).strip() or 401)
    except (TypeError, ValueError):
        want_days = 401
    if want_days < 1:
        want_days = 401
    want_days = min(want_days, 730)

    today = datetime.now(timezone.utc).date()
    start = today - __import__("datetime").timedelta(days=want_days - 1)

    merged = {}
    cursor = start
    one_day = __import__("datetime").timedelta(days=1)
    while cursor <= today:
        window_end = min(cursor + __import__("datetime").timedelta(days=364), today)
        from_iso = f"{cursor.isoformat()}T00:00:00Z"
        to_iso = f"{(window_end + one_day).isoformat()}T00:00:00Z"
        chunk = fetch_contributions_graphql(username, token, from_iso, to_iso)
        for entry in chunk:
            if start.isoformat() <= entry["date"] <= today.isoformat():
                merged[entry["date"]] = entry
        cursor = window_end + one_day

    entries = sorted(merged.values(), key=lambda item: item["date"])
    if not entries:
        raise ValueError("No contribution days from GraphQL")
    return entries


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
    # Public page only has ~52 weeks; GITHUB_HISTORY_DAYS has no effect on it.
    return entries[-371:]


def parse_contributions_graphql_entries(entries):
    entries = sorted(entries, key=lambda item: item["date"])
    return entries


def main():
    common.load_env()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        username = github_username()
        token = effective_github_token()
        if token:
            try:
                entries = fetch_contributions_graphql_extended(username, token)
                payload = {
                    "ok": True,
                    "updatedAt": datetime.now(timezone.utc).isoformat(),
                    "username": username,
                    "contributions": entries,
                    "source": "graphql",
                }
                atomic_write_json(CONTRIBUTIONS_PATH, payload)
                total = sum(entry["count"] for entry in entries)
                log_event(f"updated username={username} days={len(entries)} contributions={total} source=graphql via={'GITHUB_TOKEN' if os.environ.get('GITHUB_TOKEN','').strip() else 'gh'}")
                return 0
            except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError, KeyError) as graphql_error:
                log_event(f"graphql extended fetch failed, falling back to HTML: {graphql_error}")

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

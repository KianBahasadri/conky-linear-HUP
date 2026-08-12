#!/usr/bin/env python3
"""Build and rotate witty one-liner facts for the git overlay header."""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common
import fetch_git_status as git_status
import fetch_github_contributions as github_contrib


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
FUNFACTS_PATH = CACHE_DIR / "git-funfacts.json"
ACCOUNT_CACHE_PATH = CACHE_DIR / "github-account-cache.json"
STATUS_PATH = CACHE_DIR / "git-status.json"
CONTRIBUTIONS_PATH = CACHE_DIR / "github-contributions.json"
LOG_PATH = CACHE_DIR / "conky-git.log"

DEFAULT_ROTATE_SECONDS = 300
ACCOUNT_TTL_SECONDS = 3600
MAX_RECENT_IDS = 24
MAX_FACT_CHARS = 78

WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


log_event = common.make_logger(LOG_PATH, "fetch_git_funfacts")
atomic_write_json = common.atomic_write_json


def env_int(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def now_utc():
    return datetime.now(timezone.utc)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def clamp_text(text, limit=MAX_FACT_CHARS):
    text = re.sub(r"\s+", " ", str(text)).strip()
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return text[: limit - 3].rstrip() + "..."


def github_headers():
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "conky-linear-HUP/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_get_json(url, timeout):
    request = urllib.request.Request(url, headers=github_headers(), method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def load_or_fetch_account(username, timeout, ttl=ACCOUNT_TTL_SECONDS):
    cached = read_json(ACCOUNT_CACHE_PATH) or {}
    fetched_at = common.parse_iso_epoch(cached.get("fetchedAt"))
    now_epoch = int(now_utc().timestamp())
    if (
        cached.get("ok")
        and cached.get("username") == username
        and fetched_at
        and now_epoch - fetched_at < ttl
    ):
        return cached

    try:
        user = github_get_json(f"https://api.github.com/users/{urllib.parse.quote(username)}", timeout)
        repos = []
        page = 1
        # Authenticated users can list private repos via /user/repos; public via /users/x/repos.
        token = os.environ.get("GITHUB_TOKEN", "").strip()
        while page <= 5:
            if token:
                url = (
                    "https://api.github.com/user/repos"
                    f"?per_page=100&page={page}&affiliation=owner&sort=updated"
                )
            else:
                url = (
                    f"https://api.github.com/users/{urllib.parse.quote(username)}/repos"
                    f"?per_page=100&page={page}&type=owner&sort=updated"
                )
            batch = github_get_json(url, timeout)
            if not isinstance(batch, list) or not batch:
                break
            # Keep only repos owned by this user when using /user/repos.
            for repo in batch:
                owner = (repo.get("owner") or {}).get("login") or ""
                if owner.lower() == username.lower() or not token:
                    repos.append(repo)
            if len(batch) < 100:
                break
            page += 1

        payload = {
            "ok": True,
            "fetchedAt": now_utc().isoformat(),
            "username": username,
            "user": {
                "login": user.get("login") or username,
                "followers": int(user.get("followers") or 0),
                "following": int(user.get("following") or 0),
                "publicRepos": int(user.get("public_repos") or 0),
                "publicGists": int(user.get("public_gists") or 0),
                "createdAt": user.get("created_at") or "",
                "hireable": bool(user.get("hireable")),
            },
            "repos": [
                {
                    "name": repo.get("name") or "",
                    "private": bool(repo.get("private")),
                    "fork": bool(repo.get("fork")),
                    "archived": bool(repo.get("archived")),
                    "stargazers": int(repo.get("stargazers_count") or 0),
                    "forks": int(repo.get("forks_count") or 0),
                    "language": repo.get("language") or "",
                    "createdAt": repo.get("created_at") or "",
                    "pushedAt": repo.get("pushed_at") or "",
                    "size": int(repo.get("size") or 0),
                    "defaultBranch": repo.get("default_branch") or "",
                }
                for repo in repos
                if repo.get("name")
            ],
        }
        atomic_write_json(ACCOUNT_CACHE_PATH, payload)
        log_event(f"account cache refreshed username={username} repos={len(payload['repos'])}")
        return payload
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, ValueError, TypeError) as error:
        log_event(f"account fetch failed: {error}")
        if cached.get("ok"):
            cached["stale"] = True
            return cached
        return {"ok": False, "error": str(error), "username": username, "user": {}, "repos": []}


def count_loc(repo_path, timeout=3.0):
    """Approximate LOC via git ls-files + reading text files (capped)."""
    try:
        listing = subprocess.run(
            ["git", "-C", str(repo_path), "ls-files"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if listing.returncode != 0:
        return None

    skip_ext = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".tgz",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp3",
        ".mp4",
        ".mov",
        ".bin",
        ".exe",
        ".dll",
        ".so",
        ".o",
        ".a",
        ".pyc",
        ".pyo",
        ".class",
        ".jar",
        ".lock",
        ".min.js",
        ".min.css",
        ".map",
        ".svg",
    }
    total = 0
    files_seen = 0
    for rel in listing.stdout.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        lower = rel.lower()
        if any(lower.endswith(ext) for ext in skip_ext):
            continue
        if "/node_modules/" in f"/{lower}/" or "/.git/" in f"/{lower}/":
            continue
        path = Path(repo_path) / rel
        try:
            if not path.is_file() or path.stat().st_size > 1_500_000:
                continue
            # Skip likely binary
            raw = path.read_bytes()[:8192]
            if b"\0" in raw:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            total += text.count("\n") + (1 if text and not text.endswith("\n") else 0)
            files_seen += 1
            if files_seen >= 4000:
                break
        except OSError:
            continue
    return total if files_seen else None


def count_todos(repo_path, timeout=3.0):
    try:
        result = subprocess.run(
            [
                "rg",
                "-n",
                "--hidden",
                "--glob",
                "!.git",
                "-e",
                r"\bTODO\b",
                "-e",
                r"\bFIXME\b",
                str(repo_path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode not in (0, 1):
        return None
    return sum(1 for line in result.stdout.splitlines() if line.strip())


def count_fix_commits(repo_path, timeout=3.0):
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "log",
                "--pretty=%s",
                "--all",
                "-n",
                "200",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return sum(1 for line in result.stdout.splitlines() if re.search(r"\bfix\b", line, re.I))


def contribution_stats(entries):
    if not entries:
        return {}
    by_weekday = Counter()
    active_days = 0
    level4 = 0
    best = None
    # streak / drought on sorted dates
    sorted_entries = sorted(entries, key=lambda item: item.get("date") or "")
    current_streak = 0
    longest_streak = 0
    current_drought = 0
    longest_drought = 0
    running_streak = 0
    running_drought = 0
    for entry in sorted_entries:
        level = int(entry.get("level") or 0)
        date = entry.get("date") or ""
        try:
            weekday = datetime.fromisoformat(date).weekday()
            by_weekday[weekday] += level
        except ValueError:
            pass
        if level > 0:
            active_days += 1
            running_streak += 1
            running_drought = 0
            longest_streak = max(longest_streak, running_streak)
        else:
            running_drought += 1
            running_streak = 0
            longest_drought = max(longest_drought, running_drought)
        if level >= 4:
            level4 += 1
        if best is None or level > best["level"] or (
            level == best["level"] and date > best["date"]
        ):
            best = {"date": date, "level": level}
        current_streak = running_streak
        current_drought = running_drought

    # Current streak/drought from the end of the calendar
    current_streak = 0
    current_drought = 0
    for entry in reversed(sorted_entries):
        level = int(entry.get("level") or 0)
        if current_streak == 0 and current_drought == 0:
            if level > 0:
                current_streak = 1
            else:
                current_drought = 1
            continue
        if current_streak > 0:
            if level > 0:
                current_streak += 1
            else:
                break
        else:
            if level == 0:
                current_drought += 1
            else:
                break

    most_active_weekday = None
    if by_weekday:
        most_active_weekday = WEEKDAYS[max(by_weekday.items(), key=lambda item: item[1])[0]]
    deadest_weekday = None
    if by_weekday:
        deadest_weekday = WEEKDAYS[min(by_weekday.items(), key=lambda item: item[1])[0]]

    weekend = by_weekday.get(5, 0) + by_weekday.get(6, 0)
    total_level = sum(by_weekday.values()) or 1
    return {
        "activeDays": active_days,
        "level4Days": level4,
        "bestDay": best,
        "currentStreak": current_streak,
        "longestStreak": longest_streak,
        "currentDrought": current_drought,
        "longestDrought": longest_drought,
        "mostActiveWeekday": most_active_weekday,
        "deadestWeekday": deadest_weekday,
        "weekendShare": round(100 * weekend / total_level),
        "totalDays": len(sorted_entries),
    }


def build_facts(status, contributions, account, local_extras):
    facts = []

    def add(fact_id, text, weight=1):
        text = clamp_text(text)
        if text:
            facts.append({"id": fact_id, "text": text, "weight": weight})

    summary = (status or {}).get("summary") or {}
    repos = (status or {}).get("repos") or []
    total = int(summary.get("total") or len(repos))
    dirty = int(summary.get("dirty") or 0)
    clean = int(summary.get("clean") or 0)
    stash = int(summary.get("stash") or 0)
    behind = int(summary.get("behind") or 0)
    ahead = int(summary.get("ahead") or 0)
    conflict = int(summary.get("conflict") or 0)

    if total:
        add("fleet_size", f"Watching {total} local repo{'s' if total != 1 else ''}")
    if total and dirty == 0 and clean == total:
        add("fleet_all_clean", "Fleet is 100% clean", weight=3)
    if dirty:
        dirtiest = max(
            (repo for repo in repos if repo.get("ok")),
            key=lambda repo: (
                int(repo.get("modified") or 0)
                + int(repo.get("untracked") or 0)
                + int(repo.get("staged") or 0)
            ),
            default=None,
        )
        if dirtiest:
            mess = (
                int(dirtiest.get("modified") or 0)
                + int(dirtiest.get("untracked") or 0)
                + int(dirtiest.get("staged") or 0)
            )
            add(
                "dirtiest",
                f"{dirtiest.get('name')}: {mess} dirty path{'s' if mess != 1 else ''}",
                weight=2,
            )
    if stash:
        add("fleet_stash", f"Stashes across fleet: {stash}")
    if behind:
        add("fleet_behind", f"Behind upstream on {behind} repo{'s' if behind != 1 else ''}")
    if ahead:
        add("fleet_ahead", f"Ahead of origin on {ahead} repo{'s' if ahead != 1 else ''}")
    if conflict:
        add(
            "fleet_conflict",
            f"Merge conflict on {conflict} repo{'s' if conflict != 1 else ''}",
            weight=3,
        )

    feature = [
        repo
        for repo in repos
        if repo.get("ok")
        and repo.get("branch")
        and repo.get("branch") not in {"main", "master", "DETACHED"}
    ]
    if feature:
        repo = feature[0]
        add(
            "side_quest",
            f"{repo.get('name')} on {repo.get('branch')}",
            weight=2,
        )

    no_upstream = [repo for repo in repos if repo.get("ok") and not repo.get("upstream")]
    if no_upstream:
        add(
            "no_upstream",
            f"{len(no_upstream)} watched repo{'s' if len(no_upstream) != 1 else ''} lack upstream",
        )

    # Sibling dirtiness comparison
    ok_repos = [repo for repo in repos if repo.get("ok")]
    if len(ok_repos) >= 2:
        ranked = sorted(
            ok_repos,
            key=lambda repo: int(repo.get("modified") or 0) + int(repo.get("untracked") or 0),
            reverse=True,
        )
        a, b = ranked[0], ranked[1]
        a_n = int(a.get("modified") or 0) + int(a.get("untracked") or 0)
        b_n = int(b.get("modified") or 0) + int(b.get("untracked") or 0)
        if a_n > b_n:
            add(
                "sibling_rivalry",
                f"{a.get('name')} dirtier than {b.get('name')} by {a_n - b_n}",
            )

    # Contribution calendar
    entries = (contributions or {}).get("contributions") or []
    if (contributions or {}).get("ok") and entries:
        stats = contribution_stats(entries)
        if stats.get("mostActiveWeekday"):
            add(
                "most_active_weekday",
                f"Most active weekday: {stats['mostActiveWeekday']}",
                weight=2,
            )
        if stats.get("deadestWeekday") and stats["deadestWeekday"] != stats.get("mostActiveWeekday"):
            add("deadest_weekday", f"Quietest weekday: {stats['deadestWeekday']}")
        if stats.get("currentStreak", 0) > 0:
            add(
                "current_streak",
                f"Green streak: {stats['currentStreak']} day{'s' if stats['currentStreak'] != 1 else ''}",
                weight=2,
            )
        if stats.get("longestStreak", 0) > 1:
            add("longest_streak", f"Longest streak: {stats['longestStreak']} days")
        if stats.get("longestDrought", 0) > 2:
            add("longest_drought", f"Longest drought: {stats['longestDrought']} days")
        best = stats.get("bestDay") or {}
        if best.get("date") and best.get("level", 0) > 0:
            add(
                "best_day",
                f"Busiest day: {best['date']} (level {best['level']})",
                weight=2,
            )
        if stats.get("activeDays"):
            add(
                "active_days",
                f"Active days: {stats['activeDays']}/{stats.get('totalDays', '?')}",
            )
        if stats.get("weekendShare") is not None:
            add("weekend_warrior", f"Weekend activity: ~{stats['weekendShare']}%")

    # GitHub account portfolio
    user = (account or {}).get("user") or {}
    remote_repos = (account or {}).get("repos") or []
    if (account or {}).get("ok") and user:
        followers = int(user.get("followers") or 0)
        following = int(user.get("following") or 0)
        add(
            "followers",
            f"{followers} follower{'s' if followers != 1 else ''}",
            weight=2,
        )
        if following:
            add("following", f"Following {following}")
            ratio = followers / max(following, 1)
            add("follow_ratio", f"Follower:following ≈ {ratio:.2f}")

        created = user.get("createdAt") or ""
        created_epoch = common.parse_iso_epoch(created)
        if created_epoch:
            years = max(0, (int(now_utc().timestamp()) - created_epoch) / (365.25 * 24 * 3600))
            add("account_age", f"Account age: {years:.1f} years", weight=2)

        public = int(user.get("publicRepos") or 0)
        private = sum(1 for repo in remote_repos if repo.get("private"))
        # public_repos from API is public only; listed repos may include private with token
        listed_public = sum(1 for repo in remote_repos if not repo.get("private"))
        listed_total = len(remote_repos)
        if listed_total:
            add(
                "public_private",
                f"{listed_public} public · {private} private ({round(100 * private / listed_total)}%)",
                weight=3,
            )
        elif public:
            add("public_repos", f"{public} public repos")

        if listed_total:
            add("repo_count", f"{listed_total} owned repos visible")

        forks = sum(1 for repo in remote_repos if repo.get("fork"))
        originals = listed_total - forks
        if listed_total:
            add("forks_vs_original", f"{originals} original · {forks} forks")

        archived = sum(1 for repo in remote_repos if repo.get("archived"))
        if archived:
            add("archived", f"{archived} archived repo{'s' if archived != 1 else ''}")

        if remote_repos:
            top = max(remote_repos, key=lambda repo: int(repo.get("stargazers") or 0))
            stars = int(top.get("stargazers") or 0)
            if stars > 0:
                add(
                    "top_starred",
                    f"Most starred: {top.get('name')} ★{stars}",
                    weight=2,
                )
            total_stars = sum(int(repo.get("stargazers") or 0) for repo in remote_repos)
            if total_stars:
                add("total_stars", f"Stars across your repos: {total_stars}")

            languages = Counter(
                repo.get("language") for repo in remote_repos if repo.get("language")
            )
            if languages:
                lang, count = languages.most_common(1)[0]
                pct = round(100 * count / max(1, sum(languages.values())))
                add(
                    "top_language",
                    f"Top language: {lang} (~{pct}% of repos)",
                    weight=2,
                )
                add("language_count", f"{len(languages)} languages in portfolio")

            dated = [repo for repo in remote_repos if repo.get("createdAt")]
            if dated:
                oldest = min(dated, key=lambda repo: repo.get("createdAt") or "")
                newest = max(dated, key=lambda repo: repo.get("createdAt") or "")
                add("oldest_repo", f"Oldest repo: {oldest.get('name')}")
                add("newest_repo", f"Newest repo: {newest.get('name')}")

            masterish = sum(
                1
                for repo in remote_repos
                if (repo.get("defaultBranch") or "").lower() == "master"
            )
            if masterish:
                add(
                    "default_master",
                    f"{masterish} repo{'s' if masterish != 1 else ''} still default to master",
                )

        gists = int(user.get("publicGists") or 0)
        if gists:
            add("gists", f"{gists} public gist{'s' if gists != 1 else ''}")
        if user.get("hireable"):
            add("hireable", "Hireable flag is ON")

    # Local extras: LOC / TODOs / fix commits for watched repos
    for name, loc in (local_extras.get("loc") or {}).items():
        if loc is None:
            continue
        pages = max(1, round(loc / 300))
        add(
            f"loc_{name}",
            f"{name}: ~{loc:,} LOC (~{pages} page{'s' if pages != 1 else ''})",
            weight=2,
        )
    for name, todos in (local_extras.get("todos") or {}).items():
        if todos:
            add(
                f"todos_{name}",
                f"{name}: {todos} TODO/FIXME{'s' if todos != 1 else ''}",
                weight=2,
            )
    for name, fixes in (local_extras.get("fixes") or {}).items():
        if fixes:
            add(
                f"fix_{name}",
                f"{name}: {fixes} recent 'fix' commit{'s' if fixes != 1 else ''}",
            )

    if not facts:
        add("fallback", "Git HUD online — waiting for facts")

    return facts


def gather_local_extras(status, timeout=2.5):
    extras = {"loc": {}, "todos": {}, "fixes": {}}
    repos = (status or {}).get("repos") or []
    # Only sample a few ok repos to stay fast.
    candidates = [repo for repo in repos if repo.get("ok") and repo.get("path")][:4]
    for repo in candidates:
        path = Path(repo["path"])
        name = repo.get("name") or path.name
        extras["loc"][name] = count_loc(path, timeout=timeout)
        extras["todos"][name] = count_todos(path, timeout=timeout)
        extras["fixes"][name] = count_fix_commits(path, timeout=timeout)
    return extras


def pick_fact(pool, previous, recent_ids, rotate_seconds):
    now_epoch = int(now_utc().timestamp())
    pool_by_id = {fact["id"]: fact for fact in pool if fact.get("id")}
    if previous and previous.get("text") and previous.get("id"):
        shown = int(previous.get("shownAtEpoch") or 0)
        if shown and now_epoch - shown < rotate_seconds:
            # Keep current fact until rotation window ends, but refresh
            # wording from the live pool so copy edits apply immediately.
            refreshed = dict(previous)
            live = pool_by_id.get(previous["id"])
            if live and live.get("text"):
                refreshed["text"] = live["text"]
            return refreshed, recent_ids, False

    recent = list(recent_ids or [])
    candidates = [fact for fact in pool if fact["id"] not in recent]
    if not candidates:
        candidates = list(pool)
        recent = []

    # Weighted random choice
    weights = [max(1, int(fact.get("weight") or 1)) for fact in candidates]
    choice = random.choices(candidates, weights=weights, k=1)[0]
    current = {
        "id": choice["id"],
        "text": choice["text"],
        "shownAtEpoch": now_epoch,
    }
    recent = ([choice["id"]] + recent)[:MAX_RECENT_IDS]
    return current, recent, True


def collect_funfacts():
    common.load_env()
    rotate_seconds = max(30, env_int("GIT_FUNFACT_ROTATE_SECONDS", DEFAULT_ROTATE_SECONDS))
    timeout = float(os.environ.get("GITHUB_TIMEOUT_SECONDS", "10") or 10)

    status = read_json(STATUS_PATH)
    if not status or not status.get("ok"):
        # Best-effort live fleet snapshot if cache missing.
        try:
            status = git_status.collect_status()
        except Exception:
            status = {"ok": False, "summary": {}, "repos": []}

    contributions = read_json(CONTRIBUTIONS_PATH) or {}

    username = ""
    try:
        username = github_contrib.github_username()
    except ValueError:
        username = (contributions or {}).get("username") or ""

    account = {"ok": False, "user": {}, "repos": []}
    if username:
        account = load_or_fetch_account(username, timeout=timeout)

    local_extras = gather_local_extras(status)
    pool = build_facts(status, contributions, account, local_extras)

    previous_payload = read_json(FUNFACTS_PATH) or {}
    previous = previous_payload.get("current") or {}
    recent_ids = previous_payload.get("recentIds") or []
    current, recent_ids, rotated = pick_fact(pool, previous, recent_ids, rotate_seconds)

    return {
        "ok": True,
        "updatedAt": now_utc().isoformat(),
        "updatedAtEpoch": int(now_utc().timestamp()),
        "rotateSeconds": rotate_seconds,
        "username": username,
        "poolSize": len(pool),
        "rotated": rotated,
        "current": current,
        "recentIds": recent_ids,
        "error": "",
    }


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()
    try:
        payload = collect_funfacts()
    except Exception as error:
        payload = {
            "ok": False,
            "updatedAt": now_utc().isoformat(),
            "updatedAtEpoch": int(now_utc().timestamp()),
            "error": str(error),
            "current": {
                "id": "error",
                "text": "Fun facts temporarily offline. The repos remain chaotic.",
                "shownAtEpoch": int(now_utc().timestamp()),
            },
            "recentIds": [],
            "poolSize": 0,
            "rotated": False,
        }
        log_event(f"error: {error}")
        atomic_write_json(FUNFACTS_PATH, payload)
        return 1

    atomic_write_json(FUNFACTS_PATH, payload)
    current = payload.get("current") or {}
    log_event(
        f"ok pool={payload.get('poolSize')} rotated={payload.get('rotated')} "
        f"id={current.get('id')} text={current.get('text')!r}"
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

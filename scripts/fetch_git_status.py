#!/usr/bin/env python3
"""Fetch compact git status for configured local repositories."""

from __future__ import annotations

import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
STATUS_PATH = CACHE_DIR / "git-status.json"
LOG_PATH = CACHE_DIR / "conky-git.log"

# Severity tiers used for sorting (higher = more urgent).
SEVERITY_CONFLICT = 100
SEVERITY_ERROR = 90
SEVERITY_BEHIND = 70
SEVERITY_DIRTY = 40
SEVERITY_STASH = 25
SEVERITY_AHEAD = 15
SEVERITY_CLEAN = 0

DEFAULT_BRANCHES = ("main", "master")


log_event = common.make_logger(LOG_PATH, "fetch_git_status")
atomic_write_json = common.atomic_write_json


def env_int(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    return value


def env_float(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    return value


def env_flag(name, default=False):
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off", "disabled"}


def split_path_list(raw):
    """Split colon/comma/newline-separated path lists, preserving order."""
    if not raw:
        return []
    parts = re.split(r"[:\n,]+", raw)
    return [part.strip() for part in parts if part.strip()]


def expand_repo_path(raw_path):
    return Path(os.path.expandvars(os.path.expanduser(raw_path))).resolve()


def parse_repo_paths(raw=None):
    """Return ordered unique repo paths from GIT_REPO_PATHS."""
    if raw is None:
        raw = os.environ.get("GIT_REPO_PATHS", "")
    paths = []
    seen = set()
    for entry in split_path_list(raw):
        path = expand_repo_path(entry)
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        paths.append(path)
    return paths


def parse_default_branches(raw=None):
    if raw is None:
        raw = os.environ.get("GIT_DEFAULT_BRANCHES", "")
    branches = [part.strip() for part in re.split(r"[,\s]+", raw) if part.strip()]
    return tuple(branches) if branches else DEFAULT_BRANCHES


def run_git(repo_path, args, timeout):
    command = ["git", "-C", str(repo_path), *args]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(f"git timed out after {timeout}s: {' '.join(args)}") from error
    except FileNotFoundError as error:
        raise RuntimeError("git executable not found on PATH") from error

    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "git command failed").strip()
        message = re.sub(r"\s+", " ", message)
        raise RuntimeError(message or f"git exited {completed.returncode}")
    return completed.stdout


def parse_ahead_behind(ab_line):
    # branch.ab +ahead -behind
    match = re.search(r"\+(\d+)\s+-(\d+)", ab_line or "")
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def classify_xy(xy):
    """Return staged/modified flags from a two-character porcelain XY code."""
    if not xy or len(xy) < 2:
        return False, False
    index_state, worktree_state = xy[0], xy[1]
    staged = index_state not in {".", " ", "?", "!"}
    modified = worktree_state not in {".", " ", "?", "!"}
    return staged, modified


def parse_porcelain_v2(output):
    branch = "HEAD"
    upstream = ""
    detached = False
    ahead = 0
    behind = 0
    staged = 0
    modified = 0
    untracked = 0
    conflicted = 0

    for raw_line in output.splitlines():
        line = raw_line.rstrip("\n")
        if not line:
            continue

        if line.startswith("# branch.head "):
            head = line[len("# branch.head ") :].strip()
            if head == "(detached)":
                detached = True
                branch = "DETACHED"
            else:
                branch = head or "HEAD"
            continue
        if line.startswith("# branch.upstream "):
            upstream = line[len("# branch.upstream ") :].strip()
            continue
        if line.startswith("# branch.ab "):
            ahead, behind = parse_ahead_behind(line)
            continue
        if line.startswith("#"):
            continue

        if line.startswith("? "):
            untracked += 1
            continue
        if line.startswith("! "):
            continue
        if line.startswith("u "):
            conflicted += 1
            # Unmerged entries also often show in worktree; count conflict only.
            continue

        # Ordinary (1) or rename/copy (2) entries: "1 XY ..." / "2 XY ..."
        if line[0] in {"1", "2"} and len(line) >= 4 and line[1] == " ":
            xy = line[2:4]
            is_staged, is_modified = classify_xy(xy)
            if is_staged:
                staged += 1
            if is_modified:
                modified += 1
            # Conflict-ish ordinary codes (rare with v2, but cheap to catch)
            if "U" in xy or xy in {"DD", "AU", "UA", "DU", "UD", "AA"}:
                conflicted += 1

    return {
        "branch": branch,
        "upstream": upstream,
        "detached": detached,
        "ahead": ahead,
        "behind": behind,
        "staged": staged,
        "modified": modified,
        "untracked": untracked,
        "conflicted": conflicted,
    }


def count_stashes(repo_path, timeout):
    try:
        output = run_git(repo_path, ["stash", "list"], timeout=timeout)
    except (RuntimeError, TimeoutError):
        return 0
    return sum(1 for line in output.splitlines() if line.strip())


def compute_state(repo):
    if not repo.get("ok"):
        return "error"
    if repo.get("conflicted", 0) > 0:
        return "conflict"
    if repo.get("detached"):
        return "detached"
    if repo.get("behind", 0) > 0:
        return "behind"
    if (
        repo.get("staged", 0) > 0
        or repo.get("modified", 0) > 0
        or repo.get("untracked", 0) > 0
    ):
        return "dirty"
    if repo.get("stash", 0) > 0:
        return "stash"
    if repo.get("ahead", 0) > 0:
        return "ahead"
    return "clean"


def compute_severity(repo):
    state = repo.get("state") or compute_state(repo)
    if state == "error":
        return SEVERITY_ERROR
    if state == "conflict":
        return SEVERITY_CONFLICT + min(repo.get("conflicted", 0), 20)
    if state == "detached":
        return SEVERITY_BEHIND + 5
    if state == "behind":
        return SEVERITY_BEHIND + min(repo.get("behind", 0), 20)
    if state == "dirty":
        dirty = (
            repo.get("staged", 0)
            + repo.get("modified", 0)
            + repo.get("untracked", 0)
        )
        return SEVERITY_DIRTY + min(dirty, 30)
    if state == "stash":
        return SEVERITY_STASH + min(repo.get("stash", 0), 10)
    if state == "ahead":
        return SEVERITY_AHEAD + min(repo.get("ahead", 0), 10)
    return SEVERITY_CLEAN


def inspect_repo(repo_path, timeout, include_stash=True):
    name = repo_path.name or str(repo_path)
    base = {
        "name": name,
        "path": str(repo_path),
        "ok": False,
        "error": "",
        "branch": "",
        "upstream": "",
        "detached": False,
        "ahead": 0,
        "behind": 0,
        "staged": 0,
        "modified": 0,
        "untracked": 0,
        "conflicted": 0,
        "stash": 0,
        "clean": False,
        "state": "error",
        "severity": SEVERITY_ERROR,
    }

    if not repo_path.exists():
        base["error"] = "path not found"
        return base
    if not repo_path.is_dir():
        base["error"] = "not a directory"
        return base

    git_dir = repo_path / ".git"
    if not git_dir.exists():
        # Could still be a worktree linked via .git file; ask git.
        try:
            run_git(repo_path, ["rev-parse", "--is-inside-work-tree"], timeout=timeout)
        except (RuntimeError, TimeoutError) as error:
            base["error"] = "not a git repository"
            if str(error):
                base["error"] = str(error)[:160]
            return base

    try:
        porcelain = run_git(
            repo_path,
            ["status", "--porcelain=v2", "--branch", "--untracked-files=normal"],
            timeout=timeout,
        )
        parsed = parse_porcelain_v2(porcelain)
        stash = count_stashes(repo_path, timeout=timeout) if include_stash else 0
    except (RuntimeError, TimeoutError) as error:
        base["error"] = str(error)[:160] or "git status failed"
        return base

    clean = (
        parsed["staged"] == 0
        and parsed["modified"] == 0
        and parsed["untracked"] == 0
        and parsed["conflicted"] == 0
        and parsed["ahead"] == 0
        and parsed["behind"] == 0
        and stash == 0
        and not parsed["detached"]
    )

    repo = {
        **base,
        "ok": True,
        "error": "",
        **parsed,
        "stash": stash,
        "clean": clean,
    }
    repo["state"] = compute_state(repo)
    # Clean only when truly idle; "ahead" is not clean for display purposes
    # but severity still ranks below dirty.
    if repo["state"] == "clean":
        repo["clean"] = True
    repo["severity"] = compute_severity(repo)
    return repo


def sort_repos(repos):
    return sorted(
        repos,
        key=lambda repo: (
            -int(repo.get("severity") or 0),
            (repo.get("name") or "").lower(),
        ),
    )


def build_summary(repos):
    summary = {
        "total": len(repos),
        "dirty": 0,
        "behind": 0,
        "ahead": 0,
        "conflict": 0,
        "stash": 0,
        "clean": 0,
        "error": 0,
        "detached": 0,
    }
    for repo in repos:
        state = repo.get("state") or "error"
        if state in summary:
            summary[state] += 1
        elif state == "error":
            summary["error"] += 1
        # ahead-only is its own state; dirty/behind already counted
    return summary


def collect_status(repo_paths=None, timeout=None, hide_clean=None, max_repos=None):
    common.load_env()
    if repo_paths is None:
        repo_paths = parse_repo_paths()
    if timeout is None:
        timeout = env_float("GIT_TIMEOUT_SECONDS", 2.0)
    if hide_clean is None:
        hide_clean = env_flag("GIT_HIDE_CLEAN", False)
    if max_repos is None:
        max_repos = env_int("GIT_MAX_REPOS", 12)
    if max_repos < 1:
        max_repos = 12

    timeout = max(0.5, float(timeout))
    include_stash = env_flag("GIT_INCLUDE_STASH", True)

    if not repo_paths:
        return {
            "ok": False,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "updatedAtEpoch": int(datetime.now(timezone.utc).timestamp()),
            "error": "Set GIT_REPO_PATHS in .env (colon-separated repo paths)",
            "summary": build_summary([]),
            "repos": [],
        }

    repos = []
    workers = min(8, max(1, len(repo_paths)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(inspect_repo, path, timeout, include_stash): path
            for path in repo_paths
        }
        for future in as_completed(futures):
            repos.append(future.result())

    repos = sort_repos(repos)
    if hide_clean:
        repos = [repo for repo in repos if repo.get("state") != "clean"]
    if len(repos) > max_repos:
        repos = repos[:max_repos]

    summary = build_summary(repos)
    now = datetime.now(timezone.utc)
    return {
        "ok": True,
        "updatedAt": now.isoformat(),
        "updatedAtEpoch": int(now.timestamp()),
        "error": "",
        "summary": summary,
        "repos": repos,
    }


def write_error(message):
    old_status = None
    try:
        old_status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    if old_status and old_status.get("ok") and old_status.get("repos"):
        old_status["stale"] = True
        old_status["error"] = message
        atomic_write_json(STATUS_PATH, old_status)
    else:
        atomic_write_json(
            STATUS_PATH,
            {
                "ok": False,
                "stale": False,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "updatedAtEpoch": int(datetime.now(timezone.utc).timestamp()),
                "error": message,
                "summary": build_summary([]),
                "repos": [],
            },
        )
    log_event(f"error: {message}")


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()
    try:
        status = collect_status()
    except Exception as error:
        write_error(f"Git status fetch failed: {error}")
        return 1

    atomic_write_json(STATUS_PATH, status)
    summary = status.get("summary") or {}
    log_event(
        "completed fetch "
        f"repos={summary.get('total', 0)} dirty={summary.get('dirty', 0)} "
        f"behind={summary.get('behind', 0)} conflict={summary.get('conflict', 0)} "
        f"clean={summary.get('clean', 0)} error={summary.get('error', 0)}"
    )
    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0 if status.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

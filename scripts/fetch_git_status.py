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
DISCOVERY_PATH = CACHE_DIR / "git-repo-discovery.json"
ACTIONS_CACHE_PATH = CACHE_DIR / "git-actions-cache.json"
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
DEFAULT_SCAN_DAYS = 14
DEFAULT_SCAN_MAX_DEPTH = 3
DEFAULT_SCAN_TTL_SECONDS = 300
DEFAULT_ACTIONS_TTL_SECONDS = 180
DEFAULT_ACTIONS_RUNNING_TTL_SECONDS = 20
DEFAULT_ACTIONS_EMPTY_TTL_SECONDS = 300

# A clean repo is only hidden once we know it has no Actions run, so pips have to
# be resolved for more rows than the panel shows. Probe this multiple of
# GIT_MAX_REPOS instead of the whole fleet so a large $HOME scan cannot fan out
# into dozens of `gh` calls per refresh.
ACTIONS_PROBE_ROWS_MULTIPLIER = 3

GITHUB_REMOTE_RE = re.compile(
    r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/#?\s]+)",
    re.IGNORECASE,
)
ACTIONS_ACTIVE_STATUSES = frozenset(
    {"in_progress", "queued", "waiting", "requested", "pending"}
)
ACTIONS_FAIL_CONCLUSIONS = frozenset(
    {"failure", "timed_out", "action_required", "startup_failure"}
)
ACTIONS_OK_CONCLUSIONS = frozenset({"success"})

# Directories we never descend into while discovering repos under $HOME.
SKIP_DIR_NAMES = frozenset(
    {
        ".cache",
        ".cargo",
        ".config",
        ".cursor",
        ".docker",
        ".git",
        ".local",
        ".npm",
        ".nvm",
        ".pyenv",
        ".rustup",
        ".steam",
        ".thumbnails",
        ".Trash",
        ".var",
        ".venv",
        "__pycache__",
        "AppData",
        "Applications",
        "Library",
        "Movies",
        "Music",
        "node_modules",
        "Pictures",
        "snap",
        "target",
        "Trash",
        "venv",
        "Videos",
    }
)


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
    """Return ordered unique repo paths from GIT_REPO_PATHS (pinned extras)."""
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


def parse_blacklist(raw=None):
    """
    Parse GIT_REPO_BLACKLIST entries.

    Path-like entries (~, /, $VAR) match resolved paths (exact or under that dir).
    Bare names match the repo directory basename (case-insensitive).
    """
    if raw is None:
        raw = os.environ.get("GIT_REPO_BLACKLIST", "")
    rules = []
    for entry in split_path_list(raw):
        if entry.startswith("~") or entry.startswith("$") or "/" in entry:
            rules.append(expand_repo_path(entry))
        else:
            rules.append(entry.casefold())
    return rules


def is_blacklisted(path: Path, rules=None) -> bool:
    if rules is None:
        rules = parse_blacklist()
    if not rules:
        return False
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    name = resolved.name.casefold()
    for rule in rules:
        if isinstance(rule, Path):
            try:
                rule_resolved = rule.resolve()
            except OSError:
                rule_resolved = rule
            if resolved == rule_resolved:
                return True
            # Blacklisting a parent directory drops every repo under it.
            try:
                resolved.relative_to(rule_resolved)
                return True
            except ValueError:
                continue
        elif name == str(rule).casefold():
            return True
    return False


def apply_blacklist(paths, rules=None):
    if rules is None:
        rules = parse_blacklist()
    if not rules:
        return list(paths)
    return [path for path in paths if not is_blacklisted(path, rules)]


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


def is_git_repo(path: Path) -> bool:
    """True if path is a git work tree root (.git file or directory)."""
    try:
        git_entry = path / ".git"
        return git_entry.is_dir() or git_entry.is_file()
    except OSError:
        return False


def should_skip_dir(name: str) -> bool:
    if name in SKIP_DIR_NAMES:
        return True
    # Skip most hidden dirs; still allow scanning non-hidden project folders.
    if name.startswith("."):
        return True
    return False


def last_commit_epoch(repo_path: Path, timeout: float) -> int | None:
    """Return unix epoch of HEAD commit, or None if unavailable."""
    try:
        output = run_git(repo_path, ["log", "-1", "--format=%ct"], timeout=timeout)
    except (RuntimeError, TimeoutError):
        return None
    raw = (output or "").strip().splitlines()
    if not raw:
        return None
    try:
        return int(raw[0].strip())
    except ValueError:
        return None


def is_dirty_repo(repo_path: Path, timeout: float) -> bool:
    """True if the repo has uncommitted activity: staged/modified/untracked
    changes, conflicts, a stash, ahead/behind, or detached HEAD."""
    try:
        porcelain = run_git(
            repo_path,
            ["status", "--porcelain=v2", "--branch", "--untracked-files=normal"],
            timeout=timeout,
        )
    except (RuntimeError, TimeoutError):
        return False
    parsed = parse_porcelain_v2(porcelain)
    if (
        parsed["staged"] > 0
        or parsed["modified"] > 0
        or parsed["untracked"] > 0
        or parsed["conflicted"] > 0
        or parsed["ahead"] > 0
        or parsed["behind"] > 0
        or parsed["detached"]
    ):
        return True
    return count_stashes(repo_path, timeout) > 0


def scan_home_for_recent_repos(
    root: Path | None = None,
    since_days: int | None = None,
    max_depth: int | None = None,
    timeout: float = 1.5,
):
    """
    Walk root (default $HOME) for git repos with a commit in the last since_days.

    A repo is included if its latest commit is within the cutoff OR if it is
    currently dirty (untracked/modified/staged/conflicted changes, a stash,
    ahead/behind, or detached HEAD) — dirty repos are surfaced regardless of
    commit age.

    Skips heavy/hidden directories. Does not descend into a found repo.
    Returns paths sorted by most-recent commit first.
    """
    if root is None:
        root_raw = os.environ.get("GIT_SCAN_ROOT", "").strip() or str(Path.home())
        root = expand_repo_path(root_raw)
    if since_days is None:
        since_days = env_int("GIT_SCAN_DAYS", DEFAULT_SCAN_DAYS)
    if max_depth is None:
        max_depth = env_int("GIT_SCAN_MAX_DEPTH", DEFAULT_SCAN_MAX_DEPTH)

    since_days = max(1, int(since_days))
    max_depth = max(1, min(8, int(max_depth)))
    cutoff = int(datetime.now(timezone.utc).timestamp()) - since_days * 86400

    found: list[tuple[int, Path]] = []
    root = Path(root)
    if not root.is_dir():
        return []

    # Depth-limited BFS so shallow personal projects win over deep junk.
    queue: list[tuple[Path, int]] = [(root, 0)]
    while queue:
        current, depth = queue.pop(0)
        if depth > max_depth:
            continue
        try:
            entries = list(current.iterdir())
        except OSError:
            continue

        for entry in entries:
            try:
                if not entry.is_dir() or entry.is_symlink():
                    continue
            except OSError:
                continue

            name = entry.name
            # Skip hidden/bulk dirs at every depth (including $HOME children).
            if should_skip_dir(name) or name in SKIP_DIR_NAMES:
                continue

            if is_git_repo(entry):
                epoch = last_commit_epoch(entry, timeout=timeout)
                if (epoch is not None and epoch >= cutoff) or is_dirty_repo(entry, timeout=timeout):
                    try:
                        resolved = entry.resolve()
                    except OSError:
                        resolved = entry
                    found.append((epoch or 0, resolved))
                # Never walk into a git work tree.
                continue

            if depth < max_depth:
                queue.append((entry, depth + 1))

    found.sort(key=lambda item: (-item[0], str(item[1]).lower()))
    return [path for _, path in found]


def load_discovery_cache(ttl_seconds: int):
    try:
        payload = json.loads(DISCOVERY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    updated = int(payload.get("updatedAtEpoch") or 0)
    now = int(datetime.now(timezone.utc).timestamp())
    if not updated or now - updated > max(30, ttl_seconds):
        return None
    paths = []
    for raw in payload.get("paths") or []:
        try:
            paths.append(Path(raw))
        except TypeError:
            continue
    return paths


def save_discovery_cache(paths, meta=None):
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "updatedAtEpoch": int(datetime.now(timezone.utc).timestamp()),
        "paths": [str(path) for path in paths],
        "meta": meta or {},
    }
    atomic_write_json(DISCOVERY_PATH, payload)


def discover_scanned_repos(timeout=None):
    """Return recent home repos, using the discovery cache when fresh."""
    if timeout is None:
        timeout = env_float("GIT_TIMEOUT_SECONDS", 2.0)
    scan_timeout = min(float(timeout), 1.5)
    ttl = env_int("GIT_SCAN_TTL_SECONDS", DEFAULT_SCAN_TTL_SECONDS)
    cached = load_discovery_cache(ttl)
    if cached is not None:
        return cached

    paths = scan_home_for_recent_repos(timeout=scan_timeout)
    save_discovery_cache(
        paths,
        meta={
            "sinceDays": env_int("GIT_SCAN_DAYS", DEFAULT_SCAN_DAYS),
            "maxDepth": env_int("GIT_SCAN_MAX_DEPTH", DEFAULT_SCAN_MAX_DEPTH),
            "root": str(expand_repo_path(os.environ.get("GIT_SCAN_ROOT", "") or str(Path.home()))),
        },
    )
    log_event(
        f"discovered {len(paths)} repo(s) under home "
        f"(last {env_int('GIT_SCAN_DAYS', DEFAULT_SCAN_DAYS)}d or dirty)"
    )
    return paths


def merge_repo_paths(pinned, scanned):
    """Pinned first (stable order), then scanned uniques."""
    merged = []
    seen = set()
    for path in list(pinned or []) + list(scanned or []):
        try:
            key = str(Path(path).resolve())
        except OSError:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        merged.append(Path(path))
    return merged


def resolve_repo_paths(repo_paths=None, timeout=None):
    """
    Build the fleet list: GIT_REPO_PATHS (pinned) ∪ home scan, minus blacklist.

    - Pinned paths are always included first (even without a recent commit).
    - Scan adds any other home repos with a commit in the last GIT_SCAN_DAYS,
      or any repo that is currently dirty (uncommitted changes/stash/etc.)
      regardless of commit age.
    - GIT_REPO_BLACKLIST drops matches by basename or path (always applied).
    - Discovery is cached for GIT_SCAN_TTL_SECONDS (default 300).

    When repo_paths is passed explicitly (tests), that list is used as-is after
    blacklisting — no scan merge.
    """
    rules = parse_blacklist()
    if repo_paths is not None:
        return apply_blacklist(list(repo_paths), rules)

    pinned = parse_repo_paths()
    scanned = discover_scanned_repos(timeout=timeout)
    return apply_blacklist(merge_repo_paths(pinned, scanned), rules)


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


def porcelain_v2_path(line):
    """Return the worktree path from a porcelain v2 entry, or None."""
    if not line:
        return None
    if line.startswith("? ") or line.startswith("! "):
        path = line[2:].strip()
        return path or None
    if line[0] not in {"1", "2", "u"} or len(line) < 3 or line[1] != " ":
        return None
    rest = line[2:]
    if line.startswith("2 "):
        rest = rest.split("\t", 1)[0]
    parts = rest.split()
    return parts[-1] if parts else None


def newest_worktree_mtime(repo_path, rel_paths):
    """Newest mtime among relative worktree paths, or 0 if none are readable."""
    latest = 0
    try:
        repo_root = Path(repo_path).resolve()
    except OSError:
        repo_root = Path(repo_path)
    for rel in rel_paths or []:
        if not rel or rel.startswith("/"):
            continue
        candidate = repo_root / rel
        try:
            resolved = candidate.resolve()
            resolved.relative_to(repo_root)
            mtime = int(resolved.stat().st_mtime)
        except (OSError, ValueError):
            continue
        if mtime > latest:
            latest = mtime
    return latest


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
    changed_paths = []

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
            path = porcelain_v2_path(line)
            if path:
                changed_paths.append(path)
            continue
        if line.startswith("! "):
            continue
        if line.startswith("u "):
            conflicted += 1
            # Unmerged entries also often show in worktree; count conflict only.
            path = porcelain_v2_path(line)
            if path:
                changed_paths.append(path)
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
            path = porcelain_v2_path(line)
            if path:
                changed_paths.append(path)

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
        "changed_paths": changed_paths,
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
        "lastModifiedEpoch": 0,
    }

    try:
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
    except OSError as error:
        base["error"] = str(error)[:160] or "cannot access repository"
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
        base["lastModifiedEpoch"] = last_commit_epoch(repo_path, timeout=timeout) or 0
        return base

    changed_paths = parsed.pop("changed_paths", [])
    commit_epoch = last_commit_epoch(repo_path, timeout=timeout) or 0
    worktree_epoch = newest_worktree_mtime(repo_path, changed_paths)
    last_modified = max(commit_epoch, worktree_epoch)

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
        "lastModifiedEpoch": last_modified,
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
            -int(repo.get("lastModifiedEpoch") or 0),
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


def parse_github_remote(url):
    """Return (owner, repo) for a GitHub remote URL, else None."""
    if not url:
        return None
    match = GITHUB_REMOTE_RE.search(str(url).strip())
    if not match:
        return None
    owner = match.group("owner").strip()
    repo = match.group("repo").strip()
    repo = re.sub(r"\.git$", "", repo, flags=re.IGNORECASE).rstrip("/")
    if not owner or not repo or owner == "github.com":
        return None
    return owner, repo


def github_remote_for_repo(repo_path, timeout):
    """Resolve the first GitHub remote on a local repo, preferring origin."""
    path = Path(repo_path)
    timeout = max(0.4, min(float(timeout), 1.5))
    candidates = ["origin"]
    try:
        remotes = [
            line.strip()
            for line in run_git(path, ["remote"], timeout=timeout).splitlines()
            if line.strip()
        ]
    except (RuntimeError, TimeoutError):
        remotes = []
    for name in remotes:
        if name not in candidates:
            candidates.append(name)

    for name in candidates:
        try:
            url = run_git(path, ["remote", "get-url", name], timeout=timeout).strip()
        except (RuntimeError, TimeoutError):
            continue
        parsed = parse_github_remote(url)
        if parsed:
            return parsed
    return None


def classify_workflow_runs(runs):
    """Map GitHub workflow runs to a pip state: run, fail, ok, or empty."""
    if not runs:
        return ""
    for run in runs:
        if not isinstance(run, dict):
            continue
        if (run.get("status") or "") in ACTIONS_ACTIVE_STATUSES:
            return "run"
    for run in runs:
        if not isinstance(run, dict):
            continue
        if (run.get("status") or "") != "completed":
            continue
        conclusion = run.get("conclusion") or ""
        if conclusion in ACTIONS_FAIL_CONCLUSIONS:
            return "fail"
        if conclusion in ACTIONS_OK_CONCLUSIONS:
            return "ok"
    return ""


def gh_run_list_command(owner, repo, branch, limit=10):
    command = [
        "gh",
        "run",
        "list",
        "--repo",
        f"{owner}/{repo}",
        "--limit",
        str(limit),
        "--json",
        "status,conclusion,headBranch,name",
    ]
    if branch and branch not in {"DETACHED", "HEAD"}:
        command.extend(["--branch", branch])
    return command


def parse_gh_run_list(stdout):
    payload = json.loads(stdout or "[]")
    return payload if isinstance(payload, list) else []


def _gh_run_list(owner, repo, branch, timeout):
    command = gh_run_list_command(owner, repo, branch)
    env = os.environ.copy()
    env["GH_PROMPT_DISABLED"] = "1"
    env["GH_NO_UPDATE_NOTIFIER"] = "1"
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except FileNotFoundError as error:
        raise RuntimeError("gh executable not found on PATH") from error
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(f"gh timed out after {timeout}s") from error

    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout or "").strip()
        lowered = stderr.lower()
        if "404" in lowered or "not found" in lowered or "could not resolve" in lowered:
            return []
        raise RuntimeError(stderr or f"gh exited {completed.returncode}")
    return parse_gh_run_list(completed.stdout)


def fetch_workflow_runs(owner, repo, branch, timeout):
    """List recent Actions via the authenticated `gh` CLI."""
    runs = _gh_run_list(owner, repo, branch, timeout)
    if runs:
        return runs
    # Feature branches often have no workflow yet; fall back to the repo's latest.
    if branch and branch not in {"DETACHED", "HEAD"}:
        return _gh_run_list(owner, repo, "", timeout)
    return []


def load_actions_cache():
    try:
        payload = json.loads(ACTIONS_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"repos": {}}
    repos = payload.get("repos")
    if not isinstance(repos, dict):
        return {"repos": {}}
    return payload


def save_actions_cache(entries):
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "updatedAtEpoch": int(datetime.now(timezone.utc).timestamp()),
        "repos": entries,
    }
    atomic_write_json(ACTIONS_CACHE_PATH, payload)


def actions_cache_ttl(actions):
    if actions == "run":
        return env_int("GIT_ACTIONS_RUNNING_TTL_SECONDS", DEFAULT_ACTIONS_RUNNING_TTL_SECONDS)
    if actions in {"fail", "ok"}:
        return env_int("GIT_ACTIONS_TTL_SECONDS", DEFAULT_ACTIONS_TTL_SECONDS)
    return env_int("GIT_ACTIONS_EMPTY_TTL_SECONDS", DEFAULT_ACTIONS_EMPTY_TTL_SECONDS)


def actions_cache_fresh(cached, branch, now):
    if not cached:
        return False
    if (cached.get("branch") or "") != (branch or ""):
        return False
    fetched = int(cached.get("fetchedAtEpoch") or 0)
    if fetched <= 0:
        return False
    age = int(now.timestamp()) - fetched
    return age < max(5, actions_cache_ttl(cached.get("actions") or ""))


def _actions_entry(owner, repo_name, branch, actions, now, stale=False):
    return {
        "owner": owner,
        "repo": repo_name,
        "branch": branch,
        "actions": actions,
        "fetchedAt": now.isoformat(),
        "fetchedAtEpoch": int(now.timestamp()),
        "stale": bool(stale),
    }


def refresh_repo_actions(repo, timeout, now, fetch_runs):
    """Fetch Actions for one fleet repo. Returns (path, entry)."""
    path = repo.get("path") or ""
    branch = repo.get("branch") or ""
    empty = _actions_entry("", "", branch, "", now)
    if not path:
        return path, empty
    remote = github_remote_for_repo(path, timeout=min(timeout, 1.5))
    if not remote:
        return path, empty
    owner, repo_name = remote
    try:
        runs = fetch_runs(owner, repo_name, branch, timeout)
        actions = classify_workflow_runs(runs)
        return path, _actions_entry(owner, repo_name, branch, actions, now)
    except (
        OSError,
        TimeoutError,
        RuntimeError,
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        return path, None


def attach_actions(status, now=None, fetch_runs=None):
    """
    Attach a per-repo `actions` pip state (run / fail / ok / "") to fleet rows.

    Uses cache/git-actions-cache.json so the local git poll stays cheap. Running
    repos refresh faster than idle ones. Failures keep the last known pip.
    """
    repos = status.get("repos") or []
    if not env_flag("GIT_ACTIONS_ENABLED", True):
        for repo in repos:
            repo["actions"] = ""
        return status

    now = now or datetime.now(timezone.utc)
    fetch_runs = fetch_runs or fetch_workflow_runs
    timeout = env_float(
        "GIT_ACTIONS_TIMEOUT_SECONDS",
        env_float("GITHUB_TIMEOUT_SECONDS", 6.0),
    )
    timeout = max(1.0, float(timeout))

    cache = load_actions_cache()
    entries = dict(cache.get("repos") or {})
    stale_repos = []

    for repo in repos:
        key = repo.get("path") or ""
        branch = repo.get("branch") or ""
        cached = entries.get(key) or {}
        if actions_cache_fresh(cached, branch, now):
            repo["actions"] = cached.get("actions") or ""
        else:
            stale_repos.append(repo)

    if stale_repos:
        workers = min(6, max(1, len(stale_repos)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(refresh_repo_actions, repo, timeout, now, fetch_runs): repo
                for repo in stale_repos
            }
            for future in as_completed(futures):
                repo = futures[future]
                key = repo.get("path") or ""
                try:
                    path, entry = future.result()
                except Exception as error:
                    log_event(f"actions refresh failed path={key}: {error}")
                    repo["actions"] = (entries.get(key) or {}).get("actions") or ""
                    continue
                if entry is None:
                    cached = entries.get(key) or {}
                    repo["actions"] = cached.get("actions") or ""
                    if cached:
                        cached = dict(cached)
                        cached["stale"] = True
                        entries[key] = cached
                    continue
                entries[path or key] = entry
                repo["actions"] = entry.get("actions") or ""

    keep = {repo.get("path") for repo in repos if repo.get("path")}
    entries = {key: value for key, value in entries.items() if key in keep}
    try:
        save_actions_cache(entries)
    except OSError as error:
        log_event(f"actions cache write failed: {error}")

    counts = {"run": 0, "fail": 0, "ok": 0, "empty": 0}
    for repo in repos:
        state = repo.get("actions") or ""
        counts[state if state in counts else "empty"] += 1
    log_event(
        "actions "
        f"run={counts['run']} fail={counts['fail']} ok={counts['ok']} "
        f"empty={counts['empty']} fetched={len(stale_repos)} cached={len(repos) - len(stale_repos)}"
    )
    return status


def collect_status(repo_paths=None, timeout=None, hide_clean=None, max_repos=None):
    common.load_env()
    if timeout is None:
        timeout = env_float("GIT_TIMEOUT_SECONDS", 2.0)
    timeout = max(0.5, float(timeout))
    if repo_paths is None:
        repo_paths = resolve_repo_paths(timeout=timeout)
    if hide_clean is None:
        hide_clean = env_flag("GIT_HIDE_CLEAN", False)
    if max_repos is None:
        max_repos = env_int("GIT_MAX_REPOS", 6)
    if max_repos < 1:
        max_repos = 6

    include_stash = env_flag("GIT_INCLUDE_STASH", True)

    if not repo_paths:
        days = env_int("GIT_SCAN_DAYS", DEFAULT_SCAN_DAYS)
        return {
            "ok": False,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "updatedAtEpoch": int(datetime.now(timezone.utc).timestamp()),
            "error": (
                f"No git repos with commits in the last {days} days under $HOME "
                "(pin with GIT_REPO_PATHS or loosen GIT_REPO_BLACKLIST / GIT_SCAN_DAYS)"
            ),
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
    # Keep a pool wider than the panel: limit_repos() drops idle rows once the
    # Actions pips land, and the survivors below the cut backfill the panel.
    pool = max_repos * ACTIONS_PROBE_ROWS_MULTIPLIER
    if len(repos) > pool:
        repos = repos[:pool]

    summary = build_summary(repos)
    now = datetime.now(timezone.utc)
    return {
        "ok": True,
        "updatedAt": now.isoformat(),
        "updatedAtEpoch": int(now.timestamp()),
        "error": "",
        "maxRepos": max_repos,
        "summary": summary,
        "repos": repos,
    }


def is_idle_row(repo, default_branches=None):
    """A default-branch clean repo with no Actions run isn't worth a panel row.

    Feature / non-default branches stay even when clean: being off main is the
    signal. Default names come from GIT_DEFAULT_BRANCHES (main, master).
    """
    if repo.get("state") != "clean":
        return False
    if repo.get("actions"):
        return False
    branches = default_branches if default_branches is not None else parse_default_branches()
    branch = (repo.get("branch") or "").strip()
    return branch in branches


def limit_repos(status, max_repos=None, actions_ready=True):
    """
    Trim the fleet down to the rows the panel actually shows.

    Runs after attach_actions(): idle repos (clean on a default branch *and*
    without an Actions pip) drop out first so the GIT_MAX_REPOS cap is spent
    on rows that say something. Off-default branches stay even when clean.
    When the pips are unavailable — Actions disabled, or the whole enrichment
    pass failed — nothing is hidden, since every row would look idle.
    """
    repos = status.get("repos") or []
    if max_repos is None:
        max_repos = int(status.get("maxRepos") or 0) or env_int("GIT_MAX_REPOS", 6)
    if max_repos < 1:
        max_repos = 6

    if actions_ready and env_flag("GIT_ACTIONS_ENABLED", True):
        default_branches = parse_default_branches()
        kept = [repo for repo in repos if not is_idle_row(repo, default_branches)]
        hidden = len(repos) - len(kept)
        if hidden:
            log_event(f"hid idle rows without actions hidden={hidden}")
        if hidden and not kept and status.get("ok"):
            # Otherwise the empty panel blames discovery ("set GIT_REPO_PATHS").
            status["error"] = "Every repo is clean with no Actions runs"
        repos = kept

    status["repos"] = repos[:max_repos]
    status["summary"] = build_summary(status["repos"])
    return status


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

    actions_ready = True
    try:
        status = attach_actions(status)
    except Exception as error:
        log_event(f"actions attach failed: {error}")
        actions_ready = False
        for repo in status.get("repos") or []:
            repo.setdefault("actions", "")

    status = limit_repos(status, actions_ready=actions_ready)
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

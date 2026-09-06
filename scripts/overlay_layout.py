#!/usr/bin/env python3
"""Plan bounded Conky regions in monitor-local pixels, without fetching data."""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ("linear", "rate-limit-panel", "minecraft", "github", "weather",
        "resource-monitor", "billing", "git", "sessions")


def cache_object(name, cache_dir):
    try:
        value = json.loads((cache_dir / name).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def repo_height(repo):
    """Mirror git-status-renderer: a settled repository collapses to one line.

    Anything not clean, and any repository whose Actions run failed or is still
    going, keeps the two-line row with its badge.
    """
    if not repo.get("ok") or (repo.get("state") or "error") != "clean":
        return 44
    return 44 if repo.get("actions") in ("fail", "run") else 26


def cache_counts(cache_dir):
    cards = cache_object("linear-cards.json", cache_dir).get("cards", [])
    cards = [c for c in cards if isinstance(c, dict) and c.get("title")]
    if any(c.get("dueToday") and not c.get("done") for c in cards):
        cards = [c for c in cards if any(c.get(k) for k in
                 ("done", "dueToday", "competitionUpcoming", "backlogDueSoon"))]
    accounts = 0
    for provider in ("codex", "claude", "cursor", "gemini", "grok", "commandcode"):
        try:
            accounts += sum(line.startswith("account\t") for line in
                            (cache_dir / f"{provider}-usage-render.tsv").read_text().splitlines())
        except OSError:
            pass
    sessions = cache_object("sessions.json", cache_dir)
    repos = [r for r in cache_object("git-status.json", cache_dir).get("repos") or []
             if isinstance(r, dict)]
    return {"cards": len(cards), "accounts": accounts,
            "repos": len(repos), "repo_heights": [repo_height(r) for r in repos],
            "sessions": len(sessions.get("devices") or []) + len(sessions.get("sessions") or []),
            "providers": len(cache_object("billing-usage.json", cache_dir).get("providers") or [])}


def plan(width, height, top=40, counts=None, env=None):
    """Size each region to its records, then spend the remainder on its rail."""
    counts, env = counts or {}, os.environ if env is None else env
    margin, gutter = 16, 24
    available = height - top - margin
    left = 304 if width >= 1600 else 248
    right = 400 if width >= 1600 else 360
    center = width - 2 * margin - left - right - 2 * gutter
    center_x, right_x = margin + left + gutter, width - margin - right

    # Center: quota rows sit at the bottom, the calendar above them, and the
    # task grid takes what is left. Quota rows are 18px wide-layout rows, 40px
    # two-column rows, or 76px stacks.
    row = 18 if center >= 880 else 40 if center >= 760 else 76
    quota_limit = int(available * (0.55 if available >= 900 else 0.44))
    quota_rows = max(1, min(counts.get("accounts", 0) or 1, quota_limit // row))
    quota_h = max(100, quota_rows * row)
    github = env.get("GITHUB_OVERLAY_ENABLED", "1") != "0"
    github_h = 128 if available >= 900 else 112
    quota_y = height - 4 - quota_h
    github_y = quota_y - 12 - github_h
    # A task row reserves 124px so a three-line title wraps without clipping.
    task_bottom = github_y - 12 if github else quota_y - 12
    task_h = max(124, task_bottom - top)
    quota_gutter = 12
    quota_x = margin + left + quota_gutter
    quota_w = width - margin - right - quota_gutter - quota_x

    # Left rail: repositories at the top, sessions pinned to the bottom left,
    # with Minecraft pinned below sessions to the foot when enabled.
    # A disabled Minecraft panel keeps a valid rectangle; only its reservation
    # in the rail collapses, so the launcher can enable it without replanning.
    minecraft = env.get("MINECRAFT_OVERLAY_ENABLED", "1") != "0"
    minecraft_h = 100
    minecraft_foot = minecraft_h + gutter if minecraft else 0
    # Session records are two lines on a 44px pitch; repository rows vary,
    # since a settled one collapses to a single line, so the panel is sized to
    # the records the cache actually holds.
    git_limit = min(456, available * 0.45 - (76 if minecraft else 0))
    repo_heights = counts.get("repo_heights") or [44] * (counts.get("repos", 0) or 1)
    git_used = 0
    for pitch in repo_heights:
        if git_used + pitch > git_limit - 16:
            break
        git_used += pitch
    git_h = max(100, 16 + git_used)
    max_sessions_available = height - margin - minecraft_foot - (top + git_h + gutter)
    sessions_limit = min(456, max(100, max_sessions_available))
    session_rows = max(1, min(counts.get("sessions", 0) or 1, int((sessions_limit - 16) // 44)))
    sessions_h = max(100, 16 + session_rows * 44)
    sessions_bottom = height - margin - minecraft_foot
    sessions_y = sessions_bottom - sessions_h

    # Right rail: resource readings, the budget map, then weather and training.
    # Four readings are a two-column grid of 116px cells with 16px gaps.
    resource_h = 248
    # The map keeps the guide's projection ratio.
    map_h = round(2 * 94 * 0.82 * min(right - 32, 720) / 305 + 32)
    billing_y = top + resource_h + 12
    billing_h = map_h
    weather_y = billing_y + billing_h + 12
    weather_h = max(160, height - margin - weather_y)
    windows = {
        "linear": [center_x, top, center, task_h],
        "rate-limit-panel": [quota_x, quota_y, quota_w, quota_h],
        "github": [center_x, github_y, center, github_h],
        "git": [margin, top, left, git_h],
        "sessions": [margin, sessions_y, left, sessions_h],
        "minecraft": [margin, height - margin - minecraft_h, left, minecraft_h],
        "resource-monitor": [right_x, top, right, resource_h],
        "billing": [right_x, billing_y, right, billing_h],
        "weather": [right_x, weather_y, right, weather_h],
    }
    # Existing positional overrides retain their edge semantics even though
    # every generated window now uses explicit top-left coordinates.
    for key, prefix, right_edge, bottom_edge in (
        ("git", "GIT", False, False), ("sessions", "SESSIONS", False, True),
        ("minecraft", "MINECRAFT", False, True), ("github", "GITHUB", False, True),
        ("weather", "WEATHER", True, True), ("billing", "BILLING", True, False),
        ("resource-monitor", "RESOURCE_MONITOR", True, False),
        ("rate-limit-panel", "RATE_LIMIT_PANEL", False, True),
    ):
        rect = windows[key]
        for axis, edge, dimension in ((0, right_edge, width), (1, bottom_edge, height)):
            raw = env.get(f"{prefix}_GAP_{'X' if axis == 0 else 'Y'}", "")
            if raw.strip():
                offset = int(raw)
                rect[axis] = dimension - offset - rect[axis + 2] if edge else offset
    return windows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--top", type=int, default=40)
    args = parser.parse_args()
    windows = plan(args.width, args.height, args.top, cache_counts(ROOT / "cache"))
    for key in KEYS:
        rect = windows[key]
        if any(v <= 0 for v in rect[2:]):
            raise ValueError(f"monitor too small for {key}: {rect}")
        print(key, *(int(v) for v in rect), sep="\t")


if __name__ == "__main__":
    main()

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


def cache_counts(cache_dir):
    cards = cache_object("linear-cards.json", cache_dir).get("cards", [])
    cards = [c for c in cards if isinstance(c, dict) and c.get("title")]
    if any(c.get("dueToday") and not c.get("done") for c in cards):
        cards = [c for c in cards if any(c.get(k) for k in
                 ("done", "dueToday", "competitionUpcoming", "backlogDueSoon"))]
    accounts = 0
    for provider in ("codex", "claude", "cursor", "gemini", "grok", "opencode", "commandcode"):
        try:
            accounts += sum(line.startswith("account\t") for line in
                            (cache_dir / f"{provider}-usage-render.tsv").read_text().splitlines())
        except OSError:
            pass
    sessions = cache_object("sessions.json", cache_dir)
    return {"cards": len(cards), "accounts": accounts,
            "repos": len(cache_object("git-status.json", cache_dir).get("repos") or []),
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
    # task grid takes what is left. Quota rows are 24px wide-layout rows, 40px
    # two-column rows, or 76px stacks.
    row = 24 if center >= 880 else 40 if center >= 760 else 76
    quota_limit = int(available * (0.55 if available >= 900 else 0.44))
    quota_rows = max(1, min(counts.get("accounts", 0) or 1, (quota_limit - 16) // row))
    quota_h = max(112, 16 + quota_rows * row)
    github_h = 128 if available >= 900 else 112
    quota_y = height - margin - quota_h
    github_y = quota_y - 12 - github_h
    # A task row reserves 124px so a three-line title wraps without clipping.
    task_h = max(124, github_y - 12 - top)

    # Left rail: repositories above sessions, with Minecraft pinned to the foot.
    # A disabled Minecraft panel keeps a valid rectangle; only its reservation
    # in the rail collapses, so the launcher can enable it without replanning.
    minecraft = env.get("MINECRAFT_OVERLAY_ENABLED", "1") != "0"
    minecraft_h = 100
    # Repository and session records are two lines on a 44px pitch.
    git_limit = min(456, available * 0.45 - (76 if minecraft else 0))
    repo_rows = max(1, min(counts.get("repos", 0) or 1, int((git_limit - 16) // 44)))
    git_h = max(100, 16 + repo_rows * 44)
    sessions_y = top + git_h + gutter
    sessions_h = max(100, height - margin - sessions_y - (minecraft_h + gutter if minecraft else 0))

    # Right rail: resource readings, the budget map, then weather and training.
    # Four readings are a two-column grid of 116px cells with 16px gaps.
    resource_h = 248
    # The map keeps the guide's projection ratio; provider summary rows are 18px.
    map_h = round(2 * 94 * 0.82 * min(right - 32, 720) / 305 + 32)
    billing_y = top + resource_h + 12
    billing_space = height - margin - billing_y - 12 - (320 if available >= 900 else 160)
    provider_rows = max(1, min(counts.get("providers", 0) or 5, (billing_space - map_h - 16) // 18))
    billing_h = map_h + 16 + provider_rows * 18
    weather_y = billing_y + billing_h + 12
    weather_h = max(160, height - margin - weather_y)
    windows = {
        "linear": [center_x, top, center, task_h],
        "rate-limit-panel": [center_x, quota_y, center, quota_h],
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

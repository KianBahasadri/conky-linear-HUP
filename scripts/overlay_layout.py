#!/usr/bin/env python3
"""Plan bounded Conky regions in monitor-local pixels, without fetching data."""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = ("linear", "rate-limit-panel", "minecraft", "github", "weather", "thermometer",
        "resource-monitor", "billing", "git", "sessions")
BOTTOM_ROW_HEIGHT = 112


def cache_object(name, cache_dir):
    try:
        value = json.loads((cache_dir / name).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def enabled(env, key):
    return env.get(key, "1").lower() not in {"0", "false", "no", "off", "disabled"}


def cache_counts(cache_dir):
    cards = cache_object("linear-cards.json", cache_dir).get("cards", [])
    cards = [c for c in cards if isinstance(c, dict) and c.get("title")]
    if any(c.get("dueToday") and not c.get("done") for c in cards):
        cards = [c for c in cards if any(c.get(k) for k in
                 ("done", "dueToday", "competitionUpcoming", "backlogDueSoon"))]
    accounts = 0
    gemini_pro = 0
    for provider in ("codex", "cursor", "gemini"):
        try:
            for line in (cache_dir / f"{provider}-usage-render.tsv").read_text().splitlines():
                if not line.startswith("account\t"):
                    continue
                accounts += 1
        except OSError:
            pass
    sessions = cache_object("sessions.json", cache_dir)
    return {"cards": len(cards), "accounts": accounts, "gemini_pro": gemini_pro,
            "sessions": len(sessions.get("devices") or []) + len(sessions.get("sessions") or []),
            "providers": len(cache_object("billing-usage.json", cache_dir).get("providers") or [])}


def plan(width, height, top=40, counts=None, env=None):
    """Size each region to its records, then spend the remainder on its rail."""
    counts, env = counts or {}, os.environ if env is None else env
    margin, gutter = 8, 24
    available = height - top - margin
    left = 316 if width >= 1600 else 260
    right = 400 if width >= 1600 else 360
    gutter_left = 12
    center = width - 2 * margin - left - right - gutter_left - gutter
    center_x, right_x = margin + left + gutter_left, width - margin - right

    # Right rail: two rows of compact arc gauges, with four column positions per row.
    resource_h = 176
    right_top_clearance = top + resource_h + 12 + 204 + 12

    # Center: quota rows sit at the bottom, the calendar above them, and the
    # task grid takes what is left. Wide displays keep a fixed quota band
    # alongside the billing map; the renderer fits and pages its two columns.
    row = 16 if center >= 880 else 40 if center >= 760 else 76
    is_wide = width >= 1600
    account_count = counts.get("accounts", 0) or 1
    centered_w = width - 2 * center_x
    two_col = is_wide and centered_w >= 1200
    max_quota_available = height - margin - right_top_clearance
    quota_limit = min(int(available * (0.55 if available >= 900 else 0.44)), max_quota_available)
    quota_rows = max(1, min(account_count, quota_limit // row))
    stacked_extra = 6 * counts.get("gemini_pro", 0) if row <= 16 else 0
    quota_h = BOTTOM_ROW_HEIGHT if two_col else max(100, quota_rows * row + stacked_extra)
    github = env.get("GITHUB_OVERLAY_ENABLED", "1") != "0"
    github_h = 128 if available >= 900 else 112
    quota_y = height - margin - quota_h
    github_y = quota_y - 12 - github_h
    # A task row reserves 124px so a three-line title wraps without clipping.
    task_bottom = github_y - 12 if github else quota_y - 12
    task_h = max(124, task_bottom - top)
    if two_col:
        # Centered on the monitor: x stays at the center column's left edge and
        # the width leaves equal margins on both sides.
        quota_w = centered_w
        quota_x = center_x
    elif not is_wide:
        # Narrow monitors need the full center width for quota windows and
        # countdowns. Keep the vertical reservation so neighboring panels stay
        # put; the renderer anchors its compact rows within this region.
        quota_w = center
        quota_x = center_x
    else:
        quota_w = center - 240
        quota_x = center_x + (center - quota_w) // 2

    # Bottom right: a compact 112px-deep map with clearance for its markers.
    billing_w = left
    billing_x = width - margin - billing_w
    billing_clearance = 8 if billing_w < 480 else 16
    billing_h = BOTTOM_ROW_HEIGHT + 2 * billing_clearance
    billing_y = height - margin - billing_h

    # Left rail: sessions join repositories at the top. The standalone sessions
    # rectangle is used only when Git is disabled. The thermometer and compact
    # personal-metrics (running + weight) sit side-by-side at the bottom left,
    # between the left monitor edge and the rate-limit panel, above Minecraft
    # when enabled, with room reserved in the list.
    # A disabled Minecraft panel keeps a valid rectangle; only its reservation
    # in the rail collapses, so the launcher can enable it without replanning.
    minecraft = env.get("MINECRAFT_OVERLAY_ENABLED", "1") != "0"
    minecraft_h = 100
    minecraft_foot = minecraft_h + gutter if minecraft else 0
    thermometer_w = 120
    thermometer_h = BOTTOM_ROW_HEIGHT + 12
    thermometer_y = height - margin - minecraft_foot - thermometer_h
    thermometer_foot = thermometer_h + gutter if enabled(env, "WEATHER_OVERLAY_ENABLED") else 0
    left_foot = minecraft_foot + thermometer_foot
    weather_x = margin + thermometer_w + 8
    weather_w = left - thermometer_w - 8
    weather_h = BOTTOM_ROW_HEIGHT
    weather_y = thermometer_y + thermometer_h - weather_h
    # Keep the transparent rail available for future cache updates. Cairo
    # measures and fits the live list, independently of its size at launch.
    git_top = int((env.get("GIT_GAP_Y") or "").strip() or top)
    git_h = max(100, height - git_top - margin - left_foot)
    max_sessions_available = available - left_foot
    sessions_limit = min(456, max(100, max_sessions_available))
    session_rows = max(1, min(counts.get("sessions", 0) or 1, int((sessions_limit - 16) // 44)))
    sessions_h = max(100, 16 + session_rows * 44)
    sessions_bottom = height - margin - left_foot
    sessions_y = sessions_bottom - sessions_h
    windows = {
        "linear": [center_x, top, center, task_h],
        "rate-limit-panel": [quota_x, quota_y, quota_w, quota_h],
        "github": [center_x, github_y, center, github_h],
        "git": [margin, top, left, git_h],
        "sessions": [margin, sessions_y, left, sessions_h],
        "minecraft": [margin, height - margin - minecraft_h, left, minecraft_h],
        "resource-monitor": [right_x, top, right, resource_h],
        "billing": [billing_x, billing_y, billing_w, billing_h],
        "weather": [weather_x, weather_y, weather_w, weather_h],
        "thermometer": [margin, thermometer_y, thermometer_w, thermometer_h],
    }
    # Existing positional overrides retain their edge semantics even though
    # every generated window now uses explicit top-left coordinates.
    for key, prefix, right_edge, bottom_edge in (
        ("git", "GIT", False, False), ("sessions", "SESSIONS", False, True),
        ("minecraft", "MINECRAFT", False, True), ("github", "GITHUB", False, True),
        ("weather", "WEATHER", True, True), ("billing", "BILLING", True, True),
        ("resource-monitor", "RESOURCE_MONITOR", True, False),
        ("rate-limit-panel", "RATE_LIMIT_PANEL", False, True),
    ):
        rect = windows[key]
        for axis, edge, dimension in ((0, right_edge, width), (1, bottom_edge, height)):
            raw = env.get(f"{prefix}_GAP_{'X' if axis == 0 else 'Y'}", "")
            if raw.strip():
                offset = int(raw)
                rect[axis] = dimension - offset - rect[axis + 2] if edge else offset
    # Align the visible near edge; the marker clearance extends below it.
    if not env.get("BILLING_GAP_Y", "").strip():
        quota = windows["rate-limit-panel"]
        windows["billing"][1] = quota[1] + quota[3] + billing_clearance - billing_h
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

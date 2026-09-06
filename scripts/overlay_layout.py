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
        return 36
    return 36 if repo.get("actions") in ("fail", "run") else 18


def enabled(env, key):
    return env.get(key, "1").lower() not in {"0", "false", "no", "off", "disabled"}


def merged_heights(repos, state, width, env):
    """Conservative natural heights; Cairo measures and packs the actual rows.

    Count only real sessions, resolve all attached device names, and keep
    unmatched sessions and inbound logins in the allocation. The mono estimate
    rounds up so a width-dependent extra line has room at launch.
    """
    def names(value):
        return {name.strip() for name in (value or "").split(",") if name.strip()}

    def path_of(value):
        value = os.path.expanduser(value or "")
        return os.path.normpath(value) if os.path.isabs(value) else None

    def age(seconds):
        if seconds is None or seconds < 0:
            return "unknown"
        for unit, scale in (("d", 86400), ("h", 3600), ("m", 60)):
            if seconds >= scale:
                return f"{int(seconds // scale)}{unit}"
        return f"{int(seconds)}s"

    default_branches = set(env.get("GIT_DEFAULT_BRANCHES", "main,master").replace(":", ",").replace(" ", ",").split(","))
    groups = [{"repo": repo, "sessions": []} for repo in repos]
    residual = []
    sessions = [s for s in state.get("sessions") or [] if isinstance(s, dict)] if state.get("ok") else []
    for session in sessions:
        path = path_of(session.get("path"))
        matches, named = [], []
        for group in groups:
            repo = group["repo"]
            repo_path = path_of(repo.get("path"))
            if path and repo_path:
                if path == repo_path or path.startswith(repo_path + "/"):
                    matches.append((len(repo_path), group))
            elif session.get("repo") and repo.get("name") == session["repo"]:
                named.append(group)
        target = max(matches, key=lambda item: item[0])[1] if matches else named[0] if len(named) == 1 else None
        if target is None:
            residual.append({"repo": {}, "sessions": [session]})
        else:
            target["sessions"].append(session)

    def group_height(group):
        repo, records = group["repo"], group["sessions"]
        live = [s for s in records if s.get("windows", 0) > 0]
        devices = set().union(*(names(s.get("attached")) for s in live))
        cv = next((s for s in records if s.get("codeviewRunning")),
                  next((s for s in records if s.get("codeviewPresent")), None))
        known_ages = [s.get("idleSeconds", -1) for s in live if s.get("idleSeconds", -1) is not None and s.get("idleSeconds", -1) >= 0]
        session_text = ((f"{len(live)}× " if len(live) > 1 else "") + age(min(known_ages) if known_ages else -1)) if live else ""
        cv_text = age(cv.get("codeviewIndexAgeSeconds", -1)) if cv and cv.get("codeviewRunning") else ""
        cv_width = (len(cv_text) * 7.2 + 18 if cv_text else 14) if cv else 0
        dev_count = min(len(devices), 3)
        dev_width = (dev_count * 14 + (dev_count - 1) * 4 + (len(f"+{len(devices) - 3}") * 7.2 + 4 if len(devices) > 3 else 0)) if dev_count > 0 else 0
        parts = (1 if cv_width > 0 else 0) + (1 if dev_width > 0 else 0) + (1 if session_text else 0)
        presence = (len(session_text) * 7.2 if session_text else 0) + cv_width + dev_width + (max(0, parts - 1) * 6)
        pitch = repo_height(repo) if repo else 18
        branch = repo.get("branch", "") if pitch >= 36 or repo.get("branch") not in default_branches else ""
        available = width
        if (presence > available * 0.5
                or (branch and min(width * 0.5, available - 96) - presence - (8 if presence else 0) < 48)):
            pitch = 36
        tokens = [prefix + str(repo.get(key)) for key, prefix in
                  (("staged", "S"), ("modified", "M"), ("untracked", "U"), ("conflicted", "C"),
                   ("ahead", "ahead "), ("behind", "behind "), ("stash", "stash ")) if repo.get(key, 0) > 0]
        counts_width = len("  ".join(tokens)) * 7.2
        if pitch >= 36:
            below = presence > 0 and (presence > width * 0.46 or counts_width + presence + (48 if branch else 0) + 24 > available)
            detail_width = available - (presence + 12 if presence and not below else 0)
            if len(tokens) > 1 and counts_width + (48 if branch else 0) + 12 > detail_width:
                line, lines = "", 1
                for token in tokens:
                    candidate = (line + "  " if line else "") + token
                    if line and len(candidate) * 7.2 > available:
                        lines += 1
                        line = token
                    else:
                        line = candidate
                pitch += 18 * lines
                below = presence > 0
            if below:
                pitch += 18
        return pitch

    heights = [group_height(group) for group in groups]
    active = {s.get("name") for s in sessions if s.get("windows", 0) > 0}
    logins = [d for d in state.get("devices") or [] if isinstance(d, dict)
              and (d.get("state") == "alert" or not names(d.get("session")) & active)] if state.get("ok") else []
    extra = [18 if d.get("state") == "alert" else 36 for d in logins]
    extra += [group_height(group) for group in residual]
    if heights and extra:
        extra[0] += 8
    if not state.get("ok"):
        extra.append(36)
    return heights + extra


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
            "repo_records": repos, "session_state": sessions,
            "sessions": len(sessions.get("devices") or []) + len(sessions.get("sessions") or []),
            "providers": len(cache_object("billing-usage.json", cache_dir).get("providers") or [])}


def plan(width, height, top=40, counts=None, env=None):
    """Size each region to its records, then spend the remainder on its rail."""
    counts, env = counts or {}, os.environ if env is None else env
    margin, gutter = 16, 24
    available = height - top - margin
    left = 316 if width >= 1600 else 260
    right = 400 if width >= 1600 else 360
    gutter_left = 12
    center = width - 2 * margin - left - right - gutter_left - gutter
    center_x, right_x = margin + left + gutter_left, width - margin - right

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

    # Left rail: sessions join repositories at the top. The standalone sessions
    # rectangle is used only when Git is disabled. Minecraft remains at the foot.
    # A disabled Minecraft panel keeps a valid rectangle; only its reservation
    # in the rail collapses, so the launcher can enable it without replanning.
    minecraft = env.get("MINECRAFT_OVERLAY_ENABLED", "1") != "0"
    minecraft_h = 100
    minecraft_foot = minecraft_h + gutter if minecraft else 0
    merged = enabled(env, "GIT_OVERLAY_ENABLED") and enabled(env, "SESSIONS_OVERLAY_ENABLED")
    git_limit = available - minecraft_foot
    repo_heights = counts.get("repo_heights") or [36] * (counts.get("repos", 0) or 1)
    if merged:
        if "repo_records" in counts:
            repo_heights = merged_heights(counts["repo_records"], counts["session_state"], left, env) or [36]
        else:
            repo_heights = repo_heights + [36] * counts.get("sessions", 0)
    git_used = 0
    for pitch in repo_heights:
        if git_used + pitch > git_limit - 16:
            break
        git_used += pitch
    git_h = max(100, 16 + git_used)
    max_sessions_available = available - minecraft_foot
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

import itertools
import json

import pytest

import overlay_layout


@pytest.mark.parametrize("size", [(1280, 720), (1366, 768), (1920, 1080), (2560, 1440)])
@pytest.mark.parametrize("minecraft", [False, True])
@pytest.mark.parametrize("github", [False, True])
@pytest.mark.parametrize("count", [0, 1, 30, 150])
@pytest.mark.parametrize("git,sessions", [(True, True), (True, False), (False, True)])
def test_planned_windows_fit_without_overlap_under_changing_record_counts(size, minecraft, github, count, git, sessions):
    width, height = size
    counts = dict.fromkeys(("cards", "accounts", "repos", "sessions", "providers"), count)
    windows = overlay_layout.plan(width, height, 40, counts, {
        "MINECRAFT_OVERLAY_ENABLED": str(int(minecraft)),
        "GITHUB_OVERLAY_ENABLED": str(int(github)),
        "GIT_OVERLAY_ENABLED": str(int(git)),
        "SESSIONS_OVERLAY_ENABLED": str(int(sessions)),
    })
    if git or not sessions:
        windows.pop("sessions")
    if not git:
        windows.pop("git")
    if not minecraft:
        windows.pop("minecraft")
    if not github:
        windows.pop("github")
    for name, (x, y, w, h) in windows.items():
        assert w >= 240 and h >= 100, name
        assert 0 <= x <= width - w, name
        assert 0 <= y <= height - h, name
    for (name_a, a), (name_b, b) in itertools.combinations(windows.items(), 2):
        assert (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
                or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]), (name_a, name_b)


def test_rate_limit_panel_shares_the_task_grid_left_edge_and_is_narrower():
    windows = overlay_layout.plan(1920, 1080, 40, {"accounts": 8}, {})
    linear = windows["linear"]
    quota = windows["rate-limit-panel"]
    assert quota[0] == linear[0]
    assert quota[2] == linear[2] - 96


def test_explicit_position_overrides_keep_their_original_edge_semantics():
    windows = overlay_layout.plan(1920, 1080, 40, {}, {
        "WEATHER_GAP_X": "20", "WEATHER_GAP_Y": "24", "GIT_GAP_Y": "48",
        "GITHUB_GAP_X": "320", "GITHUB_GAP_Y": "100", "SESSIONS_GAP_X": "-4",
    })
    assert windows["weather"][0] + windows["weather"][2] == 1900
    assert windows["weather"][1] + windows["weather"][3] == 1056
    assert windows["git"][1] == 48
    assert windows["github"][0] == 320
    assert windows["github"][1] + windows["github"][3] == 980
    assert windows["sessions"][0] == -4


def test_cache_counts_follow_linear_urgency_filter_and_keep_empty_account_rows(tmp_path):
    (tmp_path / "linear-cards.json").write_text('''{"cards":[
        {"title":"today","dueToday":true}, {"title":"hidden"},
        {"title":"competition","competitionUpcoming":true},
        {"title":"completed","done":true}]}''')
    (tmp_path / "codex-usage-render.tsv").write_text(
        "meta\tok\t0\naccount\tbroken\tplus\t0\t0\tUnauthorized\t0\n")
    counts = overlay_layout.cache_counts(tmp_path)
    assert counts["cards"] == 3
    assert counts["accounts"] == 1
    assert counts["sessions"] == 0


def test_merged_allocation_counts_joined_sessions_once_and_keeps_residuals(tmp_path):
    repos = [{"name": name, "path": "/work/" + name, "ok": True,
              "state": "clean", "actions": "ok", "branch": "main"}
             for name in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot")]
    repos[0].update(state="dirty", modified=11, untracked=1, branch="checkpoint/long-branch")
    sessions = {"ok": True, "devices": [{"name": "laptop", "glyph": "laptop", "session": "edit", "state": "live"}],
                "sessions": [
                    {"name": "edit", "repo": "bravo", "path": "/work/bravo/src", "windows": 1,
                     "attached": "laptop", "idleSeconds": 79, "codeviewPresent": True},
                    {"name": "charlie", "repo": "charlie", "path": "/work/charlie", "windows": 0,
                     "codeviewPresent": True},
                ]}
    (tmp_path / "git-status.json").write_text(json.dumps({"ok": True, "repos": repos}))
    (tmp_path / "sessions.json").write_text(json.dumps(sessions))
    counts = overlay_layout.cache_counts(tmp_path)
    plan = overlay_layout.plan(1920, 1080, 40, counts, {})
    assert plan["git"][3] == 142  # one dirty row at 36px + five settled rows at 18px = 126px plus the 16px footer allowance
    sessions["sessions"][0]["attached"] = "laptop, phone"
    sessions["devices"].extend([
        {"name": "phone", "glyph": "phone", "session": "edit", "state": "live"},
        {"name": "unknown", "glyph": "alert", "session": "edit", "state": "alert"},
    ])
    sessions["sessions"].append({"name": "same-name-other-repo", "repo": "bravo", "path": "/other/bravo", "windows": 1})
    heights = overlay_layout.merged_heights(repos, sessions, 248, {})
    assert len(heights) == 8  # six repositories, an attached alert, and a distinct repo session
    assert heights[1] == 18  # attached devices sit horizontally in presence without extra row height
    assert sum(heights) > 126

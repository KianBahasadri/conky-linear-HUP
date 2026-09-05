import itertools

import pytest

import overlay_layout


@pytest.mark.parametrize("size", [(1280, 720), (1366, 768), (1920, 1080), (2560, 1440)])
@pytest.mark.parametrize("minecraft", [False, True])
@pytest.mark.parametrize("github", [False, True])
@pytest.mark.parametrize("count", [0, 1, 30, 150])
def test_planned_windows_fit_without_overlap_under_changing_record_counts(size, minecraft, github, count):
    width, height = size
    counts = dict.fromkeys(("cards", "accounts", "repos", "sessions", "providers"), count)
    windows = overlay_layout.plan(width, height, 40, counts, {
        "MINECRAFT_OVERLAY_ENABLED": str(int(minecraft)),
        "GITHUB_OVERLAY_ENABLED": str(int(github)),
    })
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

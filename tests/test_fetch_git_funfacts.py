import json
from pathlib import Path

import fetch_git_funfacts as funfacts


def test_clamp_text_shortens_long_lines():
    text = "x" * 100
    clamped = funfacts.clamp_text(text, limit=20)
    assert len(clamped) == 20
    assert clamped.endswith("...")


def test_contribution_stats_streak_and_weekday():
    entries = [
        {"date": "2026-01-05", "level": 2},  # Monday
        {"date": "2026-01-06", "level": 0},
        {"date": "2026-01-07", "level": 3},
        {"date": "2026-01-08", "level": 4},
        {"date": "2026-01-09", "level": 1},
        {"date": "2026-01-10", "level": 0},
        {"date": "2026-01-11", "level": 0},
    ]
    stats = funfacts.contribution_stats(entries)
    assert stats["activeDays"] == 4
    assert stats["level4Days"] == 1
    assert stats["bestDay"]["date"] == "2026-01-08"
    assert stats["mostActiveWeekday"] in funfacts.WEEKDAYS
    assert stats["currentDrought"] >= 1


def test_build_facts_includes_fleet_and_account(tmp_path):
    status = {
        "ok": True,
        "summary": {
            "total": 2,
            "dirty": 1,
            "clean": 1,
            "stash": 0,
            "behind": 0,
            "ahead": 0,
            "conflict": 0,
        },
        "repos": [
            {
                "name": "messy",
                "ok": True,
                "path": str(tmp_path / "messy"),
                "branch": "feat/x",
                "upstream": "origin/feat/x",
                "modified": 3,
                "untracked": 1,
                "staged": 0,
            },
            {
                "name": "tidy",
                "ok": True,
                "path": str(tmp_path / "tidy"),
                "branch": "main",
                "upstream": "origin/main",
                "modified": 0,
                "untracked": 0,
                "staged": 0,
            },
        ],
    }
    contributions = {
        "ok": True,
        "contributions": [
            {"date": "2026-03-01", "level": 2},
            {"date": "2026-03-02", "level": 2},
            {"date": "2026-03-03", "level": 0},
        ],
    }
    account = {
        "ok": True,
        "user": {
            "followers": 12,
            "following": 4,
            "publicRepos": 10,
            "publicGists": 1,
            "createdAt": "2020-01-01T00:00:00Z",
            "hireable": False,
        },
        "repos": [
            {
                "name": "cool",
                "private": False,
                "fork": False,
                "archived": False,
                "stargazers": 5,
                "forks": 1,
                "language": "Python",
                "createdAt": "2021-01-01T00:00:00Z",
                "defaultBranch": "main",
            },
            {
                "name": "secret",
                "private": True,
                "fork": False,
                "archived": False,
                "stargazers": 0,
                "forks": 0,
                "language": "Lua",
                "createdAt": "2022-01-01T00:00:00Z",
                "defaultBranch": "master",
            },
        ],
    }
    local_extras = {
        "loc": {"messy": 1200},
        "todos": {"messy": 4},
        "fixes": {"messy": 2},
    }
    pool = funfacts.build_facts(status, contributions, account, local_extras)
    ids = {fact["id"] for fact in pool}
    assert "fleet_size" in ids
    assert "dirtiest" in ids
    assert "followers" in ids
    assert "public_private" in ids
    assert "loc_messy" in ids
    assert "side_quest" in ids
    assert all(len(fact["text"]) <= funfacts.MAX_FACT_CHARS for fact in pool)


def test_pick_fact_keeps_current_until_rotate():
    pool = [
        {"id": "a", "text": "alpha", "weight": 1},
        {"id": "b", "text": "beta", "weight": 1},
    ]
    now = funfacts.now_utc().timestamp()
    previous = {"id": "a", "text": "alpha", "shownAtEpoch": int(now)}
    current, recent, rotated = funfacts.pick_fact(pool, previous, ["a"], rotate_seconds=300)
    assert rotated is False
    assert current["id"] == "a"


def test_pick_fact_rotates_when_window_elapsed():
    pool = [
        {"id": "a", "text": "alpha", "weight": 1},
        {"id": "b", "text": "beta", "weight": 1},
    ]
    previous = {"id": "a", "text": "alpha", "shownAtEpoch": 1}
    current, recent, rotated = funfacts.pick_fact(pool, previous, ["a"], rotate_seconds=300)
    assert rotated is True
    assert current["id"] in {"a", "b"}
    assert current["id"] in recent

import json

import pytest

import fetch_github_contributions as github


def test_parse_contributions_from_html_fixture():
    html = """
    <table>
      <td class="ContributionCalendar-day" data-date="2026-06-02" data-level="2"></td>
      <td class="ContributionCalendar-day" data-date="2026-06-01" data-level="0"></td>
      <td class="ContributionCalendar-day" data-date="2026-06-03" data-level="4"></td>
    </table>
    """

    assert github.parse_contributions(html) == [
        {"date": "2026-06-01", "level": 0, "count": 0},
        {"date": "2026-06-02", "level": 2, "count": 4},
        {"date": "2026-06-03", "level": 4, "count": 8},
    ]


def test_parse_contributions_reads_counts_from_tooltips():
    # The real per-day number is not on the cell; it is in a sibling <tool-tip>
    # joined to it by id. Levels alone are too coarse to extrude.
    html = """
    <table>
      <td id="day-0" class="ContributionCalendar-day" data-date="2026-06-01" data-level="0"></td>
      <td id="day-1" class="ContributionCalendar-day" data-date="2026-06-02" data-level="1"></td>
      <td id="day-2" class="ContributionCalendar-day" data-date="2026-06-03" data-level="4"></td>
    </table>
    <tool-tip for="day-0">No contributions on June 1st.</tool-tip>
    <tool-tip for="day-1">1 contribution on June 2nd.</tool-tip>
    <tool-tip for="day-2">1,204 contributions on June 3rd.</tool-tip>
    """

    assert github.parse_contributions(html) == [
        {"date": "2026-06-01", "level": 0, "count": 0},
        {"date": "2026-06-02", "level": 1, "count": 1},
        {"date": "2026-06-03", "level": 4, "count": 1204},
    ]


def test_parse_contributions_falls_back_to_level_without_a_tooltip():
    html = """
    <table>
      <td id="day-0" class="ContributionCalendar-day" data-date="2026-06-01" data-level="3"></td>
      <td id="day-1" class="ContributionCalendar-day" data-date="2026-06-02" data-level="2"></td>
    </table>
    <tool-tip for="day-1">7 contributions on June 2nd.</tool-tip>
    """

    entries = github.parse_contributions(html)
    assert entries[0] == {"date": "2026-06-01", "level": 3, "count": 6}
    assert entries[1] == {"date": "2026-06-02", "level": 2, "count": 7}


def test_parse_contributions_no_squares_error_path():
    with pytest.raises(ValueError, match="No contribution squares found"):
        github.parse_contributions("<html></html>")


def test_write_error_keeps_last_successful_calendar(monkeypatch, tmp_path):
    path = tmp_path / "github-contributions.json"
    path.write_text(
        json.dumps(
            {
                "ok": True,
                "updatedAt": "2026-08-31T12:00:00+00:00",
                "username": "octocat",
                "contributions": [{"date": "2026-08-31", "level": 2, "count": 4}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(github, "CONTRIBUTIONS_PATH", path)

    github.write_error("network down", username="octocat")

    cached = json.loads(path.read_text(encoding="utf-8"))
    assert cached["ok"] is True
    assert cached["stale"] is True
    assert cached["error"] == "network down"
    assert cached["contributions"][0]["count"] == 4
    assert cached["updatedAt"] == "2026-08-31T12:00:00+00:00"


def test_write_error_does_not_retain_a_different_users_calendar(
    monkeypatch, tmp_path
):
    path = tmp_path / "github-contributions.json"
    path.write_text(
        json.dumps(
            {
                "ok": True,
                "username": "old-user",
                "contributions": [{"date": "2026-08-31", "level": 4, "count": 20}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(github, "CONTRIBUTIONS_PATH", path)

    github.write_error("network down", username="new-user")

    cached = json.loads(path.read_text(encoding="utf-8"))
    assert cached["ok"] is False
    assert cached["stale"] is False
    assert "contributions" not in cached


def test_main_falls_back_to_html_after_malformed_graphql_payload(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(github, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        github, "CONTRIBUTIONS_PATH", tmp_path / "github-contributions.json"
    )
    monkeypatch.setattr(github, "log_event", lambda _message: None)
    monkeypatch.setattr(github.common, "load_env", lambda: None)
    monkeypatch.setattr(github, "github_username", lambda: "octocat")
    monkeypatch.setattr(github, "effective_github_token", lambda: "token")
    monkeypatch.setattr(
        github,
        "fetch_contributions_graphql_extended",
        lambda *_args: (_ for _ in ()).throw(TypeError("missing user object")),
    )
    monkeypatch.setattr(
        github,
        "fetch_contributions",
        lambda _username: (
            '<td class="ContributionCalendar-day" '
            'data-date="2026-08-31" data-level="2"></td>'
        ),
    )

    assert github.main() == 0
    cached = json.loads(github.CONTRIBUTIONS_PATH.read_text(encoding="utf-8"))
    assert cached["contributions"] == [
        {"date": "2026-08-31", "level": 2, "count": 4}
    ]

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

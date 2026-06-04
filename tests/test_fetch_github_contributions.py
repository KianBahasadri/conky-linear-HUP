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
        {"date": "2026-06-01", "level": 0},
        {"date": "2026-06-02", "level": 2},
        {"date": "2026-06-03", "level": 4},
    ]


def test_parse_contributions_no_squares_error_path():
    with pytest.raises(ValueError, match="No contribution squares found"):
        github.parse_contributions("<html></html>")

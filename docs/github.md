# GitHub contributions

The overlay shows a flat daily contribution calendar above AI usage. Weeks
advance left to right and weekdays run top to bottom. Month labels and M/W/F
row labels orient the grid. Cyan intensity encodes GitHub's 0–4 activity levels.
Where the window is wide enough, latest-day and whole-window totals appear as
metrics beside the calendar, using real counts when available; a legacy
level-only cache still draws the grid but shows a dash rather than inventing a
total. A stale cache is labeled with a caution badge, and the calendar gives up
whatever width the metrics and that badge need. Shared styling and placement are
described in the [Desktop design system](design-system.md).

## Data

- `scripts/fetch_github_contributions.py` writes `cache/github-contributions.json`.
- `GITHUB_USERNAME` selects the account (`GH_USERNAME` is also accepted).
  Without either, the fetcher tries `git config github.user` and the remote owner.
- With `GITHUB_TOKEN` or a logged-in `gh`, GraphQL supplies the requested
  history (default 401 days, capped at 730 via `GITHUB_HISTORY_DAYS`). Without
  authentication, the public HTML fallback is capped at 371 days / 53 weeks.
- The HTML scraper joins each cell with its matching tooltip to recover exact
  counts; the cell's level alone is not a count.
- A failed refresh retains the last successful calendar for the same username
  and marks it stale. Switching usernames never reuses another account's data.
- `GITHUB_OVERLAY_ENABLED=0` disables the overlay and its fetch loop. Auth and
  position overrides are listed in [Configuration](configuration.md#github-overlay).

## Earlier studies

The prior 3D projection is preserved in the [contribution skyline study](github-mockups/NOTES.md)
and [contribution city study](github-city-mockups/NOTES.md). The
[rail experiments](github-rail-blob-experiments.md) preserve the older poured-shape exploration.
These are historical studies rather than the current renderer.

## Troubleshooting

GitHub may already show the next UTC date while local time is on the previous
day, and contributions may take up to 24 hours to refresh. For missing commits,
check the repository's default branch and the commit email linked to the account.

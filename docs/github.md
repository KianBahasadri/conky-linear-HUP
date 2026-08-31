# GitHub overlay

A 3D contribution city: the year of squares extruded into one building per day,
standing on a plinth that sits on the [rate limit panel](rate-limit-panel.md)'s
top edge so the two objects read as one stack. Quiet days are houses and shops;
busy days are setback / Chrysler / Empire towers. Cream limestone, lime windows,
gold cornices — no frame and no header. The desktop shows through between the
buildings. The study it came out of is the
[contribution city study](github-city-mockups/NOTES.md); the older green-bar
lattice is in the [contribution skyline study](github-mockups/NOTES.md).

## Data

- `scripts/fetch_github_contributions.py` → `cache/github-contributions.json`.
- `GITHUB_USERNAME` controls the account (`GH_USERNAME` is also accepted). If both are missing, the fetcher tries `git config github.user` and then the GitHub remote owner.
- `GITHUB_TOKEN` is optional. With a token (or a logged-in `gh` — the fetcher calls `gh auth token`) the skyline spans ~401 days via GraphQL so the left edge shows the same calendar month as the right (e.g., both August). Without it, it falls back to the public HTML scrape capped at 371 days / 53 weeks — see [GitHub rail blob experiments](github-rail-blob-experiments.md). `GITHUB_HISTORY_DAYS` tunes that window (default `401`, capped at `730`). The git overlay's Actions pip uses `gh` separately (see [Git status overlay](git.md)).
- Set `GITHUB_OVERLAY_ENABLED=0` to disable the overlay and its refresh loop.

Each day carries a `level` (0-4) **and** a `count`. The level alone cannot be
extruded into anything worth looking at — a typical year is mostly level 1, so
five discrete heights make a flat carpet. The real per-day number is not in the
`<td>`'s attributes; it is in a sibling `<tool-tip>` element joined to the cell
by `id`, which `parse_counts` reads. A cache written before counts existed still
renders: the parser falls back to the level.

## Geometry

- One week steps straight right; one weekday steps right and away. Both basis
  vectors are the same length, so plan-view cells read square.
- The **level** week axis is the point. A straight front edge gives the object a
  baseline, so it can be stood on something instead of floating.
- The plinth (`draw_deck`) fills the whole lattice and extrudes downward. Its
  fascia carries the month scale, because below the front edge is the panel.
- Building height is proportional to `sqrt(count)`. Linear scaling lets a single
  outlier day press every other tower flat into the deck.
- Kind and palette are a hash of the date against height, so neighbouring days
  differ: house, shop, warehouse, walk-up, gothic, office, glass, setback,
  Chrysler, Empire, slab. Tops are volumes (hip, dome, lantern, penthouse, tank),
  not masts.
- Only two of the four walls ever face the camera, so a shaft is three fills
  plus windows on the south face.
- Zero days draw as an outlined plate, which keeps the calendar's shape readable
  through the gaps.

The renderer solves for the week step that makes the plinth exactly the window's
width, then scales the extrusion to whatever vertical room is left. Everything
follows from the window, so placement is entirely the start script's business.

## Placement

Alignment is **`bottom_left`**, and `gap_y` is the distance from the screen
bottom up to the roof line — the renderer draws the plinth flush with the
window's bottom edge.

`scripts/start_conky_overlays.sh` measures the rate limit panel's **drawn frame**
rather than its window. That window is 1548px wide, but the frame it paints is
1000px centred inside it and sits a fixed inset above the window's bottom edge:

- Frame width comes from `fetch_common.rate_limit_panel_frame_width`, and is
  what this window's `minimum_width` is set to.
- Frame height comes from `fetch_common.rate_limit_panel_frame_height`, which
  grows with the account count.
- The frame's bottom is always 12px above its window's bottom, so its top edge
  is `monitor_height - RATE_LIMIT_PANEL_GAP_Y + 4 - 12 - frame_height`.
- The roof line is `GITHUB_ROOF_CLEARANCE` above that, because the provider
  title chips straddle the panel's top edge, riding 9px above it.

With the rate limit panel disabled there is nothing to roof, so the skyline
stands on the screen bottom instead.

`GITHUB_SKYLINE_HEIGHT` is a request, not a promise. The Linear cards grow
downward as tasks land. The start script gives height back until
`GITHUB_LINEAR_CLEARANCE` is free below them, down to a floor of
`GITHUB_SKYLINE_MIN_HEIGHT`. Setting `GITHUB_GAP_X` or `GITHUB_GAP_Y` pins that
axis and opts out of the corresponding measurement.

| Variable | Purpose |
| --- | --- |
| `GITHUB_OVERLAY_ENABLED` | `0` disables overlay + fetch loop |
| `GITHUB_USERNAME` / `GH_USERNAME` | Account to render |
| `GITHUB_TOKEN` | Optional auth for GraphQL (`401`-day) skyline; falls back to `gh` auth token |
| `GITHUB_HISTORY_DAYS` | Skyline window in days when authenticated (default `401`, max `730`) |
| `GITHUB_GAP_X` | Left offset in px; **empty = match the rate limit panel's frame** |
| `GITHUB_GAP_Y` | Bottom offset in px; **empty = sit on the rate limit panel** |
| `GITHUB_SKYLINE_HEIGHT` | Requested window height (default `340`) |
| `GITHUB_SKYLINE_MIN_HEIGHT` | Floor after the Linear clearance is taken out (default `180`) |
| `GITHUB_LINEAR_CLEARANCE` | Gap kept under the Linear cards (default `14`) |
| `GITHUB_ROOF_CLEARANCE` | Gap above the panel's title chips (default `11`) |
| `GITHUB_REFRESH_SECONDS` | Fetch interval (default `1800`) |
| `GITHUB_TIMEOUT_SECONDS` | Request timeout |

See [Configuration](configuration.md) for the full variable table.

## Contribution calendar troubleshooting

- Nothing at the right-hand end of the skyline does not necessarily mean today's commits are missing. GitHub can already be showing the next UTC date while local time is still on the previous day.
- GitHub may take up to 24 hours to refresh the contribution graph. If the expected tower is still missing afterward, confirm that the commits are pushed to the repository's default branch and use an email address linked to the GitHub account.

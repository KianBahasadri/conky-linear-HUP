# GitHub overlay

Transparent left-side contribution rail (year of squares). No chrome — only the calendar column.

## Data

- `scripts/fetch_github_contributions.py` → `cache/github-contributions.json`.
- `GITHUB_USERNAME` controls the account (`GH_USERNAME` is also accepted). If both are missing, the fetcher tries `git config github.user` and then the GitHub remote owner.
- `GITHUB_TOKEN` is optional; used only for authenticated requests to the public contributions endpoint.
- Set `GITHUB_OVERLAY_ENABLED=0` to disable the overlay and its refresh loop.

## Layout and placement

- Alignment is **`top_left`**. The renderer draws the grid from the top of the window; vertical position is entirely `gap_y`.
- When **`GITHUB_GAP_Y` is unset**, `scripts/start_conky_overlays.sh` **auto-centers** the rail in the free band between:
  - the **git status panel** (top), and
  - the **Minecraft panel** (bottom),
  using each monitor’s pixel height from `xrandr --listmonitors`.
- Auto placement estimates panel heights (git footer chip included) so the rail sits in the middle of that band, then subtracts `GITHUB_AUTO_GAP_NUDGE_UP` (default `28`) so it sits slightly high of pure center.
- On the **primary** monitor the git panel is a `normal` window, so GNOME’s top bar pushes it down; the contribution rail is a `desktop` window measured from the top of the screen. Auto-gap adds `GITHUB_AUTO_PRIMARY_GIT_EXTRA` (detected from `_NET_WORKAREA`, typically `32`) to the git-panel bottom and will not nudge the rail back over that inset.
- Set an explicit `GITHUB_GAP_Y` to pin the top of the rail; leave it empty to keep auto-centering.

| Variable | Purpose |
| --- | --- |
| `GITHUB_OVERLAY_ENABLED` | `0` disables overlay + fetch loop |
| `GITHUB_USERNAME` / `GH_USERNAME` | Account to render |
| `GITHUB_TOKEN` | Optional auth for the contributions endpoint |
| `GITHUB_GAP_X` | Horizontal gap from the left edge (default `18`) |
| `GITHUB_GAP_Y` | Top offset in px; **empty = auto-center** between git + Minecraft |
| `GITHUB_REFRESH_SECONDS` | Fetch interval (default `1800`) |
| `GITHUB_TIMEOUT_SECONDS` | Request timeout |
| `GITHUB_AUTO_GIT_PANEL_H` | Estimated git panel height for auto gap (default `300`) |
| `GITHUB_AUTO_MC_PANEL_H` | Estimated Minecraft clearance for auto gap (default `126`) |
| `GITHUB_AUTO_RAIL_H` | Estimated contribution column height (default `590`) |
| `GITHUB_AUTO_GAP_NUDGE_UP` | Pixels to shift auto gap upward (default `28`) |
| `GITHUB_AUTO_PRIMARY_GIT_EXTRA` | Extra git-bottom inset on the primary monitor; empty detects the top bar from `_NET_WORKAREA` (fallback `32`); `0` disables |

See [Configuration](configuration.md) for the full variable table.

## Contribution calendar troubleshooting

- A gray rightmost square does not necessarily mean today's commits are missing. GitHub can already be showing the next UTC date while local time is still on the previous day; hover the squares to confirm their dates.
- GitHub may take up to 24 hours to refresh the contribution graph. If the expected square is still gray afterward, confirm that the commits are pushed to the repository's default branch and use an email address linked to the GitHub account.

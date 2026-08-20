# GitHub overlay

Transparent left-side contribution rail (year of squares). No chrome — only the calendar column.

## Data

- `scripts/fetch_github_contributions.py` → `cache/github-contributions.json`.
- `GITHUB_USERNAME` controls the account (`GH_USERNAME` is also accepted). If both are missing, the fetcher tries `git config github.user` and then the GitHub remote owner.
- `GITHUB_TOKEN` is optional; used only for authenticated requests to the public contributions endpoint. The git overlay's Actions pip uses `gh` instead (see [Git status overlay](git.md)).
- Set `GITHUB_OVERLAY_ENABLED=0` to disable the overlay and its refresh loop.

## Layout and placement

- Alignment is **`top_left`**. When **`GITHUB_GAP_Y` is unset**, `scripts/start_conky_overlays.sh` sizes the rail window to the whole free band on each monitor — from the top of the **git status panel** down to the **Minecraft panel** — using each monitor’s pixel height from `xrandr --listmonitors`.
- The renderer then centers the calendar inside that band on **every draw**, measuring the git panel from the repo rows it is drawing right now (`cache/git-status.json`) plus the footer chip. A row appearing or disappearing moves the rail by half a row, so the gaps above and below the calendar stay equal without restarting Conky. Moves are logged to `cache/conky-github.log`.
- `GITHUB_AUTO_GAP_NUDGE_UP` biases the rail above pure center (default `0`).
- On the **primary** monitor the git panel is a `normal` window, so GNOME’s top bar pushes it down; the contribution rail is a `desktop` window measured from the top of the screen. Auto placement adds `GITHUB_AUTO_PRIMARY_GIT_EXTRA` (detected from `_NET_WORKAREA`, typically `32`) to the git panel’s top edge.
- Set an explicit `GITHUB_GAP_Y` to pin the top of the rail; the calendar then draws at the top of its window and stops following the git panel. Leave it empty to keep auto-centering.
- `update_interval` in `conky/github-overlay.conkyrc` (default `15`) is how fast the rail reacts to a repo row; the contribution fetch stays on `GITHUB_REFRESH_SECONDS`.

| Variable | Purpose |
| --- | --- |
| `GITHUB_OVERLAY_ENABLED` | `0` disables overlay + fetch loop |
| `GITHUB_USERNAME` / `GH_USERNAME` | Account to render |
| `GITHUB_TOKEN` | Optional auth for the contributions endpoint |
| `GITHUB_GAP_X` | Horizontal gap from the left edge (default `18`) |
| `GITHUB_GAP_Y` | Top offset in px; **empty = auto-center** between git + Minecraft |
| `GITHUB_REFRESH_SECONDS` | Fetch interval (default `1800`) |
| `GITHUB_TIMEOUT_SECONDS` | Request timeout |
| `GITHUB_AUTO_MC_PANEL_H` | Minecraft clearance above the screen bottom (default `126`) |
| `GITHUB_AUTO_RAIL_H` | Shortest the rail window may be (default `590`) |
| `GITHUB_AUTO_GAP_NUDGE_UP` | Pixels to bias the centered rail upward (default `0`) |
| `GITHUB_AUTO_PRIMARY_GIT_EXTRA` | Extra git-panel inset on the primary monitor; empty detects the top bar from `_NET_WORKAREA` (fallback `32`); `0` disables |

See [Configuration](configuration.md) for the full variable table.

## Contribution calendar troubleshooting

- A gray rightmost square does not necessarily mean today's commits are missing. GitHub can already be showing the next UTC date while local time is still on the previous day; hover the squares to confirm their dates.
- GitHub may take up to 24 hours to refresh the contribution graph. If the expected square is still gray afterward, confirm that the commits are pushed to the repository's default branch and use an email address linked to the GitHub account.

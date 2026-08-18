# Git status overlay

Top-left fleet panel for local repository health. Each configured repo shows branch, dirty/clean state, staged/modified/untracked/conflict counts, ahead/behind vs upstream, stash count, and a GitHub Actions pip when the remote is on GitHub.

## Data

- `scripts/fetch_git_status.py` builds a fleet list, then runs `git status --porcelain=v2 --branch` (and optional `git stash list`) per path.
- **Fleet list** = `GIT_REPO_PATHS` (pinned, always kept) ∪ home scan (repos with a commit in the last `GIT_SCAN_DAYS` days) − `GIT_REPO_BLACKLIST`.
- Scan root defaults to `$HOME` (`GIT_SCAN_ROOT`); discovery is cached in `cache/git-repo-discovery.json` for `GIT_SCAN_TTL_SECONDS` (default `300`).
- Blacklist matches directory basenames (`dev-box`) or paths (`~/old-project`); path rules also drop repos nested under that directory.
- Status results land in `cache/git-status.json` for the Cairo renderer.
- After the local inspect, each GitHub-remote row is enriched with an `actions` pip (`run` / `fail` / `ok` / empty) via `gh run list` (uses your existing `gh auth` login, including private remotes). If the current branch has no runs, the fetcher falls back to the repo's latest run. Results are cached in `cache/git-actions-cache.json` so the 30s git poll stays local. Running repos refresh every `GIT_ACTIONS_RUNNING_TTL_SECONDS` (default `20`); completed pips every `GIT_ACTIONS_TTL_SECONDS` (default `180`); no-run remotes every `GIT_ACTIONS_EMPTY_TTL_SECONDS` (default `300`). Set `GIT_ACTIONS_ENABLED=0` to skip.
- Repos are sorted by severity: conflict → error → behind → dirty → stash → ahead → clean. Within a tier, higher counts rank first (capped), then last modified (HEAD commit or newest dirty/untracked file), then A–Z by name.
- After sort, only the first `GIT_MAX_REPOS` rows are kept (default **6**).
- Missing pinned paths appear as error rows instead of being skipped.

## Configuration

```bash
GIT_OVERLAY_ENABLED=1
# Always show these, even without a recent commit:
# GIT_REPO_PATHS=~/legacy-tool
# Hide noisy repos from pin + scan:
# GIT_REPO_BLACKLIST=dev-box:~/experiments
# GIT_SCAN_DAYS=14
```

| Variable | Purpose |
| --- | --- |
| `GIT_OVERLAY_ENABLED` | Set to `0` to disable the panel and its fetch loop |
| `GIT_REPO_PATHS` | Optional pin list always included (merged with scan) |
| `GIT_REPO_BLACKLIST` | Basename or path excludes applied after merge |
| `GIT_SCAN_ROOT` | Root directory to scan (default `$HOME`) |
| `GIT_SCAN_DAYS` | Include scanned repos with a commit within this many days (default `14`) |
| `GIT_SCAN_MAX_DEPTH` | Max directory depth under the scan root (default `3`) |
| `GIT_SCAN_TTL_SECONDS` | How long to reuse discovery results (default `300`) |
| `GIT_GAP_X` | Horizontal gap from the left edge (default `12`; avoid `0` on the leftmost monitor under Xwayland) |
| `GIT_GAP_Y` | Vertical gap from the top (default `40`; empty follows Linear’s per-monitor offset) |
| `GIT_REFRESH_SECONDS` | Fetch interval (default `30`) |
| `GIT_TIMEOUT_SECONDS` | Per-repo git command timeout (default `2`) |
| `GIT_MAX_REPOS` | Cap on rows shown after sort (default `6`) |
| `GIT_HIDE_CLEAN` | `1` hides fully clean repos |
| `GIT_INCLUDE_STASH` | `0` skips stash counting |
| `GIT_DEFAULT_BRANCHES` | Branches treated as default for muted styling |
| `GIT_ACTIONS_ENABLED` | `0` disables the per-row Actions pip |
| `GIT_ACTIONS_TTL_SECONDS` | Cache TTL for `ok` / `fail` pips (default `180`) |
| `GIT_ACTIONS_RUNNING_TTL_SECONDS` | Cache TTL while a run is `in_progress` / queued (default `20`) |
| `GIT_ACTIONS_EMPTY_TTL_SECONDS` | Cache TTL when a GitHub repo has no recent runs (default `300`) |
| `GIT_ACTIONS_TIMEOUT_SECONDS` | `gh run list` timeout (falls back to `GITHUB_TIMEOUT_SECONDS`, then `6`) |

See [Configuration](configuration.md) for the full variable table.

## Reading the panel

- Frame is repo rows only (no header bar). Under the box, bottom-right: a chip with the GitHub mark and git-status refresh age.
- Each row is two lines: repo name on top, branch underneath. Left accent bar encodes state; clean rows are dimmed.
- Compact badges sit on the **branch line** (right side): `S` staged, `M` modified, `U` untracked, `C` conflicted, plus tags like `STASH×n` / `CONFLICT`.
- Sync: `^n` ahead, `vn` behind when nonzero.
- A 7px pip on the **name line** (far right) is GitHub Actions for the current branch: amber = running/queued, red = last completed failed, green = last completed succeeded. No pip if the remote is not GitHub or there is no recent run. Pips stay full-brightness on dimmed clean rows.

# Git status overlay

Top-left fleet panel for local repository health. Each configured repo shows branch, dirty/clean state, staged/modified/untracked/conflict counts, ahead/behind vs upstream, stash count, and a GitHub Actions status when the remote is on GitHub.

## Data

- `scripts/fetch_git_status.py` builds a fleet list, then runs `git status --porcelain=v2 --branch` (and optional `git stash list`) per path.
- **Fleet list** = `GIT_REPO_PATHS` (pinned, always kept) ∪ home scan (repos with a commit in the last `GIT_SCAN_DAYS` days) − `GIT_REPO_BLACKLIST`.
- Scan root defaults to `$HOME` (`GIT_SCAN_ROOT`); discovery is cached in `cache/git-repo-discovery.json` for `GIT_SCAN_TTL_SECONDS` (default `300`).
- Blacklist matches directory basenames (`dev-box`) or paths (`~/old-project`); path rules also drop repos nested under that directory.
- Status results land in `cache/git-status.json` for the Cairo renderer.
- After the local inspect, each GitHub-remote row is enriched with an `actions` status (`run` / `fail` / `ok` / empty) via `gh run list` (uses your existing `gh auth` login, including private remotes). If the current branch has no runs, the fetcher falls back to the repo's latest run. Results are cached in `cache/git-actions-cache.json` so the 30s git poll stays local. Running repos refresh every `GIT_ACTIONS_RUNNING_TTL_SECONDS` (default `20`); completed states every `GIT_ACTIONS_TTL_SECONDS` (default `180`); no-run remotes every `GIT_ACTIONS_EMPTY_TTL_SECONDS` (default `300`). Set `GIT_ACTIONS_ENABLED=0` to skip.
- Clean repos on a default branch (`main` / `master`, or `GIT_DEFAULT_BRANCHES`) with no Actions status are hidden: a green row on the usual branch that has no workflow run says nothing the panel needs a line for. Rows with any status (`run` / `fail` / `ok`) stay, as does anything not clean, and any repo whose current branch is not a default. Nothing is hidden when the states are unavailable (`GIT_ACTIONS_ENABLED=0`, or the whole Actions pass failed), since every row would look idle.
- Repos are sorted by severity: conflict → error → behind → dirty → stash → ahead → clean. Within a tier, higher counts rank first (capped), then last modified (HEAD commit or newest dirty/untracked file), then A–Z by name.
- After sort, Actions statuss are resolved for up to 3× `GIT_MAX_REPOS` rows, the idle rows above drop out, and only the first `GIT_MAX_REPOS` survivors are kept (default **6**). Hidden rows do not spend a slot — repos below the cut move up to fill the panel.
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
| `GIT_GAP_X` | Horizontal gap from the left edge (empty uses coordinated layout) |
| `GIT_GAP_Y` | Vertical gap from the top (empty aligns with Tasks) |
| `GIT_REFRESH_SECONDS` | Fetch interval (default `30`) |
| `GIT_TIMEOUT_SECONDS` | Per-repo git command timeout (default `2`) |
| `GIT_MAX_REPOS` | Cap on rows shown after sort and the idle-row filter (default `6`) |
| `GIT_HIDE_CLEAN` | `1` hides fully clean repos |
| `GIT_INCLUDE_STASH` | `0` skips stash counting |
| `GIT_DEFAULT_BRANCHES` | Branches treated as default for idle-row hiding and for suppressing the branch on a settled row (`main`, `master`) |
| `GIT_ACTIONS_ENABLED` | `0` disables the per-row Actions status |
| `GIT_ACTIONS_TTL_SECONDS` | Cache TTL for `ok` / `fail` states (default `180`) |
| `GIT_ACTIONS_RUNNING_TTL_SECONDS` | Cache TTL while a run is `in_progress` / queued (default `20`) |
| `GIT_ACTIONS_EMPTY_TTL_SECONDS` | Cache TTL when a GitHub repo has no recent runs (default `300`) |
| `GIT_ACTIONS_TIMEOUT_SECONDS` | `gh run list` timeout (falls back to `GITHUB_TIMEOUT_SECONDS`, then `6`) |

See [Configuration](configuration.md) for the full variable table.

## Reading the panel

A settled repository — clean, with no failed or running workflow — is a single
muted line carrying its name, plus its branch at the right edge when that
branch is not a default (`GIT_DEFAULT_BRANCHES`). Session and CodeView presence
are described in [Sessions in the repository panel](sessions.md).

Any other repository starts with two lines: its name with one badge, then the branch
and nonzero counts (`S` staged, `M` modified, `U` untracked, `C` conflicted,
ahead, behind, and stash). Failed scans retain their error text in place of the
counts.

The badge names the worst thing true of the repository, in the fetcher's own
severity order with the Actions result folded in — `Error`, `Conflicts`,
`CI failed`, `Detached`, `Behind n`, `Dirty`, `Stashed`, `Ahead n`, then
`CI running`. A passing run draws no badge at all: it is the baseline, and
spending a green pill on it buries the rows that need attention. A stale cache
is named in the panel's footer line.

The list uses the [Desktop design system](design-system.md). The renderer keeps
the fetcher's severity order and rotates excess rows within its bounded region.
Because rows differ in height, the launcher sizes the window to the records the
cache holds, so a fleet that is mostly settled leaves the rail shorter.

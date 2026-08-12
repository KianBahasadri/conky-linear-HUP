# Git status overlay

Top-left fleet panel for local repository health. Each configured repo shows branch, dirty/clean state, staged/modified/untracked/conflict counts, ahead/behind vs upstream, and stash count.

## Data

- `scripts/fetch_git_status.py` runs `git status --porcelain=v2 --branch` (and optional `git stash list`) per path in `GIT_REPO_PATHS`.
- Results land in `cache/git-status.json` for the Cairo renderer.
- Repos are sorted by severity: conflict → error → behind → dirty → stash → ahead → clean.
- Missing paths and non-git directories appear as error rows instead of being skipped.

## Configuration

Set a colon-separated path list in `.env` (commas and newlines are also accepted; `~` is expanded):

```bash
GIT_OVERLAY_ENABLED=1
GIT_REPO_PATHS=~/linux-state-search:~/hangout-automator
```

| Variable | Purpose |
| --- | --- |
| `GIT_OVERLAY_ENABLED` | Set to `0` to disable the panel and its fetch loop |
| `GIT_REPO_PATHS` | Ordered list of local repo paths |
| `GIT_GAP_X` | Horizontal gap from the left edge (default `12`; avoid `0` on the leftmost monitor under Xwayland) |
| `GIT_GAP_Y` | Vertical gap from the top (default `40`; empty follows Linear’s per-monitor offset) |
| `GIT_REFRESH_SECONDS` | Fetch interval (default `30`) |
| `GIT_TIMEOUT_SECONDS` | Per-repo git command timeout (default `2`) |
| `GIT_MAX_REPOS` | Cap on rows shown after sort (default `12`) |
| `GIT_HIDE_CLEAN` | `1` hides fully clean repos |
| `GIT_INCLUDE_STASH` | `0` skips stash counting |
| `GIT_DEFAULT_BRANCHES` | Branches treated as default for muted styling |
| `GIT_FUNFACT_ROTATE_SECONDS` | How long each header joke stays (default `300`) |
| `GIT_FUNFACTS_REFRESH_SECONDS` | Fun-fact fetch loop interval (default `60`) |

See [Configuration](configuration.md) for the full variable table.

## Reading the panel

- Header: GitHub mark, **rotating fun-fact ticker**, and git-status refresh age top-right.
- Fun facts come from `scripts/fetch_git_funfacts.py` → `cache/git-funfacts.json` (local fleet, contribution graph, GitHub account/repos, light LOC/TODO scans). They rotate every `GIT_FUNFACT_ROTATE_SECONDS` (default `300`).
- Each row is two lines: repo name on top, branch underneath. Glyph and left accent encode state; clean rows are dimmed.
- Counts on the right: `S` staged, `M` modified (worktree), `U` untracked, `C` conflicted.
- Sync: `^n` ahead, `vn` behind when nonzero.

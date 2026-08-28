# Maintenance

## Dead-code cleanup

The shipped overlays keep private helpers only when they have a runtime caller. The following implementation-only paths were removed after repository-wide reference checks:

- Fetchers: `read_latest_local_rate_limits` from `scripts/fetch_codex_usage.py`, `parse_contributions_graphql_entries` from `scripts/fetch_github_contributions.py`, and `pace_seconds` from `scripts/fetch_workouts.py`.
- Renderers: the unused Codex account/combined-pace helpers and unrendered `PACE` chip helper from `conky/rate-limit-panel-renderer.lua`; the old Git chip helpers from `conky/git-status-renderer.lua`; `glow_line` from `conky/billing-renderer.lua`; `segment_dist` from `conky/sessions-renderer.lua`; and the resource HUD's unused duration, disk-fraction, text, and bottom-readout-grid helpers from `conky/resource-monitor-renderer.lua`.
- Support code: the unused `sys` import in `fetch_claude_usage.py`, `os` import in `fetch_sessions.py`, `pytest` import in `tests/test_fetch_git_status.py`, unused `math` and color imports in `render_annunciator.py`, the unused `render_variants` path/import in `render_layout_v2.py`, the unused `CURSOR_AUTH_STORE_DIR` constant, `bar_pair_gap`, `content_bottom`, the launcher's redundant `launch_env` wrapper, unused workouts log mapping, and no-op `is_primary` variable.
- Archive cleanup: unused imports in the session mockup renderers and the empty `docs/billing-mockups/claude-design-review.txt` placeholder.

These removals do not remove compatibility handling, public configuration variables, fetcher-owned workout logging, or preserved design-study source and artwork. Current visible behavior is documented in the owning topic files: [Rate limit panel](rate-limit-panel.md), [Configuration](configuration.md), and [Session overlay design study](session-mockups/NOTES.md).

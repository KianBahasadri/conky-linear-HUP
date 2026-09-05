# Maintenance

## Dead-code cleanup

The shipped overlays keep private helpers only when they have a runtime caller. The following implementation-only paths were removed after repository-wide reference checks:

- Fetchers: `read_latest_local_rate_limits` from `scripts/fetch_codex_usage.py`, `parse_contributions_graphql_entries` from `scripts/fetch_github_contributions.py`, and `pace_seconds` from `scripts/fetch_workouts.py`.
- Renderers: the unused Codex account/combined-pace helpers and unrendered `PACE` chip helper from `conky/rate-limit-panel-renderer.lua`; the old Git chip helpers from `conky/git-status-renderer.lua`; `glow_line` from `conky/billing-renderer.lua`; `segment_dist` from `conky/sessions-renderer.lua`; and the resource HUD's unused duration, disk-fraction, text, and bottom-readout-grid helpers from `conky/resource-monitor-renderer.lua`.
- Support code: the unused `sys` import in `fetch_claude_usage.py`, `os` import in `fetch_sessions.py`, `pytest` import in `tests/test_fetch_git_status.py`, unused `math` and color imports in `render_annunciator.py`, the unused `render_variants` path/import in `render_layout_v2.py`, the unused `CURSOR_AUTH_STORE_DIR` constant, `bar_pair_gap`, `content_bottom`, the launcher's redundant `launch_env` wrapper, unused workouts log mapping, and no-op `is_primary` variable.
- Archive cleanup: unused imports in the session mockup renderers and the empty `docs/billing-mockups/claude-design-review.txt` placeholder.

These removals do not remove compatibility handling, public configuration variables, fetcher-owned workout logging, or preserved design-study source and artwork. Current visible behavior is documented in the owning topic files: [Rate limit panel](rate-limit-panel.md), [Configuration](configuration.md), and [Session overlay design study](session-mockups/NOTES.md).

## Renderer cache and loading seams

JSON-backed renderers share one small structural cache reader in `renderer-shared.lua`. It reads direct fields and arrays while respecting nested containers, escaped quotes, and Unicode surrogate pairs; missing or malformed caches still degrade to each overlay's empty/error state. The rate-limit panel retains both the current nested Codex account cache and the older flattened `bars` shape as fallback adapters.

`overlay-entrypoint.lua` registers every Conky hook but loads only the renderer that a window actually invokes. Renderer state and load failures therefore stay local to that overlay instead of every Conky process eagerly instantiating the full renderer set.

## Design-system migration

The former 3D drawing paths, colored frames, glyph marks, and constellation
layout were removed from shipped renderers. The original design studies remain
under `docs/*-mockups/`; they are archives. Unused frame/shading helpers and
resource disk probes were removed with their final drawing callers.

Section headings, table header rows, separator rules, and panel borders were
removed with the second design pass; each window now begins at its content. The
system monitor's load average, interface, and uptime readouts went with them,
because the realtime-monitoring component allows no text beneath its plots, and
its unread core-count, absolute-memory, and interface-name status fields were
removed with their last caller. The billing renderer's exported map-height
helper went the same way once the layout planner derived that height itself.

Legacy height-spacer hooks and fetcher `--print-overlay-height` / quota sizing
CLI helpers still report natural content dimensions for compatibility. Current
Conky templates use the planner's bounded sizes instead. The layout and paging
contract belongs to [Desktop design system](design-system.md).

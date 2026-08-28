# Documentation

- [Getting started](getting-started.md) — start and stop overlays
- [Desktop render](desktop-render.md) — draw every overlay to a PNG without screenshotting
- [Conky windows and input](conky-windows-and-input.md) — overlapping windows, click stacking, and why Conky is not interactive
- [Configuration](configuration.md) — `.env` setup and environment variables
- [Caches](caches.md) — cache files, logs, and fetch intervals
- [Linear overlay](linear.md) — card colors, filtering, and display rules
- [Rate limit panel](rate-limit-panel.md) — quota chips, provider discovery, and pace markers
- [Expired credentials and stale cache](expired-credentials.md) — token refresh and fallback behavior per provider
- [Minecraft overlay](minecraft.md) — server status and PebbleHost integration
- [GitHub overlay](github.md) — 3D contribution skyline stacked on the rate limit panel
- [GitHub rail blob experiments](github-rail-blob-experiments.md) — poured-shape study; reverted to the square calendar
- [Weather and running overlay](weather.md) — current conditions, air quality, and run guidance
- [Workout data source](workout-data-source.md) — how workouts get from the phone to this machine
- [Affine billing map](billing.md) — live provider spend, prepaid runway, and common EOM forecasts
- [Git status overlay](git.md) — local repo fleet (branch, dirty, ahead/behind, Actions pip)
- [Sessions overlay](sessions.md) — tmux sessions and the inbound logins driving them
- [Session overlay design study](session-mockups/NOTES.md) — the concept survey the patch bay was picked from
- [Contribution skyline study](github-mockups/NOTES.md) — the projection study behind the skyline
- [Billing panel design archive](billing-mockups/README.md) — preserved Affine Month Map mockup, alternatives, and Cairo sources
  - [Trajectory concept notes](billing-mockups/trajectory_variants/NOTES.md) — four time-and-cap transformations
  - [Ambient concept notes](billing-mockups/ambient_variants/NOTES.md) — four calm and breach signal systems
  - [Geometric concept notes](billing-mockups/geometric_variants/NOTES.md) — four shape-based budget studies
- [Testing](testing.md) — run the Python test suite
- [Maintenance](maintenance.md) — implementation cleanup and retained compatibility paths

## Layout

Vertical alignment matters for every overlay: columns of labels and values, gauge tops vs Linear cards, and stacked readouts should share x-positions (and matching baselines) whenever they form a visual column. Keep text and displays vertically aligned across rows; do not leave near-miss offsets.

## Notes

- These docs are AI-generated after the fact. They record the implementation accurately, but they are not a statement of the original design intent.
- Information should not be repeated elsewhere. Each topic belongs in exactly one file, with links used when another topic needs it.
- Experiments and dead ends should be preserved in their own topic files rather than mixed into shipped-feature documentation.

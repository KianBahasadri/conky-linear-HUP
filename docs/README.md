# Documentation

- [Getting started](getting-started.md) — start and stop overlays
- [Conky windows and input](conky-windows-and-input.md) — overlapping windows, click stacking, and why Conky is not interactive
- [Configuration](configuration.md) — `.env` setup and environment variables
- [Caches](caches.md) — cache files, logs, and fetch intervals
- [Linear overlay](linear.md) — card colors, filtering, and display rules
- [Rate limit panel](rate-limit-panel.md) — quota chips, provider discovery, and pace markers
- [Expired credentials and stale cache](expired-credentials.md) — token refresh and fallback behavior per provider
- [Minecraft overlay](minecraft.md) — server status and PebbleHost integration
- [GitHub overlay](github.md) — contribution tracker
- [Weather and running overlay](weather.md) — current conditions, air quality, and run guidance
- [Git status overlay](git.md) — local repo fleet (branch, dirty, ahead/behind, Actions pip)
- [Testing](testing.md) — run the Python test suite

## Layout

Vertical alignment matters for every overlay: columns of labels and values, gauge tops vs Linear cards, and stacked readouts should share x-positions (and matching baselines) whenever they form a visual column. Keep text and displays vertically aligned across rows; do not leave near-miss offsets.
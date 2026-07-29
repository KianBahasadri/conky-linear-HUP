# Caches

## Data files

- `cache/linear-cards.json`: Linear cards consumed by the Cairo renderer.
- `cache/codex-usage.json`: full Codex account/window usage for inspection.
- `cache/codex-usage-render.tsv`: renderer-friendly Codex usage consumed by the Cairo renderer.
- `cache/claude-usage.json`: normalized Claude Code account/window usage for inspection.
- `cache/claude-usage-render.tsv`: renderer-friendly Claude Code usage consumed by the Cairo renderer.
- `cache/claude-usage-cache-*.json`: per-account Claude API quota-check cache.
- `cache/cursor-usage.json`: normalized Cursor account/monthly usage for inspection.
- `cache/cursor-usage-render.tsv`: renderer-friendly Cursor usage consumed by the Cairo renderer.
- `cache/gemini-usage.json`: normalized Gemini Antigravity account/model usage for inspection.
- `cache/gemini-usage-render.tsv`: renderer-friendly Gemini usage consumed by the Cairo renderer.
- `cache/gemini-usage-cache-*.json`: last successful Gemini usage per Antigravity profile.
- `cache/grok-usage.json`: normalized Grok Build account/monthly usage for inspection.
- `cache/grok-usage-render.tsv`: renderer-friendly Grok usage consumed by the Cairo renderer.
- `cache/grok-usage-cache-*.json`: last successful Grok usage per account.
- `cache/opencode-usage.json`: normalized OpenCode Go account/window usage for inspection.
- `cache/opencode-usage-render.tsv`: renderer-friendly OpenCode Go usage consumed by the Cairo renderer.
- `cache/opencode-web-cache.json`: last successful OpenCode Go dashboard response used when the dashboard request fails.
- `cache/*-usage-render.tsv.fingerprint`: SHA-256 of the meaningful usage state from the matching render TSV, used by the adaptive rate-limit fetch loops to detect usage changes.
- `cache/*-usage-render.tsv.last_change`: Unix epoch of the last fingerprint change for that fetcher; keeps the short poll interval active for `RATE_LIMIT_RECENT_CHANGE_WINDOW` seconds after any change.
- `cache/minecraft-status.json`: Minecraft Java server status consumed by the Cairo renderer.
- `cache/github-contributions.json`: GitHub contribution squares consumed by the Cairo renderer.
- `cache/weather-status.json`: normalized weather, air quality, and running guidance consumed by the Cairo renderer.

## Logs

- `cache/conky-linear.log`: Linear fetch, launcher, and Linear Conky output.
- `cache/conky-rate-limit-panel.log`: rate limit panel fetch loops and Conky output.
- `cache/conky-minecraft.log`: Minecraft fetch, launcher, and Minecraft Conky output.
- `cache/conky-github.log`: GitHub fetch, launcher, and GitHub Conky output.
- `cache/conky-weather.log`: weather fetch, launcher, and weather Conky output.

## Fetch intervals

- Linear: `60s`
- Codex, Claude, Cursor, Gemini, Grok, OpenCode: adaptive — `RATE_LIMIT_CHANGED_INTERVAL` (default `60s`) while any usage change has been seen in the last `RATE_LIMIT_RECENT_CHANGE_WINDOW` (default `600s`), otherwise `RATE_LIMIT_UNCHANGED_INTERVAL` (default `300s`). Claude also keeps a per-account API cache.
- OpenCode: dashboard response is retained as a stale fallback when the latest request fails
- Minecraft: `60s`
- GitHub: `1800s`
- Weather and air quality: `600s`

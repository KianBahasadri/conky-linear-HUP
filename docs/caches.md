# Caches

## Data files

- `cache/linear-cards.json`: Linear cards consumed by the Cairo renderer. A failed fetch keeps the last successful cards and sets `stale` / `error` instead of blanking the overlay.
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
- `cache/commandcode-usage.json`: normalized Command Code account/window usage for inspection.
- `cache/commandcode-usage-render.tsv`: renderer-friendly Command Code usage consumed by the Cairo renderer.
- `cache/commandcode-usage-cache-*.json`: last successful Command Code usage per account.
- `cache/*-usage-render.tsv.fingerprint`: SHA-256 of the meaningful usage state from the matching render TSV, used by the adaptive rate-limit fetch loops to detect usage changes.
- `cache/*-usage-render.tsv.last_change`: Unix epoch of the last fingerprint change for that fetcher; keeps the short poll interval active for `RATE_LIMIT_RECENT_CHANGE_WINDOW` seconds after any change.
- `cache/minecraft-status.json`: Minecraft Java server status consumed by the Cairo renderer. Includes `lastPlayerSeenAt` / `lastPlayerSeenAtEpoch` and `lastSuccessfulAt` / `lastSuccessfulAtEpoch` for empty-server idle display; last-seen is only trusted across continuous successful polls.
- `cache/github-contributions.json`: GitHub contribution days consumed by the Cairo renderer. Each entry carries the `level` (0-4) that GitHub puts on the cell and the real `count` scraped from its tooltip; the skyline extrudes the count.
- `cache/sessions.json`: inbound logins joined to tmux sessions, consumed by the Cairo renderer. Device names and OS strings come from `tailscale status`; no tailnet account identity is stored.
- `cache/weather-status.json`: normalized weather, air quality, and running guidance consumed by the Cairo renderer.
- `cache/workouts-status.json`: workout summaries parsed from the TCX files in `cache/workouts/` (uploaded from the phone; see [Workout data source](workout-data-source.md)). Consumed by the weather panel's training section: last workout, rolling 7-day totals, and the last 14 workouts' distances for the sparkline bars. Heart rate and cadence are per-workout optionals.
- `cache/git-status.json`: local git fleet status consumed by the Cairo renderer. Each repo may include `actions` (`run` / `fail` / `ok` / empty) for the name-line pip.
- `cache/git-repo-discovery.json`: auto-discovered home repos with recent commits (TTL `GIT_SCAN_TTL_SECONDS`).
- `cache/git-actions-cache.json`: per-path GitHub Actions pip state from `gh run list`; running TTL `GIT_ACTIONS_RUNNING_TTL_SECONDS`, completed TTL `GIT_ACTIONS_TTL_SECONDS`.
- `cache/resource-net-peaks.tsv`: hourly max IN/OUT byte rates from the resource monitor; retained for 7 days and used as the NET sparkline scale.
- `cache/billing-usage.json`: full billing observations, normalized pressures, forecast details, data sources, and per-provider errors.
- `cache/billing-usage-render.tsv`: compact affine-map input consumed by the Lua renderer; it contains no credentials.
- `cache/billing-history.json`: dated observations for every billing provider. Each successful collect upserts that day's pressure (the affine map's past trail). OpenRouter samples also keep total-usage / balance for the burn-rate fallback. Retained from the earlier of month-start and 30 days ago.
- `cache/billing-aws-cache.json`: last successful AWS Cost Explorer and Budgets response; daily cache (TTL `BILLING_AWS_CACHE_TTL_SECONDS`, default `86400s`) to avoid Cost Explorer API query charges.

## Logs

- `cache/conky-linear.log`: Linear fetch, launcher, and Linear Conky output.
- `cache/conky-rate-limit-panel.log`: rate limit panel fetch loops and Conky output.
- `cache/conky-minecraft.log`: Minecraft fetch, launcher, and Minecraft Conky output.
- `cache/conky-github.log`: GitHub fetch, launcher, and GitHub Conky output.
- `cache/conky-weather.log`: weather fetch, launcher, and weather Conky output.
- `cache/conky-workouts.log`: workout summary fetch output.
- `cache/conky-billing.log`: billing provider fetches, launcher placement, fallback notices, and billing Conky output.
- `cache/conky-git.log`: git status fetch, launcher, and git Conky output.
- `cache/conky-sessions.log`: session scans, launcher placement, and sessions Conky output.

## Fetch intervals

- Linear: `60s`
- Codex, Claude, Cursor, Gemini, Grok, OpenCode, Command Code: adaptive — `RATE_LIMIT_CHANGED_INTERVAL` (default `60s`) while any usage change has been seen in the last `RATE_LIMIT_RECENT_CHANGE_WINDOW` (default `600s`), otherwise `RATE_LIMIT_UNCHANGED_INTERVAL` (default `300s`). Claude also keeps a per-account API cache.
- OpenCode: dashboard response is retained as a stale fallback when the latest request fails
- Command Code: last successful usage is retained as a stale fallback when the latest request fails
- Minecraft: `60s`
- GitHub: `1800s`
- Weather and air quality: `600s`
- Workouts: `20s` (override with `WORKOUTS_REFRESH_SECONDS`); local TCX parse, no network
- Billing: `900s` (override with `BILLING_REFRESH_SECONDS`); AWS Cost Explorer is cached daily (`86400s` / `BILLING_AWS_CACHE_TTL_SECONDS`) to avoid per-query API fees on daily-refreshed backend data
- Sessions: `20s` (override with `SESSIONS_REFRESH_SECONDS`)
- Git status: `30s` (override with `GIT_REFRESH_SECONDS`)
- Git Actions pips: on the git fetch; cache `20s` while running, `180s` when completed, `300s` when empty

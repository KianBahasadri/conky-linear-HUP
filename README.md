# Conky Linear + AI Quota Overlay

Desktop Conky widgets for keeping Linear work, Codex, Claude, Cursor, Gemini, Grok, and Pioneer quota pressure, Minecraft server population, and GitHub contributions visible across all monitors.

## Run

```bash
./scripts/start_conky_overlays.sh
./scripts/stop_conky_overlays.sh
```

`start_conky_overlays.sh` kills prior matching overlays, starts fetch loops, and generates one Linear, rate limit panel, Minecraft, and GitHub config per detected monitor.
Each overlay can be disabled with its `*_OVERLAY_ENABLED=0` variable in `.env`.

## Caches

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
- `cache/pioneer-usage.json`: normalized Pioneer account/daily and monthly usage for inspection.
- `cache/pioneer-usage-render.tsv`: renderer-friendly Pioneer usage consumed by the Cairo renderer.
- `cache/minecraft-status.json`: Minecraft Java server status consumed by the Cairo renderer.
- `cache/github-contributions.json`: GitHub contribution squares consumed by the Cairo renderer.
- `cache/conky-linear.log`: Linear fetch, launcher, and Linear Conky output.
- `cache/conky-rate-limit-panel.log`: rate limit panel fetch loops and Conky output.
- `cache/conky-minecraft.log`: Minecraft fetch, launcher, and Minecraft Conky output.
- `cache/conky-github.log`: GitHub fetch, launcher, and GitHub Conky output.
- Fetch loops refresh Linear every `180s`, Codex every `300s`, Claude every `60s` with a per-account API cache, Cursor, Gemini, Grok, and Pioneer every `300s`, Minecraft every `60s`, and GitHub every `1800s`.

## Linear Rules

- Card colors are stateful: green is recently completed, red is due today, cyan is normal active work.
- Non-red, non-green cards show their due date when one is available.
- If any unfinished card is due today, non-due unfinished cards are hidden so urgent work dominates the overlay.
- Unfinished issues in the `Competitions` project due in the next 3 days are always shown, with their due date beside the issue id.
- Cancelled and duplicate issues are never shown.
- Recently completed cards remain visible for `LINEAR_DONE_LOOKBACK_HOURS`.
- Set `LINEAR_OVERLAY_ENABLED=0` to disable the Linear overlay and its refresh loop.

## Rate Limit Panel Rules

- The quota panel shows separate `CODEX`, `CLAUDE`, `CURSOR`, `GEMINI`, `GROK`, and `PIONEER` chips. Codex rows use cyan/navy bars; Claude rows use coral/gold bars; Cursor rows use grey bars; Gemini rows use Google blue/green and yellow/red bars; Grok rows use regal purple bars; Pioneer rows use amber/gold daily and monthly bars.
- The selection chevron marks selected auth profiles: Codex rows whose path resolves to `~/.codex/auth.json`, Cursor rows whose path resolves to `~/.config/cursor/auth.json`, Claude rows whose path resolves to `~/.claude/.credentials.json` or whose access token equals the one in that file, Gemini rows matching Antigravity's `current` profile, and Grok rows whose path resolves to `~/.grok/auth.json`. Codex uses a blue chevron, Claude uses orange, Cursor uses grey, Gemini uses Google blue, and Grok uses purple. Token comparison is required for Claude because Claude Code replaces `~/.claude/.credentials.json` with a new regular file on login and on every OAuth refresh, so a symlink there does not survive.
- All account-rotation tooling is stored in `~/.config/clusterfork`.
- Multiple Codex accounts are discovered from `~/.codex/auth.json.*`; `CODEX_AUTH_PATH` forces a single auth file.
- `CODEX_HOME`, `CODEX_SQLITE_HOME`, `CODEX_USAGE_DEGENERATE_RETRIES`, and `CODEX_LOCAL_RATE_LIMIT_MAX_AGE_SECONDS` are advanced overrides for local Codex state discovery and retry behavior. Local session rate limits do not include an account ID, so they are only applied when their reset windows uniquely match one account's API response.
- Multiple Claude accounts are discovered from `~/.claude/.credentials.json.*`; `CLAUDE_CREDENTIALS_PATH` or `CLAUDE_AUTH_PATH` forces a single credentials file.
- Claude account names and selected-account chevrons use the same bright/dim and marker rules as Codex.
- Claude usage is fetched with a direct Anthropic quota-check request and cached per account. `CLAUDE_HOME`, `CLAUDE_USAGE_TTL`, `CLAUDE_PLAN_TYPE`, and `ANTHROPIC_DEFAULT_HAIKU_MODEL` are advanced overrides.
- Multiple Cursor accounts are discovered from `~/.config/cursor/auth.json.*`; `CURSOR_AUTH_PATH` forces a single auth file and `CURSOR_HOME` overrides the config directory.
- Cursor usage is fetched from Cursor's DashboardService. It renders Cursor's monthly `Auto + Composer` and `API` usage pools as the two bars for each account.
- Gemini accounts are discovered from Antigravity's rotation state in `~/.gemini/antigravity-cli/rotate-auth`. The selected profile reads the live GNOME Keyring item `service=gemini username=antigravity`; inactive profiles read `service=rotate-antigravity username=<profile>`.
- Gemini usage is fetched from Antigravity's Code Assist API. Bar 1 averages all active Flash and Pro request quotas, while bar 2 averages every other active model quota. The existing `gemini` and `other` cache labels identify those two groups.
- `GEMINI_ANTIGRAVITY_STATE_DIR` overrides the rotation state directory, `GEMINI_CODE_ASSIST_ENDPOINT` overrides the Antigravity API endpoint, `GEMINI_ANTIGRAVITY_CLI` overrides the `agy` executable, and `GEMINI_AUTH_REFRESH_TIMEOUT_SECONDS` controls the refresh timeout.
- Multiple Grok accounts are discovered from `~/.grok/auth.json.*`; `GROK_AUTH_PATH` forces a single auth file.
- Grok usage is fetched from Grok Build's billing API at `cli-chat-proxy.grok.com/v1/billing?format=credits`. It renders the monthly included-credit pool as one bar per account.
- `GROK_HOME` overrides the Grok config directory and `GROK_CLI_CHAT_PROXY_BASE_URL` overrides the billing API base URL.
- Pioneer usage is fetched with `PIONEER_API_KEY` from `GET /billing/plan-info` for the daily credit pool and team overage settings for the billing-period monthly pool (`current_month_start`, `current_period_usage`).
- `PIONEER_USAGE_LABEL` overrides the Pioneer account label and `PIONEER_MONTHLY_CREDIT_LIMIT` overrides the monthly credit cap when Pioneer does not expose one.

### Expired credentials and stale cache

Each provider fetcher handles expired or rejected credentials differently:

- **Codex** reads `~/.codex/auth.json.*`. On HTTP `401` or `403`, it refreshes the OAuth access token with the auth file's `refresh_token`, writes the new tokens back to that file (mode `0600`), and retries the usage request once. It does not keep a separate stale-cache fallback for auth failures. For paid accounts whose API response is missing future reset windows, it can carry forward still-valid windows from the previous `codex-usage.json` write. It can also apply local session rate limits from Codex rollout logs when those windows uniquely match one account's API response.
- **Claude** reads `~/.claude/.credentials.json.*`. It refreshes expired access tokens with the credentials file's `refresh_token` and writes the new tokens back to that suffixed file (mode `0600`). It never writes `~/.claude/.credentials.json` and never refreshes a grant whose refresh token equals the one in that file, because Claude Code owns that file and a competing refresh would revoke the token Claude Code holds. While waiting for Claude Code to rotate an expired shared grant, the panel serves the last successful quota from `cache/claude-usage-cache-<label>.json`. Between live API calls, fresh cache entries are reused for `CLAUDE_USAGE_TTL` seconds. When stale data is shown, the renderer draws an empty 5h bar labeled `refresh`.
- **Cursor** reads `~/.config/cursor/auth.json.*`. It does not refresh tokens itself; it uses the access token stored in the auth file. On HTTP errors or missing usage buckets, the account row is written with empty bars and no stale-cache fallback. Cursor must refresh `auth.json` on its own.
- **Gemini** reads Antigravity Keyring items discovered from `~/.gemini/antigravity-cli/rotate-auth`. The fetcher never edits Keyring credentials directly. For the selected profile only, HTTP `401` or `403` triggers `agy models`, a re-read of the CLI-refreshed Keyring item, and one retry. Inactive profiles are never refreshed because that would require switching the active account. On any remaining error, the panel serves the last successful quota from `cache/gemini-usage-cache-<label>.json`.
- **Grok** reads `~/.grok/auth.json.*`. It does not refresh tokens itself; Grok CLI refreshes `auth.json` in place while you are actively using Grok. On any fetch error, including HTTP `401` expired credentials, the panel serves the last successful monthly usage from `cache/grok-usage-cache-<label>.json`, falling back to the last good account entry in `grok-usage.json` if no per-account cache exists yet. Usage is unlikely to change while Grok is idle, so stale data is intentional.
- **Pioneer** uses the static `PIONEER_API_KEY` from `.env`, not OAuth tokens. Invalid or missing keys produce an error row with empty bars and no stale-cache fallback.

Claude rotation recovery is separate from ordinary expiry handling. Claude Code rotates the refresh token of the logged-in account, which invalidates a copied credentials file for the same account. The fetcher recovers in two ways, both gated on the live file's profile email matching the email recorded for that account in `cache/claude-usage-cache-<label>.json`:

- It detects a changed default-file token (fingerprint in `cache/claude-default-token.fingerprint`) and copies the rotated tokens into the matching suffixed file within one loop iteration.
- As a backstop, it re-adopts from `~/.claude/.credentials.json` when a refresh fails with `invalid_grant`.
- The account email is recorded automatically after the first successful fetch. A new `~/.claude/.credentials.json.<label>` copy therefore needs one successful fetch before rotation recovery works for it.
- Weekly and 5h pace markers are per paid account: each bar uses that window's own reset time.
- Combined usage is the average weekly `usedPercent` across paid accounts; free accounts are muted and excluded.
- Under pace by at least `10%` shows an amber fast-mode chip, except during the first `10%` of the weekly cycle.
- Over pace by at least `10%` shows a red warning chip, including early in the cycle.
- The pace chip is centered across the whole rate limit panel and uses the combined weekly pace state.
- Set `RATE_LIMIT_PANEL_ENABLED=0` to disable the rate limit panel and its refresh loops.

## Minecraft Rules

- The Minecraft panel uses the Java server status protocol directly over TCP.
- If `PEBBLEHOST_API_KEY` is present, the fetcher also reads PebbleHost resource stats and player names.
- PebbleHost server lookup is automatic from `MINECRAFT_SERVER`; `MINECRAFT_SERVER_HOST` and `MINECRAFT_SERVER_PORT` are the split alternative form, and `PEBBLEHOST_SERVER_ID` can force a specific server identifier.
- The panel is launched in the bottom-left corner by default.
- Set `MINECRAFT_OVERLAY_ENABLED=0` to disable the Minecraft overlay and its refresh loop.
- `MINECRAFT_REFRESH_SECONDS`, `MINECRAFT_GAP_X`, `MINECRAFT_GAP_Y`, `MINECRAFT_STATUS_TIMEOUT_SECONDS`, and `MINECRAFT_PROTOCOL_VERSION` can tune refresh cadence, placement, timeout, and protocol negotiation.

## GitHub Rules

- The GitHub tracker is a transparent left-side rail with only contribution squares.
- `GITHUB_USERNAME` controls the rendered account. `GH_USERNAME` is also accepted. If both are missing, the fetcher tries `git config github.user` and then the GitHub remote owner.
- `GITHUB_TOKEN` is optional and only used for authenticated requests to the public contributions endpoint.
- Set `GITHUB_OVERLAY_ENABLED=0` to disable the GitHub overlay and its refresh loop.
- `GITHUB_REFRESH_SECONDS`, `GITHUB_TIMEOUT_SECONDS`, `GITHUB_GAP_X`, and `GITHUB_GAP_Y` can tune refresh cadence, request timeout, and placement.

## Config

Create `.env` from `.env.example` and fill in the overlays you use:

```bash
# Linear overlay
LINEAR_API_KEY=lin_api_your_key_here
LINEAR_OVERLAY_ENABLED=1
LINEAR_TASK_STATES=Todo,In Progress
LINEAR_TASK_LIMIT=20
LINEAR_COMPETITION_TASK_LIMIT=50
LINEAR_DONE_LOOKBACK_HOURS=18
LINEAR_PRIMARY_MONITOR_INDEX=0
PRIMARY_WAIT_SECONDS=20

# Rate limit panel (Codex + Claude + Cursor + Gemini + Grok + Pioneer)
RATE_LIMIT_PANEL_ENABLED=1
CLAUDE_PLAN_TYPE=pro
# CLAUDE_CREDENTIALS_PATH=/home/you/.claude/.credentials.json
# CLAUDE_HOME=/home/you/.claude
# CLAUDE_USAGE_TTL=300
# CODEX_AUTH_PATH=/home/you/.codex/auth.json
# CODEX_HOME=/home/you/.codex
# CODEX_SQLITE_HOME=/home/you/.codex
# CODEX_USAGE_DEGENERATE_RETRIES=4
# CODEX_LOCAL_RATE_LIMIT_MAX_AGE_SECONDS=21600
# CURSOR_AUTH_PATH=/home/you/.config/cursor/auth.json
# CURSOR_HOME=/home/you/.config/cursor
# GEMINI_ANTIGRAVITY_STATE_DIR=/home/you/.gemini/antigravity-cli/rotate-auth
# GEMINI_CODE_ASSIST_ENDPOINT=https://daily-cloudcode-pa.googleapis.com
# GEMINI_ANTIGRAVITY_CLI=/usr/bin/agy
# GEMINI_AUTH_REFRESH_TIMEOUT_SECONDS=30
# GROK_AUTH_PATH=/home/you/.grok/auth.json
# GROK_HOME=/home/you/.grok
# GROK_CLI_CHAT_PROXY_BASE_URL=https://cli-chat-proxy.grok.com/v1

# Minecraft overlay
MINECRAFT_SERVER=mc.example.com:25565
MINECRAFT_SERVER_HOST=mc.example.com
MINECRAFT_SERVER_PORT=25565
MINECRAFT_SERVER_LABEL=Minecraft
MINECRAFT_OVERLAY_ENABLED=1
MINECRAFT_GAP_X=4
MINECRAFT_GAP_Y=12
MINECRAFT_REFRESH_SECONDS=60
MINECRAFT_STATUS_TIMEOUT_SECONDS=5
MINECRAFT_PROTOCOL_VERSION=-1

# PebbleHost Minecraft stats
PEBBLEHOST_API_KEY=ptlc_your_key_here
# Optional: set this if auto-matching MINECRAFT_SERVER to a PebbleHost allocation fails.
PEBBLEHOST_SERVER_ID=
PEBBLEHOST_API_TIMEOUT_SECONDS=10

# GitHub overlay
GITHUB_USERNAME=your-github-username
# GH_USERNAME=your-github-username
GITHUB_TOKEN=ghp_optional_token_here
GITHUB_OVERLAY_ENABLED=1
GITHUB_GAP_X=18
GITHUB_GAP_Y=0
GITHUB_REFRESH_SECONDS=1800
GITHUB_TIMEOUT_SECONDS=10
```

See **Expired credentials and stale cache** above for how each provider handles token expiry, refresh, and stale data. Codex and Claude refresh OAuth tokens in their own auth files when possible. Cursor and Grok depend on their host apps to refresh local auth files. Gemini refreshes only the selected Antigravity profile through `agy`. Pioneer uses a static API key.

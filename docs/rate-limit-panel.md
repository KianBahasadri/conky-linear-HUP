# Rate limit panel

## Layout and colors

- The quota panel shows separate `CODEX`, `CLAUDE`, `CURSOR`, `GEMINI`, `GROK`, and `OPENCODE` chips. Codex rows use cyan/navy bars; Claude rows use coral/gold bars; Cursor rows use grey bars; Gemini rows use Google blue/green and yellow/red bars; Grok rows use regal purple bars; OpenCode Go rows use amber/gold bars.
- The selection chevron marks selected auth profiles: Codex rows whose path resolves to `~/.local/share/clusterfork-auth/codex/current`, Cursor rows whose path resolves to `~/.local/share/clusterfork-auth/cursor/current`, Claude rows whose path resolves to `~/.claude/.credentials.json` or whose access token equals the one in that file, Gemini rows matching Antigravity's `current` profile, Grok rows whose path resolves to `~/.grok/auth.json`, and the configured OpenCode Go dashboard workspace. Codex uses a blue chevron, Claude uses orange, Cursor uses grey, Gemini uses Google blue, Grok uses purple, and OpenCode Go uses amber. Token comparison is required for Claude because Claude Code replaces `~/.claude/.credentials.json` with a new regular file on login and on every OAuth refresh, so a symlink there does not survive.
- When any account expires, the panel should keep the last cached fill and reset time until that window's reset has already passed; only then should the bar show `refresh`. See [Expired credentials and stale cache](expired-credentials.md).
- All account-rotation tooling is stored in `~/.config/clusterfork`. Shared auth profiles for Codex and Cursor are stored in `~/.local/share/clusterfork-auth/`.

## Codex

- Multiple accounts are discovered from `~/.local/share/clusterfork-auth/codex/auth.json.*`; `CODEX_AUTH_PATH` forces a single auth file. The legacy path `~/.codex/auth.json.*` is used as a fallback when the shared store directory does not exist.
- `CODEX_HOME`, `CODEX_SQLITE_HOME`, `CODEX_AUTH_STORE_DIR`, `CODEX_USAGE_DEGENERATE_RETRIES`, and `CODEX_LOCAL_RATE_LIMIT_MAX_AGE_SECONDS` are advanced overrides for local Codex state discovery and retry behavior. The usage endpoint is authoritative for every account whenever it returns a successful usage response; local session rate limits are discarded rather than allowed to replace fresh endpoint data.
- Recent Codex rollout samples are still logged per session for diagnostics, including their values and matching account candidates. They never override a fresh endpoint response, so an older local sample cannot make a bar move backward.

## Claude

- Multiple accounts are discovered from `~/.claude/.credentials.json.*`; `CLAUDE_CREDENTIALS_PATH` or `CLAUDE_AUTH_PATH` forces a single credentials file.
- Claude account names and selected-account chevrons use the same bright/dim and marker rules as Codex.
- Usage is fetched with a direct Anthropic quota-check request and cached per account. `CLAUDE_HOME`, `CLAUDE_USAGE_TTL`, `CLAUDE_PLAN_TYPE`, and `ANTHROPIC_DEFAULT_HAIKU_MODEL` are advanced overrides.
- Expired-grant display follows the general rule in [Expired credentials and stale cache](expired-credentials.md): cached 5h and weekly fills are held until each window's reset passes. The `refresh` prompt appears per window once its reset is over, or on the whole row when no cached sample exists.

## Cursor

- Multiple accounts are discovered from `~/.local/share/clusterfork-auth/cursor/auth.json.*`; `CURSOR_AUTH_PATH` forces a single auth file and `CURSOR_HOME` overrides the config directory. The legacy path `~/.config/cursor/auth.json.*` is used as a fallback when the shared store directory does not exist.
- `CURSOR_AUTH_STORE_DIR` overrides the shared auth store directory.
- Usage is fetched from Cursor's DashboardService. It renders Cursor's monthly `Auto + Composer` and `API` usage pools as the two bars for each account.

## Gemini

- Accounts are discovered from Antigravity's rotation state in `~/.gemini/antigravity-cli/rotate-auth`. The selected profile reads the live GNOME Keyring item `service=gemini username=antigravity`; inactive profiles read `service=rotate-antigravity username=<profile>`.
- Usage is fetched from Antigravity's Code Assist API. Bar 1 averages all active Flash and Pro request quotas, while bar 2 averages every other active model quota. The existing `gemini` and `other` cache labels identify those two groups.
- `GEMINI_ANTIGRAVITY_STATE_DIR` overrides the rotation state directory, `GEMINI_CODE_ASSIST_ENDPOINT` overrides the Antigravity API endpoint, `GEMINI_ANTIGRAVITY_CLI` overrides the `agy` executable, and `GEMINI_AUTH_REFRESH_TIMEOUT_SECONDS` controls the refresh timeout.

## Grok

- Multiple accounts are discovered from `~/.grok/auth.json.*`; `GROK_AUTH_PATH` forces a single auth file.
- Usage is fetched from Grok Build's billing API at `cli-chat-proxy.grok.com/v1/billing?format=credits`. It renders the monthly included-credit pool as one bar per account.
- `GROK_HOME` overrides the Grok config directory and `GROK_CLI_CHAT_PROXY_BASE_URL` overrides the billing API base URL.

## OpenCode Go

- Usage is fetched from the authenticated OpenCode Go dashboard configured by `OPENCODE_WORKSPACE_URL` (or `OPENCODE_WORKSPACE_ID`). The session cookie is read from Firefox's `cookies.sqlite` for `opencode.ai` (Install default profile, overridable with `OPENCODE_FIREFOX_PROFILE`). Set `OPENCODE_FIREFOX_CONTAINER` to select a named Firefox container; matching is case-insensitive. `OPENCODE_COOKIE` / `OPENCODE_AUTH_COOKIE` remain optional overrides.
- The fetcher uses one dashboard `GET` request per refresh. It never reads OpenCode local auth files or SQLite usage DBs, and never calls the OpenCode API or sends a usage probe.
- The dashboard's rolling/5-hour ($12 limit), weekly ($30 limit), and monthly ($60 limit) cards are parsed and rendered as three bars.
- The `OPENCODE` title chip's percentage uses the monthly window (skipped entirely if the row has none), unlike Codex/Claude which use the weekly window.
- `cache/opencode-web-cache.json` stores the last successful dashboard response. If the next request fails, that response is shown as stale until a fresh dashboard request succeeds. The workspace URL is stored with the cache so data from a different workspace cannot be reused. If no matching cache exists, the panel keeps the OpenCode row with empty bars instead of hiding it. Expired-session display follows the general rule in [Expired credentials and stale cache](expired-credentials.md).
- `OPENCODE_USAGE_LABEL` controls the row label; the dashboard is represented as one selected workspace row rather than local auth profiles.

## Removed providers

- **Pioneer** was removed from the rate limit panel. The Pioneer fetch script, cache files, env vars, and panel chip are no longer used.

## Adaptive polling

- Each rate-limit fetcher (Codex, Claude, Cursor, Gemini, Grok, OpenCode Go) repolls adaptively instead of on a fixed cadence.
- After every fetch the loop fingerprints the meaningful usage state in that fetcher's `cache/*-usage-render.tsv`: the `meta`/`updatedAt` row is dropped, and time-derived bar columns (`resetsAt`, `resetAtEpoch`, `resetAfterSeconds`) are blanked so the fingerprint only changes when actual usage numbers or account/window structure change.
- When the fingerprint changes, the loop records the change time in `cache/*-usage-render.tsv.last_change` and uses `RATE_LIMIT_CHANGED_INTERVAL` (default `60`s). It keeps that short interval for any subsequent poll whose last change is still within `RATE_LIMIT_RECENT_CHANGE_WINDOW` (default `600`s / 10 minutes), even if the latest poll itself was unchanged. After the window expires with no further changes, it backs off to `RATE_LIMIT_UNCHANGED_INTERVAL` (default `300`s).
- The fingerprint is stored as `cache/*-usage-render.tsv.fingerprint`. Both the fingerprint and last-change files persist across overlay restarts; a restart does not force a short interval unless usage actually changed or a prior change is still inside the recent-change window.

## Pace markers

- Weekly and 5h pace markers are per paid account: each bar uses that window's own reset time.
- The orange tick is **expected** usage for on-pace spend: `expected = (windowSeconds - remainingSeconds) / windowSeconds * 100` (elapsed time through the reset window, not `usedPercent`).
- **Visibility (do not change):** hide the tick only while remaining time still equals the full window (`expected <= 0`, nothing elapsed). Show it as soon as any time has elapsed (`expected > 0`), even when that still rounds to 0% or the left edge of the bar. Do not gate on fill percentage, and do not hide based on pixel/rounded display position.
- Combined usage is the average weekly `usedPercent` across paid accounts; free accounts are muted and excluded.
- Under pace by at least `10%` shows an amber fast-mode chip, except during the first `10%` of the weekly cycle.
- Over pace by at least `10%` shows a red warning chip, including early in the cycle.
- The pace chip is centered across the whole rate limit panel and uses the combined weekly pace state.

## Disable

- Set `RATE_LIMIT_PANEL_ENABLED=0` to disable the rate limit panel and its refresh loops.

See [Expired credentials and stale cache](expired-credentials.md) for how each provider handles token expiry and fallback data.

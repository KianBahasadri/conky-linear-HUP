# Rate limit panel

## Layout and colors

- The quota panel shows separate `CODEX`, `CLAUDE`, `CURSOR`, `GEMINI`, `GROK`, and `OPENCODE` chips. Codex rows use cyan/navy bars; Claude rows use coral/gold bars; Cursor rows use grey bars; Gemini rows use Google blue/green and yellow/red bars; Grok rows use regal purple bars; OpenCode Go rows use amber/gold bars.
- The selection chevron marks selected auth profiles: Codex rows whose path resolves to `~/.local/share/clusterfork-auth/codex/current`, Cursor rows whose path resolves to `~/.local/share/clusterfork-auth/cursor/current`, Claude rows whose path resolves to `~/.claude/.credentials.json` or whose access token equals the one in that file, Gemini rows matching Antigravity's `current` profile, Grok rows whose path resolves to `~/.grok/auth.json`, and the configured OpenCode Go dashboard workspace. Codex uses a blue chevron, Claude uses orange, Cursor uses grey, Gemini uses Google blue, Grok uses purple, and OpenCode Go uses amber. Token comparison is required for Claude because Claude Code replaces `~/.claude/.credentials.json` with a new regular file on login and on every OAuth refresh, so a symlink there does not survive.
- All account-rotation tooling is stored in `~/.config/clusterfork`. Shared auth profiles for Codex and Cursor are stored in `~/.local/share/clusterfork-auth/`.

## Codex

- Multiple accounts are discovered from `~/.local/share/clusterfork-auth/codex/auth.json.*`; `CODEX_AUTH_PATH` forces a single auth file. The legacy path `~/.codex/auth.json.*` is used as a fallback when the shared store directory does not exist.
- `CODEX_HOME`, `CODEX_SQLITE_HOME`, `CODEX_AUTH_STORE_DIR`, `CODEX_USAGE_DEGENERATE_RETRIES`, and `CODEX_LOCAL_RATE_LIMIT_MAX_AGE_SECONDS` are advanced overrides for local Codex state discovery and retry behavior. Local session rate limits do not include an account ID, so they are only applied when their reset windows uniquely match one account's API response.

## Claude

- Multiple accounts are discovered from `~/.claude/.credentials.json.*`; `CLAUDE_CREDENTIALS_PATH` or `CLAUDE_AUTH_PATH` forces a single credentials file.
- Claude account names and selected-account chevrons use the same bright/dim and marker rules as Codex.
- Usage is fetched with a direct Anthropic quota-check request and cached per account. `CLAUDE_HOME`, `CLAUDE_USAGE_TTL`, `CLAUDE_PLAN_TYPE`, and `ANTHROPIC_DEFAULT_HAIKU_MODEL` are advanced overrides.

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

- Usage is fetched from the authenticated OpenCode Go dashboard configured by `OPENCODE_WORKSPACE_URL` (or `OPENCODE_WORKSPACE_ID`). The session cookie is read from Firefox's `cookies.sqlite` for `opencode.ai` (Install default profile, overridable with `OPENCODE_FIREFOX_PROFILE`). `OPENCODE_COOKIE` / `OPENCODE_AUTH_COOKIE` remain optional overrides.
- The fetcher uses one dashboard `GET` request per refresh. It never reads OpenCode local auth files or SQLite usage DBs, and never calls the OpenCode API or sends a usage probe.
- The dashboard's rolling/5-hour ($12 limit), weekly ($30 limit), and monthly ($60 limit) cards are parsed and rendered as three bars.
- `cache/opencode-web-cache.json` stores the last successful dashboard response. If the next request fails, that response is shown as stale until a fresh dashboard request succeeds. The workspace URL is stored with the cache so data from a different workspace cannot be reused. If no matching cache exists, the panel keeps the OpenCode row with empty bars instead of hiding it.
- `OPENCODE_USAGE_LABEL` controls the row label; the dashboard is represented as one selected workspace row rather than local auth profiles.

## Removed providers

- **Pioneer** was removed from the rate limit panel. The Pioneer fetch script, cache files, env vars, and panel chip are no longer used.

## Pace markers

- Weekly and 5h pace markers are per paid account: each bar uses that window's own reset time.
- Combined usage is the average weekly `usedPercent` across paid accounts; free accounts are muted and excluded.
- Under pace by at least `10%` shows an amber fast-mode chip, except during the first `10%` of the weekly cycle.
- Over pace by at least `10%` shows a red warning chip, including early in the cycle.
- The pace chip is centered across the whole rate limit panel and uses the combined weekly pace state.

## Disable

- Set `RATE_LIMIT_PANEL_ENABLED=0` to disable the rate limit panel and its refresh loops.

See [Expired credentials and stale cache](expired-credentials.md) for how each provider handles token expiry and fallback data.

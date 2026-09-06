# Rate limit panel

## Display

Each row displays the provider mark (brand logo) on the first row of its group,
followed by the account name and quota windows. Reset countdowns occupy a fixed-width
column flanking the flat observed-data bars on the right, keeping bar lengths uniform.
Two-part labels left-align each quantity in a 3-character field so both numbers
share x-positions across rows (`9h  58m`, `10d 11h`, `17d 1h`) rather than
staggering with digit count.
Pool-distinguishing labels (like `Auto`, `API`, `Reserve`, or Gemini model families) flank
on the left. Standard interval windows (`5h`, `7d`, `Month`) omit the leading label so
bars start directly beside the account name.
Selected profiles use a neutral raised row and a medium-weight account name.
Provider identity does not determine bar color. Shared typography, colors, and
overflow are owned by the [Desktop design system](design-system.md).

- Accounts sort alphabetically within each provider, regardless of plan tier.
- A row without usable windows remains visible with `Retrying:` and its error.
- Full windows do not display a `full` text label; the 100% bar fill and danger color indicate capacity exhaustion, and the account name turns danger color if any of its displayed bars are filled.
- Expired/stale accounts keep their cached fill and reset time until that
  window's absolute reset passes, then show `Refresh`. See
  [Expired credentials and stale cache](expired-credentials.md).
- Reset labels count down (`3h 16m`, `6d 8h`). A window with nothing used and
  no pending reset shows its full span (`5h`, `7d`) and no pace tick.
  `wait` means the countdown ended while usage remains.
- The provider's average pace delta in percent (`%`) sits beside its
  brand logo on the first row of each group, in derived-data color. There is no
  separate summary row and no combined pace value. The vertical tick on each
  eligible bar uses the same derived color.
- Cache refreshes do not resize or reload windows. Startup bounds the list and
  excess rows rotate through the available region.

Selected profiles are resolved by the existing fetchers: shared `current`
profiles for Codex/Cursor, the active Claude credential file or matching access
token, Antigravity's current profile, and active Grok/Command Code auth.
Claude requires token comparison because its
CLI replaces the credential file during refresh.

Account-rotation tooling lives in `~/.config/clusterfork`; shared Codex/Cursor
profiles live in `~/.local/share/clusterfork-auth/`.

## Codex

- Multiple accounts are discovered from `~/.local/share/clusterfork-auth/codex/auth.json.*`; `CODEX_AUTH_PATH` forces a single auth file. The legacy path `~/.codex/auth.json.*` is used as a fallback when the shared store directory does not exist.
- `CODEX_HOME`, `CODEX_SQLITE_HOME`, `CODEX_AUTH_STORE_DIR`, `CODEX_USAGE_DEGENERATE_RETRIES`, and `CODEX_LOCAL_RATE_LIMIT_MAX_AGE_SECONDS` are advanced overrides for local Codex state discovery and retry behavior. The usage endpoint is authoritative for every account whenever it returns a successful usage response; local session rate limits are discarded rather than allowed to replace fresh endpoint data.
- When the account-level limit is reached (`limit_reached` / `allowed`), only the blocking window is pinned to 100%: the one whose reset matches the response's `rate_limit_upsell.reset_at`, or the fullest window when the banner is missing (rollout samples always use the fullest window, since they carry no banner). Other windows keep their reported percentages, so an exhausted 5h window no longer pegs the weekly bar.
- A third `reserve` bar is rendered when `/wham/usage` includes `additional_rate_limits` whose `limit_name` contains `reserve` (today `gpt-reserve`, Luna Reserve). That bucket is a fallback weekly pool, not a refill of the main 5h/weekly windows, so account-level reached/allowed flags never pin it. The bar is labelled `RESERVE` on the bar. Accounts without that extra limit keep two bars.
- Recent Codex rollout samples are still logged per session for diagnostics, including their values and matching account candidates. They never override a fresh endpoint response, so an older local sample cannot make a bar move backward. Local samples only carry 5h and weekly; an existing reserve window is kept beside them rather than dropped.
- The `CODEX` summary's pace percentage uses the weekly window when available and falls back to the 5h window only when weekly is absent (Pro accounts are weighted 20x relative to Plus accounts in the average). Reserve is never the summary's pace source. Free accounts have a single 30-day window.

## Claude

- Multiple accounts are discovered from `~/.claude/.credentials.json.*`; `CLAUDE_CREDENTIALS_PATH` or `CLAUDE_AUTH_PATH` forces a single credentials file.
- Claude selected accounts use the same neutral row treatment as Codex.
- Usage is fetched with a direct Anthropic quota-check request and cached per account. `CLAUDE_HOME`, `CLAUDE_USAGE_TTL`, `CLAUDE_PLAN_TYPE`, and `ANTHROPIC_DEFAULT_HAIKU_MODEL` are advanced overrides.
- Expired-grant display follows the general rule in [Expired credentials and stale cache](expired-credentials.md): cached 5h and weekly fills are held until each window's reset passes. The `refresh` prompt appears per window once its reset is over, or on the whole row when no cached sample exists.

## Cursor

- Multiple accounts are discovered from `~/.local/share/clusterfork-auth/cursor/auth.json.*`; `CURSOR_AUTH_PATH` forces a single auth file and `CURSOR_HOME` overrides the config directory. The legacy path `~/.config/cursor/auth.json.*` is used as a fallback when the shared store directory does not exist.
- `CURSOR_AUTH_STORE_DIR` overrides the shared auth store directory.
- Usage is fetched from Cursor's DashboardService. It renders Cursor's monthly `Auto + Composer` and `API` usage pools as the two bars for each account.
- Free and paid accounts share the same `Auto` and `API` window labels; plan tier still controls pace eligibility.

## Gemini

- Accounts are discovered from Antigravity's rotation state in `~/.gemini/antigravity-cli/rotate-auth`. The selected profile reads the live GNOME Keyring item `service=gemini username=antigravity`; inactive profiles read `service=rotate-antigravity username=<profile>`.
- Usage is fetched from Antigravity's Code Assist API (`retrieveUserQuotaSummary`). Pro accounts render four quota bars: Gemini 5-hour and Gemini weekly (labelled `Gem`), and Other/Claude/GPT 5-hour and Other/Claude/GPT weekly (labelled `Other`). Free accounts render two weekly bars (`Gem` and `Other`). Paid tiers (such as Google AI Pro) are recognized from the account's `paidTier` subscription.
- `GEMINI_ANTIGRAVITY_STATE_DIR` overrides the rotation state directory, `GEMINI_CODE_ASSIST_ENDPOINT` overrides the Antigravity API endpoint, `GEMINI_ANTIGRAVITY_CLI` overrides the `agy` executable, and `GEMINI_AUTH_REFRESH_TIMEOUT_SECONDS` controls the refresh timeout.

## Grok

- Multiple accounts are discovered from `~/.grok/auth.json.*`; `GROK_AUTH_PATH` forces a single auth file.
- Usage is fetched from Grok Build's billing API at `cli-chat-proxy.grok.com/v1/billing?format=credits`. It renders the included-credit pool as one bar per account (7-day cycle labelled `7d` on Build subscriptions, or monthly cycle labelled `Month` on Tier 1).
- `GROK_HOME` overrides the Grok config directory and `GROK_CLI_CHAT_PROXY_BASE_URL` overrides the billing API base URL.

## OpenCode Go

- Usage is fetched from the authenticated OpenCode Go dashboard configured by `OPENCODE_WORKSPACE_URL` (or `OPENCODE_WORKSPACE_ID`). The session cookie is read from Firefox's `cookies.sqlite` for `opencode.ai` (Install default profile, overridable with `OPENCODE_FIREFOX_PROFILE`). Set `OPENCODE_FIREFOX_CONTAINER` to select a named Firefox container; matching is case-insensitive. `OPENCODE_COOKIE` / `OPENCODE_AUTH_COOKIE` remain optional overrides.
- The fetcher uses one dashboard `GET` request per refresh. It never reads OpenCode local auth files or SQLite usage DBs, and never calls the OpenCode API or sends a usage probe.
- The dashboard's rolling/5-hour ($12 limit), weekly ($30 limit), and monthly ($60 limit) cards are parsed and rendered as three bars.
- The `OPENCODE` pace summary's delta uses the monthly window (skipped entirely if the row has none), unlike Codex/Claude which use the weekly window.
- `cache/opencode-web-cache.json` stores the last successful dashboard response. If the next request fails, that response is shown as stale until a fresh dashboard request succeeds. The workspace URL is stored with the cache so data from a different workspace cannot be reused. If no matching cache exists, the panel keeps the OpenCode row with an error message instead of hiding it. Expired-session display follows the general rule in [Expired credentials and stale cache](expired-credentials.md).
- `OPENCODE_USAGE_LABEL` controls the row label; the dashboard is represented as one selected workspace row rather than local auth profiles.

## Command Code

- Multiple accounts are discovered from `~/.commandcode/auth.json.*`; `COMMAND_CODE_AUTH_PATH` forces a single auth file. `COMMAND_CODE_API_KEY` takes precedence over local auth files, matching the CLI.
- Usage is fetched from Command Code's Studio API: `GET /alpha/whoami`, `GET /alpha/billing/credits`, `GET /alpha/billing/subscriptions`, and `GET /alpha/usage/summary`. Auth is a bearer API key from `~/.commandcode/auth.json` (written by `cmd login`) or `COMMAND_CODE_API_KEY`.
- It renders the rolling 5-hour and weekly credit windows plus the monthly included-credit pool as three bars. Window caps and remaining monthly credits come from `/alpha/billing/credits`; the monthly reset comes from the subscription period. The `CMD` pace summary's delta uses the monthly window.
- `COMMAND_CODE_HOME` overrides the config directory, `COMMANDCODE_API_URL` overrides the API base URL (`https://api.commandcode.ai`), and `COMMAND_CODE_USAGE_LABEL` labels the env-key account.
- On fetch errors, the panel serves the last successful usage from `cache/commandcode-usage-cache-<label>.json`. If no cache exists, it keeps the Command Code row with an error message instead of hiding it. Expired-key display follows the general rule in [Expired credentials and stale cache](expired-credentials.md).

## Removed providers

- **OpenCode Go** was removed from the rate limit panel.
- **Pioneer** was removed from the rate limit panel. The Pioneer fetch script, cache files, env vars, and panel chip are no longer used.

## Adaptive polling

- Each rate-limit fetcher (Codex, Claude, Cursor, Gemini, Grok, OpenCode Go, Command Code) repolls adaptively instead of on a fixed cadence.
- After every fetch the loop fingerprints the meaningful usage state in that fetcher's `cache/*-usage-render.tsv`: the `meta`/`updatedAt` row is dropped, and time-derived bar columns (`resetsAt`, `resetAtEpoch`, `resetAfterSeconds`) are blanked so the fingerprint only changes when actual usage numbers or account/window structure change.
- When the fingerprint changes, the loop records the change time in `cache/*-usage-render.tsv.last_change` and uses `RATE_LIMIT_CHANGED_INTERVAL` (default `60`s). It keeps that short interval for any subsequent poll whose last change is still within `RATE_LIMIT_RECENT_CHANGE_WINDOW` (default `600`s / 10 minutes), even if the latest poll itself was unchanged. After the window expires with no further changes, it backs off to `RATE_LIMIT_UNCHANGED_INTERVAL` (default `300`s).
- The fingerprint is stored as `cache/*-usage-render.tsv.fingerprint`. Both the fingerprint and last-change files persist across overlay restarts; a restart does not force a short interval unless usage actually changed or a prior change is still inside the recent-change window.

## Pace markers

- Weekly and 5h pace markers are per paid account: each bar uses that window's own reset time.
- The derived-color tick is **expected** usage for on-pace spend: `expected = (windowSeconds - remainingSeconds) / windowSeconds * 100` (elapsed time through the reset window, not `usedPercent`).
- **Visibility:** hide the tick while none of the reset window has elapsed (`expected <= 0`). Unused sliding resets report remaining equal to the full duration at fetch time; treat those as not elapsed even after later wall-clock countdown. Show the tick as soon as any of the window has elapsed (`expected > 0`), even at 0% fill or the left edge. Do not gate on `usedPercent`, and do not hide based on pixel/rounded display position. A window that has not started has its whole span ahead of it, not behind it: treat its zero countdown as fully remaining so the tick stays hidden instead of pinning to the right edge.
- Per-provider summary deltas and per-bar ticks also cover paid accounts only, except when a provider has no paid account at all (Antigravity today): then its free accounts carry the pace instead, so the summary delta and ticks stay live.
- Each provider group shows one pace value, its average delta, beside the group name.

## Disable

- Set `RATE_LIMIT_PANEL_ENABLED=0` to disable the rate limit panel and its refresh loops.

See [Expired credentials and stale cache](expired-credentials.md) for how each provider handles token expiry and fallback data.

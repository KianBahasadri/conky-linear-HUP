# Rate limit panel

## Layout and colors

- The quota panel shows separate `CODEX`, `CLAUDE`, `CURSOR`, `GEMINI`, `GROK`, `OPENCODE`, and `CMD` chips, centered as a row across the panel. Codex rows use cyan/navy bars; Claude rows use coral/gold bars; Cursor rows use bronze bars; Gemini rows use Google blue/green and yellow/red bars; Grok rows use black bars; OpenCode Go rows use rose-crimson bars; Command Code rows use indigo bars.
- Overlay window height is computed from the account list (rows × row gap + padding) by the Lua spacer on each Conky tick. Startup sets `minimum_height` from the current usage caches so the first frame is not clipped. The fetch loops update `cache/*-usage-render.tsv` only — they do not rewrite configs or reload Conky.
- An account with no usable windows remains visible with a compact red error badge in place of its bars. The badge includes the fetch error and `RETRYING`, so transient provider failures are visible instead of looking like missing data.
- The selection chevron marks selected auth profiles: Codex rows whose path resolves to `~/.local/share/clusterfork-auth/codex/current`, Cursor rows whose path resolves to `~/.local/share/clusterfork-auth/cursor/current`, Claude rows whose path resolves to `~/.claude/.credentials.json` or whose access token equals the one in that file, Gemini rows matching Antigravity's `current` profile, Grok rows whose path resolves to `~/.grok/auth.json`, the configured OpenCode Go dashboard workspace, and Command Code rows whose path resolves to `~/.commandcode/auth.json` (or the `COMMAND_CODE_API_KEY` account). Codex uses a blue chevron, Claude uses orange, Cursor uses bronze, Gemini uses Google blue, Grok uses black, OpenCode Go uses red, and Command Code uses indigo. Token comparison is required for Claude because Claude Code replaces `~/.claude/.credentials.json` with a new regular file on login and on every OAuth refresh, so a symlink there does not survive.
- The panel frame, title chips, selection chevrons and row labels are lit the same way as the bars, so nothing on the panel reads as flat beside them: a shadow underneath, a face running from a lit top edge down to a dark base, and a rim brightest where the light lands. Chip faces are tinted with their own provider color so each keeps its hue in shadow.
- Every label above 8px is drawn twice: a dark pass one pixel below, then the glyphs shown with a vertical gradient as their source, running from a lifted top edge down to a deepened base. Two relief profiles set how far that runs. `soft` is a sheen, used everywhere a label already sits on a lit surface. `raised` packs a specular band into the top eighth of the cap height, digs the base out further and repeats the shadow a second pixel down; it needs the full cap height to land, so it is used for the all-caps account names and would only smear the 10px countdowns. The shadow is offset in `y` only — the panel's light comes from straight overhead, and a diagonal offset would imply a second source nothing else here is lit by. The lit pass uses `cairo_show_text` against a gradient rather than filling a text path, because an outline fill loses the hinting the 10px countdowns need. The 8px labels drawn inside the bars are deliberately left flat: at that size neither a gradient nor a contrast pass reads as depth, and both cost legibility. No label moves — every baseline is where it was.
- Usage bars are drawn as cylindrical tubes. In paint order: a contact shadow beneath the bar, a vertical gradient for the tube body (lit rim, near-black middle, bounce underneath), an inner rim shadow on the empty glass, the fill as its own cylinder in the accent color, a bright meniscus plus cast shadow at the head of the fill, faded quarter dividers, one tapered reflection streak, darkened end caps, and a gradient rim stroke. Bar height stays `8px`, so no row spacing or text baseline moves. Every Cairo gradient pattern must be destroyed after use: the panel repaints on each Conky tick and would otherwise leak roughly a dozen patterns per bar per frame.
- The text beside each bar counts down to that window's reset (`3h 16m`, `6d 8h`). A window with nothing used and no reset pending has not started rather than run out, so it shows its full span instead (`5h left`, `7d left`) and draws no pace tick. `wait` means the countdown ran out while the window still holds usage.
- When any account expires, the panel should keep the last cached fill and reset time until that window's reset has already passed; only then should the bar show `refresh`. See [Expired credentials and stale cache](expired-credentials.md).
- All account-rotation tooling is stored in `~/.config/clusterfork`. Shared auth profiles for Codex and Cursor are stored in `~/.local/share/clusterfork-auth/`.

## Codex

- Multiple accounts are discovered from `~/.local/share/clusterfork-auth/codex/auth.json.*`; `CODEX_AUTH_PATH` forces a single auth file. The legacy path `~/.codex/auth.json.*` is used as a fallback when the shared store directory does not exist.
- `CODEX_HOME`, `CODEX_SQLITE_HOME`, `CODEX_AUTH_STORE_DIR`, `CODEX_USAGE_DEGENERATE_RETRIES`, and `CODEX_LOCAL_RATE_LIMIT_MAX_AGE_SECONDS` are advanced overrides for local Codex state discovery and retry behavior. The usage endpoint is authoritative for every account whenever it returns a successful usage response; local session rate limits are discarded rather than allowed to replace fresh endpoint data.
- When the account-level limit is reached (`limit_reached` / `allowed`), only the blocking window is pinned to 100%: the one whose reset matches the response's `rate_limit_upsell.reset_at`, or the fullest window when the banner is missing (rollout samples always use the fullest window, since they carry no banner). Other windows keep their reported percentages, so an exhausted 5h window no longer pegs the weekly bar.
- Recent Codex rollout samples are still logged per session for diagnostics, including their values and matching account candidates. They never override a fresh endpoint response, so an older local sample cannot make a bar move backward.
- The `CODEX` chip's pace percentage uses the weekly window when available and falls back to the 5h window only when weekly is absent.

## Claude

- Multiple accounts are discovered from `~/.claude/.credentials.json.*`; `CLAUDE_CREDENTIALS_PATH` or `CLAUDE_AUTH_PATH` forces a single credentials file.
- Claude account names and selected-account chevrons use the same bright/dim and marker rules as Codex.
- Usage is fetched with a direct Anthropic quota-check request and cached per account. `CLAUDE_HOME`, `CLAUDE_USAGE_TTL`, `CLAUDE_PLAN_TYPE`, and `ANTHROPIC_DEFAULT_HAIKU_MODEL` are advanced overrides.
- Expired-grant display follows the general rule in [Expired credentials and stale cache](expired-credentials.md): cached 5h and weekly fills are held until each window's reset passes. The `refresh` prompt appears per window once its reset is over, or on the whole row when no cached sample exists.

## Cursor

- Multiple accounts are discovered from `~/.local/share/clusterfork-auth/cursor/auth.json.*`; `CURSOR_AUTH_PATH` forces a single auth file and `CURSOR_HOME` overrides the config directory. The legacy path `~/.config/cursor/auth.json.*` is used as a fallback when the shared store directory does not exist.
- `CURSOR_AUTH_STORE_DIR` overrides the shared auth store directory.
- Usage is fetched from Cursor's DashboardService. It renders Cursor's monthly `Auto + Composer` and `API` usage pools as the two bars for each account.
- Free accounts are labelled `AUTO (Free)` / `API (Free)` and both of their bars drop two shades down the slate ramp from the paid colors, so the whole row dims by the same amount rather than just the first bar.

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
- `cache/opencode-web-cache.json` stores the last successful dashboard response. If the next request fails, that response is shown as stale until a fresh dashboard request succeeds. The workspace URL is stored with the cache so data from a different workspace cannot be reused. If no matching cache exists, the panel keeps the OpenCode row with an error badge instead of hiding it. Expired-session display follows the general rule in [Expired credentials and stale cache](expired-credentials.md).
- `OPENCODE_USAGE_LABEL` controls the row label; the dashboard is represented as one selected workspace row rather than local auth profiles.

## Command Code

- Multiple accounts are discovered from `~/.commandcode/auth.json.*`; `COMMAND_CODE_AUTH_PATH` forces a single auth file. `COMMAND_CODE_API_KEY` takes precedence over local auth files, matching the CLI.
- Usage is fetched from Command Code's Studio API: `GET /alpha/whoami`, `GET /alpha/billing/credits`, `GET /alpha/billing/subscriptions`, and `GET /alpha/usage/summary`. Auth is a bearer API key from `~/.commandcode/auth.json` (written by `cmd login`) or `COMMAND_CODE_API_KEY`.
- It renders the rolling 5-hour and weekly credit windows plus the monthly included-credit pool as three bars. Window caps and remaining monthly credits come from `/alpha/billing/credits`; the monthly reset comes from the subscription period. The `CMD` title chip's percentage uses the monthly window.
- `COMMAND_CODE_HOME` overrides the config directory, `COMMANDCODE_API_URL` overrides the API base URL (`https://api.commandcode.ai`), and `COMMAND_CODE_USAGE_LABEL` labels the env-key account.
- On fetch errors, the panel serves the last successful usage from `cache/commandcode-usage-cache-<label>.json`. If no cache exists, it keeps the Command Code row with an error badge instead of hiding it. Expired-key display follows the general rule in [Expired credentials and stale cache](expired-credentials.md).

## Removed providers

- **Pioneer** was removed from the rate limit panel. The Pioneer fetch script, cache files, env vars, and panel chip are no longer used.

## Adaptive polling

- Each rate-limit fetcher (Codex, Claude, Cursor, Gemini, Grok, OpenCode Go, Command Code) repolls adaptively instead of on a fixed cadence.
- After every fetch the loop fingerprints the meaningful usage state in that fetcher's `cache/*-usage-render.tsv`: the `meta`/`updatedAt` row is dropped, and time-derived bar columns (`resetsAt`, `resetAtEpoch`, `resetAfterSeconds`) are blanked so the fingerprint only changes when actual usage numbers or account/window structure change.
- When the fingerprint changes, the loop records the change time in `cache/*-usage-render.tsv.last_change` and uses `RATE_LIMIT_CHANGED_INTERVAL` (default `60`s). It keeps that short interval for any subsequent poll whose last change is still within `RATE_LIMIT_RECENT_CHANGE_WINDOW` (default `600`s / 10 minutes), even if the latest poll itself was unchanged. After the window expires with no further changes, it backs off to `RATE_LIMIT_UNCHANGED_INTERVAL` (default `300`s).
- The fingerprint is stored as `cache/*-usage-render.tsv.fingerprint`. Both the fingerprint and last-change files persist across overlay restarts; a restart does not force a short interval unless usage actually changed or a prior change is still inside the recent-change window.

## Pace markers

- Weekly and 5h pace markers are per paid account: each bar uses that window's own reset time.
- The orange tick is **expected** usage for on-pace spend: `expected = (windowSeconds - remainingSeconds) / windowSeconds * 100` (elapsed time through the reset window, not `usedPercent`).
- **Visibility:** hide the tick while none of the reset window has elapsed (`expected <= 0`). Unused sliding resets report remaining equal to the full duration at fetch time; treat those as not elapsed even after later wall-clock countdown. Show the tick as soon as any of the window has elapsed (`expected > 0`), even at 0% fill or the left edge. Do not gate on `usedPercent`, and do not hide based on pixel/rounded display position. A window that has not started has its whole span ahead of it, not behind it: treat its zero countdown as fully remaining so the tick stays hidden instead of pinning to the right edge. The tick is faded at its top and bottom so it sits on the tube's curve rather than cutting across it; its position and width are unchanged.
- Per-provider chip percentages and per-bar ticks also cover paid accounts only, except when a provider has no paid account at all (Antigravity today): then its free accounts carry the pace instead, so the chip percentage and ticks stay live.
- The title row contains one provider chip per provider, each showing that provider's average pace delta. There is no separate combined `PACE` chip.

## Disable

- Set `RATE_LIMIT_PANEL_ENABLED=0` to disable the rate limit panel and its refresh loops.

See [Expired credentials and stale cache](expired-credentials.md) for how each provider handles token expiry and fallback data.

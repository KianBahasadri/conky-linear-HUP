# Rate limit panel

## Display

The provider mark (brand logo) and its pace percentage are centered on the
vertical middle of each provider group. Three equal rows put them on the second
row; four put them on the boundary between the second and third. The account
name and quota windows follow. Reset countdowns occupy a fixed-width
Reset countdowns render as a single left-aligned readout (`4h 59m`, `1d 23h`) in
the fixed-width countdown column flanking the flat observed-data bars on the right,
keeping the time cohesive and bar lengths uniform.
Pool-distinguishing labels (like `Auto`, `API`, `Reserve`, or `Argon`) flank
on the left. Standard interval windows (`5h`, `7d`, `Month`) omit the leading label so
bars start directly beside the account name.
Codex and Cursor show a computer icon beside each readable local login with an
access token. The icon appears on selected and unselected rows and expires
300 seconds after the last availability check. Quota can be stale while the
login icon is still visible.
Every row reserves two 14px icon slots, so names share a left edge regardless of
which icons are shown. A known banked-reset count is one apostrophe per reset
immediately after that account name. Zero and unknown counts add none. Each column's name area is the widest name-plus-apostrophe span in that column,
so a gap that every row in the column would share is closed. A shorter name or
fewer apostrophes keeps only its own difference, and that column's bars stay on
one origin. Names still ellipsize
within the width left after their own apostrophes.
A single horizontal rule separates provider sections in a column. A column with only one provider has no rule. Wide panels use a fixed 112px-high band aligned with the neighboring billing map, retaining two columns regardless of account count. Gemini follows Codex in the left column; OpenCode follows Cursor in the right column. Each column redistributes its row spacing to fill that band when profiles are added or removed, including during cache refreshes. Rows keep their minimum readable pitch; an overflowing column reserves a 16px footer and rotates through its own pages within the same band. Provider identity does not determine bar color. Shared typography, colors, and
overflow are owned by the [Desktop design system](design-system.md).

On monitors narrower than 1600px, the panel uses the full center column width.
Single-column panels below 880px use compact 24px account rows; below 560px,
quota windows stack beside the account name with enough height for each bar.
When all accounts fit, these narrow lists sit at the bottom of their allocated
region. The allocation for neighboring overlays stays unchanged. At 1280×1024,
the 608px-wide panel shows the current 13 accounts together without paging.

- Accounts sort alphabetically within each provider, regardless of plan tier.
- A row without usable windows remains visible with `Retrying:` and its error.
- Full windows do not display a `full` text label; the 100% bar fill and danger color indicate capacity exhaustion, and the account name turns danger color if any of its displayed bars are filled.
- Fill already recorded at local 05:00 is muted. Usage added since then keeps the bar's accent, or danger when the window is full. A window that opened at or after 05:00 is entirely current usage. The split reads `cache/rate-limit-usage-history.tsv`: the latest sample at or before 05:00 for that same account, window, and reset, clamped to the current fill. Until that sample exists, the whole fill stays the current color. Fetchers record a sample only when the used percent or reset changes, so an unchanged reading keeps the timestamp that was already in effect at 05:00. The first history file is seeded from Codex `stage=final` lines in the rate-limit panel log.
- Expired/stale accounts keep their cached fill and reset time until that
  window's absolute reset passes, then show `Refresh`. See
  [Expired credentials and stale cache](expired-credentials.md).
- Reset labels count down (`3h 16m`, `6d 8h`). A window with nothing used and
  no pending reset shows its full span (`5h`, `7d`) and no pace tick.
  `wait` means the countdown ended while usage remains.
- The provider's average pace delta in percent (`%`) sits beside its
  brand logo at the group's vertical center, in derived-data color. There is no
  separate summary row and no combined pace value. The vertical tick on each
  eligible bar uses the same derived color.
- Cache refreshes do not resize or reload windows. Startup bounds the list and
  excess rows rotate through the available region.

Codex and Cursor select the profile pointed to by the store's `current` link,
falling back to the CLI auth file. Claude uses the active credential file or a
matching access token, and Gemini uses Antigravity's current profile.
The selected profile has the same visual treatment as the other profiles.

Claude requires token comparison because its
CLI replaces the credential file during refresh.

Account-rotation tooling lives in `~/.config/clusterfork`; shared Codex/Cursor
profiles live in `~/.local/share/clusterfork-auth/`.

## Local Codex and Cursor profiles

The fetchers poll the providers directly using `auth.json.*` files under
`~/.local/share/clusterfork-auth/codex` and
`~/.local/share/clusterfork-auth/cursor`. They skip lock files. If the store
directory is absent, they look for profiles under the CLI home directory
(`~/.codex` or `~/.config/cursor`). If no suffixed profiles are found, they use
that CLI's `auth.json`. For auth file and directory overrides, see
[Configuration](configuration.md#rate-limit-panel).

Codex's account ID and Cursor's access-token subject are hashed to preserve
account identity across aliases, token rotation, and the transition from the
retired account snapshot. Each identity has one row, one quota poll, and one
contribution to provider pace. The poll uses the selected alias or the first
saved alias. Credentials with no account identifier use their profile name.
The current local profiles determine which rows appear.

Fresh measurements keep the provider-reported plan tier and reset times.
Failed polls reuse the last measured windows when the account identity matches.
The render cache carries availability and observation timestamps independently.
Quota older than 300 seconds or past its reset is stale and contributes neither
pace ticks nor the provider average. See
[Expired credentials and stale cache](expired-credentials.md).

## Codex

- Codex polls `/wham/usage`. `CODEX_USAGE_DEGENERATE_RETRIES` controls retries of incomplete responses. If the account limit is reached, only the blocking window is pinned to 100%. Additional model limits keep the `Reserve` label. The response's `rate_limit_reset_credits.available_count` records the number of banked resets already granted and still unused. The row draws one apostrophe per reset after the account name. A missing or malformed count draws none. A retained stale sample keeps its recorded count.
- The `CODEX` summary's pace percentage uses the weekly window when available, falling back to 5h and monthly (for Free accounts). Pro accounts are weighted 20x relative to Plus accounts (400x relative to Free accounts), while Plus accounts are weighted 20x relative to Free accounts (weight 1) in the average. Reserve is never the summary's pace source. Free accounts have a single 30-day window.

## Claude

- The Claude account was removed from active display because the Claude subscription expired. Multiple accounts are discovered from `~/.claude/.credentials.json.*` when valid credentials exist; `CLAUDE_CREDENTIALS_PATH` or `CLAUDE_AUTH_PATH` forces a single credentials file.
- Claude accounts are not highlighted when selected.
- Usage is fetched with a direct Anthropic quota-check request and cached per account. `CLAUDE_HOME`, `CLAUDE_USAGE_TTL`, `CLAUDE_PLAN_TYPE`, and `ANTHROPIC_DEFAULT_HAIKU_MODEL` are advanced overrides.
- Expired-grant display follows the general rule in [Expired credentials and stale cache](expired-credentials.md): cached 5h and weekly fills are held until each window's reset passes. The `refresh` prompt appears per window once its reset is over, or on the whole row when no cached sample exists.

## Cursor

- Cursor uses DashboardService's `Auto + Composer` and `API` pools (`Auto` and `API`). Free accounts display only `Auto`.
- Fresh measured windows display on-pace ticks and participate once per account in the `CURSOR` average. Pro accounts carry weight 20. Free and unknown tiers carry weight 1.

## Gemini

- Accounts are discovered from Antigravity's rotation state in `~/.gemini/antigravity-cli/rotate-auth`. The selected profile reads the live GNOME Keyring item `service=gemini username=antigravity`; inactive profiles read `service=rotate-antigravity username=<profile>`.
- Usage is fetched from Antigravity's Code Assist API (`retrieveUserQuotaSummary` with `User-Agent: antigravity/cli/...` so the server includes the `Gemini Models` and `Gemini 4 Argon` quota groups). Pro accounts render 5-hour and weekly Gemini quota bars plus a third `Argon` weekly bar (when the separate Gemini 4 Argon pool is present) on one 16px row. Free accounts render one weekly bar on one 16px row. Paid tiers (such as Google AI Pro) are recognized from the account's `paidTier` subscription.
- The `ANTIGRAVITY` pace summary's delta includes both Pro and Free accounts, weighting Pro accounts 20x relative to Free accounts (weight 1) in the average. Free Gemini accounts display on-pace ticks on their weekly bar.
- `GEMINI_ANTIGRAVITY_STATE_DIR` overrides the rotation state directory, `GEMINI_CODE_ASSIST_ENDPOINT` overrides the Antigravity API endpoint, `GEMINI_ANTIGRAVITY_CLI` overrides the `agy` executable, and `GEMINI_AUTH_REFRESH_TIMEOUT_SECONDS` controls the refresh timeout.

## Grok

- Grok was removed from active display. Multiple accounts are discovered from `~/.grok/auth.json.*`; `GROK_AUTH_PATH` forces a single auth file.
- Usage is fetched from Grok Build's billing API at `cli-chat-proxy.grok.com/v1/billing?format=credits`. It renders the included-credit pool as one bar per account (7-day cycle labelled `7d` on Build subscriptions, or monthly cycle labelled `Month` on Tier 1).
- `GROK_HOME` overrides the Grok config directory and `GROK_CLI_CHAT_PROXY_BASE_URL` overrides the billing API base URL.

## OpenCode Go

- Usage is one `GET https://opencode.ai/zen/go/v1/usage` with the Go API key as a bearer token and the workspace id in `x-opencode-org-id`. `OPENCODE_API_KEY` overrides the key. Otherwise the fetcher reads the active `opencode-go` key in `${XDG_DATA_HOME:-~/.local/share}/opencode/opencode.db`, then the legacy `auth.json` `opencode-go` entry. `OPENCODE_WORKSPACE_ID` overrides the workspace; otherwise the signed-in `opencode` credential's `orgID` is used.
- The rolling, weekly, and monthly meters are the 5-hour, weekly, and monthly bars. A `rate-limited` meter is drawn full. The route returns each reset time and not the window length, so pace ticks use 5 hours, 7 days, and 31 days.
- The `OPENCODE` pace summary's delta uses the monthly window (skipped entirely if the row has none), unlike Codex/Claude which use the weekly window.
- `cache/opencode-usage-cache.json` stores the last successful meters for that workspace. If the next request fails, those meters are shown as stale until a fresh request succeeds. A cache from a different workspace is not reused. If no matching cache exists, the panel keeps the OpenCode row with an error message instead of hiding it. Expired-key display follows the general rule in [Expired credentials and stale cache](expired-credentials.md).
- `OPENCODE_USAGE_LABEL` controls the row label; the workspace is one selected row.

## Command Code

- Command Code was removed from active display. Multiple accounts are discovered from `~/.commandcode/auth.json.*`; `COMMAND_CODE_AUTH_PATH` forces a single auth file. `COMMAND_CODE_API_KEY` takes precedence over local auth files, matching the CLI.
- Usage is fetched from Command Code's Studio API: `GET /alpha/whoami`, `GET /alpha/billing/credits`, `GET /alpha/billing/subscriptions`, and `GET /alpha/usage/summary`. Auth is a bearer API key from `~/.commandcode/auth.json` (written by `cmd login`) or `COMMAND_CODE_API_KEY`.
- It renders the rolling 5-hour and weekly credit windows plus the monthly included-credit pool as three bars. Window caps and remaining monthly credits come from `/alpha/billing/credits`; the monthly reset comes from the subscription period. The `CMD` pace summary's delta uses the monthly window.
- `COMMAND_CODE_HOME` overrides the config directory, `COMMANDCODE_API_URL` overrides the API base URL (`https://api.commandcode.ai`), and `COMMAND_CODE_USAGE_LABEL` labels the env-key account.
- On fetch errors, the panel serves the last successful usage from `cache/commandcode-usage-cache-<label>.json`. If no cache exists, it keeps the Command Code row with an error message instead of hiding it. Expired-key display follows the general rule in [Expired credentials and stale cache](expired-credentials.md).

## Removed providers

- **Claude** account was removed from the rate limit panel because the Claude subscription expired. Its background fetch loop is stopped and disabled.
- **Grok** was removed from the rate limit panel. Its background fetch loop is stopped and disabled.
- **Command Code** was removed from the rate limit panel. Its background fetch loop is stopped and disabled.
- **Pioneer** was removed from the rate limit panel. The Pioneer fetch script, cache files, env vars, and panel chip are no longer used.

## Adaptive polling

- Each active rate-limit fetcher (Codex, Cursor, Gemini, OpenCode) repolls adaptively instead of on a fixed cadence.
- After every fetch the loop fingerprints the meaningful usage state in that fetcher's `cache/*-usage-render.tsv`: the `meta`/`updatedAt` row is dropped, and time-derived bar columns (`resetsAt`, `resetAtEpoch`, `resetAfterSeconds`) and account availability/measurement capture timestamps are blanked. Usage, availability, selection, freshness/error and account/window structure changes still affect the fingerprint.
- When the fingerprint changes, the loop records the change time in `cache/*-usage-render.tsv.last_change` and uses `RATE_LIMIT_CHANGED_INTERVAL` (default `60`s). It keeps that short interval for any subsequent poll whose last change is still within `RATE_LIMIT_RECENT_CHANGE_WINDOW` (default `600`s / 10 minutes), even if the latest poll itself was unchanged. After the window expires with no further changes, it backs off to `RATE_LIMIT_UNCHANGED_INTERVAL` (default `300`s).
- The fingerprint is stored as `cache/*-usage-render.tsv.fingerprint`. Both the fingerprint and last-change files persist across overlay restarts; a restart does not force a short interval unless usage actually changed or a prior change is still inside the recent-change window.

## Pace markers

- Pace markers render across all accounts (both paid and free): each bar uses that window's own reset time.
- The derived-color tick is **expected** usage for on-pace spend: `expected = (windowSeconds - remainingSeconds) / windowSeconds * 100` (elapsed time through the reset window, not `usedPercent`). Ticks render on top of the bar fill with full opacity (`1.0`) when positioned within the filled progress region (`expected <= usedPercent`), and quieter opacity (`0.7`) when ahead on the empty track.
- **Visibility:** hide the tick while none of the reset window has elapsed (`expected <= 0`). Unused sliding resets report remaining equal to the full duration at fetch time; treat those as not elapsed even after later wall-clock countdown. Show the tick as soon as any of the window has elapsed (`expected > 0`), even at 0% fill or the left edge. Do not gate on `usedPercent`, and do not hide based on pixel/rounded display position. A window that has not started has its whole span ahead of it, not behind it: treat its zero countdown as fully remaining so the tick stays hidden instead of pinning to the right edge.
- Per-provider summary deltas include all accounts, properly capacity-weighted by tier: Pro accounts carry 20x the weight of Free accounts on Cursor and Gemini. On Codex, Pro carries 400x, Plus carries 20x, and Free carries 1x (maintaining a 20x ratio between each tier).
- Each provider group shows one pace value, its average delta, beside the group name.

## Disable

- Set `RATE_LIMIT_PANEL_ENABLED=0` to disable the rate limit panel and its refresh loops.

See [Expired credentials and stale cache](expired-credentials.md) for how each provider handles token expiry and fallback data.

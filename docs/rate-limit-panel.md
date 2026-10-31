# Rate limit panel

## Display

The provider mark (brand logo) sits on the highlighted (selected) row of its group
(or on the first row when no profile is selected), followed by the account name and quota windows. Reset countdowns occupy a fixed-width
column flanking the flat observed-data bars on the right, keeping bar lengths uniform.
Two-part labels left-align each quantity in a 3-character field so both numbers
share x-positions across rows (`9h  58m`, `10d 11h`, `17d 1h`) rather than
staggering with digit count.
Pool-distinguishing labels (like `Auto`, `API`, `Reserve`, or `Argon`) flank
on the left. Standard interval windows (`5h`, `7d`, `Month`) omit the leading label so
bars start directly beside the account name.
Selected profiles use a neutral raised row and a medium-weight account name.
Managed Codex/Cursor accounts show one small Lucide computer icon beside the
name when an independently authenticated local login is configured on this host.
The icon appears on selected and unselected rows alike; selection keeps its
separate highlight. All managed accounts are cloud-accessible, so no cloud badge
is shown. A managed row without the computer icon is cloud-only, or its local
availability is unknown/stale. A leftover auth file never establishes availability.
The icon uses space inside the existing name column; names retain their normal
ellipsis behavior and all bars and reset columns stay aligned.
A single horizontal rule separates provider sections in a column. A column with only one provider has no rule. Wide panels use a fixed 112px-high band aligned with the neighboring billing map, retaining two columns regardless of account count. Each column redistributes its row spacing to fill that band when profiles are added or removed, including during cache refreshes. Rows keep their minimum readable pitch; an overflowing column reserves a 16px footer and rotates through its own pages within the same band. Provider identity does not determine bar color. Shared typography, colors, and
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
  brand logo on the highlighted row of each group (falling back to the first row if no account is selected), in derived-data color. There is no
  separate summary row and no combined pace value. The vertical tick on each
  eligible bar uses the same derived color.
- Cache refreshes do not resize or reload windows. Startup bounds the list and
  excess rows rotate through the available region.

Selected profiles are resolved by Clusterfork's eligible `selected_local_profile`
for Codex/Cursor, the active Claude credential file or matching access
token, and Antigravity's current profile.
Claude requires token comparison because its
CLI replaces the credential file during refresh.

Account-rotation tooling lives in `~/.config/clusterfork`; shared Codex/Cursor
profiles live in `~/.local/share/clusterfork-auth/`.

## Managed Codex/Cursor source and ownership

Both fetchers use Clusterfork's [read-only consumer contract, schema version 1](https://github.com/KianBahasadri/clusterfork/blob/5787a55a3c5cccadf0f221006fcf9c99209d8bae/docs/remote-development-accounts.md#read-only-consumer-contract-schema-version-1),
delivered by KIAN-941. Each poll invokes the installed account CLI:

```bash
~/.config/clusterfork/automation/venv/bin/python \
  ~/.config/clusterfork/automation/accounts.py snapshot --provider codex \
  --store ~/.local/share/clusterfork-auth/codex
# Repeat with --provider cursor and the cursor store.
```

The CLI joins offline, host-scoped availability with the controller's read-only
`GET /api/accounts/snapshot?provider=codex|cursor`, using the existing Azure CLI
operator identity's management access token. It never signs in for the operator.
The controller collects quota under its credential/lease boundary; polling this
snapshot cannot initiate a provider probe or refresh. Install/update Clusterfork
and retain its existing operator access before enabling these fetchers.
`CLUSTERFORK_ACCOUNTS_SCRIPT` can override the installed `automation/accounts.py`;
`CLUSTERFORK_PYTHON` can override its interpreter (otherwise the adjacent
`venv/bin/python`, then the fetcher's interpreter). The subprocess has a 45-second
timeout; command failures report a bounded error without exposing subprocess output.

Rows, cached usage, daily usage history and quota contributions join by
`(provider, account_id)`, where the upstream ID is an unprefixed 64-character
SHA-256. Aliases are display names only. Independent sessions and multiple aliases
produce one account row and one contribution to the provider pace average.
The label stays stable across selection changes. JSON retains aliases, stable
identity, local profiles, selected profile, availability capture time, cloud state,
and usage source. The TSV appends explicit availability/identity/capture/freshness
fields to account records and identity/source-window fields to bar records;
legacy records with no availability fields show no local icon.

Managed accounts, including dual-session accounts, always use cloud quota data.
The fetchers never enumerate or read their auth copies for tokens, refresh them,
rewrite them, or fall back to them on source failure. Existing `CODEX_AUTH_PATH`
and `CURSOR_AUTH_PATH` settings cannot bypass this ownership boundary. Ordinary
unenrolled accounts may still use direct provider polling, but only when the
current contract explicitly reports `cloud_available: false` and an eligible local
profile. Their quota is also deduplicated by stable identity. Auth store locations
come from `CODEX_AUTH_STORE_DIR` / `CURSOR_AUTH_STORE_DIR`; an explicit
`CODEX_HOME` / `CURSOR_HOME` continues to set the corresponding store by default.

Usage preserves original observation/attempt timestamps, source-window names,
reset times, durations (including unknown durations), source freshness/age and
error codes. Freshness is recomputed from the observation time and absolute
resets, with a maximum age of 300 seconds, both at fetch time and while rendering.
Unknown quota produces an error row rather than zero usage. Failed/unauthorized
snapshots retain known accounts and their last captured windows as stale; expired
windows show `Refresh`. Stale quota contributes neither pace ticks nor averages.
Cached availability is never reused after a failed metadata read; local icons also
expire after 300 seconds when fetching stops. A controller error can retain a
fresh offline availability result, independently of quota freshness.

Schema version 1 supplies no plan tier. Managed accounts therefore use the
baseline capacity weight of 1 rather than inferring a subscription from aliases
or duplicating local/cloud capacity. Known tiers from direct local polling retain
their existing weights.

## Codex

- Managed accounts render the snapshot's `codex/primary`, `codex/secondary`, and applicable `gpt-…/primary|secondary` windows, preserving their original names for history. Durations distinguish 5-hour, weekly and monthly windows; reserve model limits retain the `Reserve` label. No local session measurement replaces the cloud source.
- Explicit unenrolled local profiles use `/wham/usage`. `CODEX_USAGE_DEGENERATE_RETRIES` controls retries of incomplete local responses. If the account limit is reached, only the blocking window is pinned to 100%; additional reserve limits stay separate. Managed polling never enters the local HTTP 401/403 token-refresh recovery path.
- The `CODEX` summary's pace percentage uses the weekly window when available, falling back to 5h and monthly (for Free accounts). Pro accounts are weighted 20x relative to Plus accounts (400x relative to Free accounts), while Plus accounts are weighted 20x relative to Free accounts (weight 1) in the average. Reserve is never the summary's pace source. Free accounts have a single 30-day window.

## Claude

- The Claude account was removed from active display because the Claude subscription expired. Multiple accounts are discovered from `~/.claude/.credentials.json.*` when valid credentials exist; `CLAUDE_CREDENTIALS_PATH` or `CLAUDE_AUTH_PATH` forces a single credentials file.
- Claude selected accounts use the same neutral row treatment as Codex.
- Usage is fetched with a direct Anthropic quota-check request and cached per account. `CLAUDE_HOME`, `CLAUDE_USAGE_TTL`, `CLAUDE_PLAN_TYPE`, and `ANTHROPIC_DEFAULT_HAIKU_MODEL` are advanced overrides.
- Expired-grant display follows the general rule in [Expired credentials and stale cache](expired-credentials.md): cached 5h and weekly fills are held until each window's reset passes. The `refresh` prompt appears per window once its reset is over, or on the whole row when no cached sample exists.

## Cursor

- Managed cloud and joined accounts render exactly the supplied `cursor/api` and optional `cursor/included` pools as `API` and `Included`. Included total usage is never relabeled `Auto`. Billing-cycle resets are Unix seconds, not milliseconds; nullable duration/reset metadata does not invent a pace estimate.
- Explicit unenrolled local profiles retain DashboardService's `Auto + Composer` and `API` pools (`Auto` and `API`); Free local accounts display only `Auto`.
- Fresh measured windows display on-pace ticks and participate once per account in the `CURSOR` average. Known Pro local accounts retain weight 20, Free and unknown tiers weight 1.

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

- Usage is fetched from the authenticated OpenCode Go dashboard configured by `OPENCODE_WORKSPACE_URL` (or `OPENCODE_WORKSPACE_ID`). The session cookie is read from Firefox's `cookies.sqlite` for `opencode.ai` (Install default profile, overridable with `OPENCODE_FIREFOX_PROFILE`). Set `OPENCODE_FIREFOX_CONTAINER` to select a named Firefox container; matching is case-insensitive. `OPENCODE_COOKIE` / `OPENCODE_AUTH_COOKIE` remain optional overrides.
- The fetcher uses one dashboard `GET` request per refresh. It never reads OpenCode local auth files or SQLite usage DBs, and never calls the OpenCode API or sends a usage probe.
- The dashboard's rolling/5-hour ($12 limit), weekly ($30 limit), and monthly ($60 limit) cards are parsed and rendered as three bars.
- The `OPENCODE` pace summary's delta uses the monthly window (skipped entirely if the row has none), unlike Codex/Claude which use the weekly window.
- `cache/opencode-web-cache.json` stores the last successful dashboard response. If the next request fails, that response is shown as stale until a fresh dashboard request succeeds. The workspace URL is stored with the cache so data from a different workspace cannot be reused. If no matching cache exists, the panel keeps the OpenCode row with an error message instead of hiding it. Expired-session display follows the general rule in [Expired credentials and stale cache](expired-credentials.md).
- `OPENCODE_USAGE_LABEL` controls the row label; the dashboard is represented as one selected workspace row rather than local auth profiles.

## Command Code

- Command Code was removed from active display. Multiple accounts are discovered from `~/.commandcode/auth.json.*`; `COMMAND_CODE_AUTH_PATH` forces a single auth file. `COMMAND_CODE_API_KEY` takes precedence over local auth files, matching the CLI.
- Usage is fetched from Command Code's Studio API: `GET /alpha/whoami`, `GET /alpha/billing/credits`, `GET /alpha/billing/subscriptions`, and `GET /alpha/usage/summary`. Auth is a bearer API key from `~/.commandcode/auth.json` (written by `cmd login`) or `COMMAND_CODE_API_KEY`.
- It renders the rolling 5-hour and weekly credit windows plus the monthly included-credit pool as three bars. Window caps and remaining monthly credits come from `/alpha/billing/credits`; the monthly reset comes from the subscription period. The `CMD` pace summary's delta uses the monthly window.
- `COMMAND_CODE_HOME` overrides the config directory, `COMMANDCODE_API_URL` overrides the API base URL (`https://api.commandcode.ai`), and `COMMAND_CODE_USAGE_LABEL` labels the env-key account.
- On fetch errors, the panel serves the last successful usage from `cache/commandcode-usage-cache-<label>.json`. If no cache exists, it keeps the Command Code row with an error message instead of hiding it. Expired-key display follows the general rule in [Expired credentials and stale cache](expired-credentials.md).

## Removed providers

- **Claude** account was removed from the rate limit panel because the Claude subscription expired. Its background fetch loop is stopped and disabled.
- **Grok** was removed from the rate limit panel. Its background fetch loop is stopped and disabled.
- **OpenCode Go** was removed from the rate limit panel. Its background fetch loop is stopped and disabled.
- **Command Code** was removed from the rate limit panel. Its background fetch loop is stopped and disabled.
- **Pioneer** was removed from the rate limit panel. The Pioneer fetch script, cache files, env vars, and panel chip are no longer used.

## Adaptive polling

- Each active rate-limit fetcher (Codex, Cursor, Gemini) repolls adaptively instead of on a fixed cadence.
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

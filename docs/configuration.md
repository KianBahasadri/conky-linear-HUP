# Configuration

Copy `.env.example` to `.env` and fill in the overlays you use.

## Linear overlay

| Variable | Purpose |
| --- | --- |
| `LINEAR_API_KEY` | Linear API key |
| `LINEAR_OVERLAY_ENABLED` | Set to `0` to disable |
| `LINEAR_TASK_STATES` | Issue states to include |
| `LINEAR_TASK_LIMIT` | Max active issues shown |
| `LINEAR_COMPETITION_TASK_LIMIT` | Max competition-project issues shown |
| `LINEAR_BACKLOG_DUE_SOON_LIMIT` | Max Backlog issues due within 3 days shown |
| `LINEAR_DONE_LOOKBACK_HOURS` | How long completed cards stay visible |
| `LINEAR_PRIMARY_MONITOR_INDEX` | Monitor index for primary placement |
| `PRIMARY_WAIT_SECONDS` | Startup wait before placing on the primary monitor |

## Rate limit panel

| Variable | Purpose |
| --- | --- |
| `RATE_LIMIT_PANEL_ENABLED` | Set to `0` to disable |
| `RATE_LIMIT_PANEL_GAP_Y` | Vertical gap from the bottom screen edge (default `6`) |
| `RATE_LIMIT_CHANGED_INTERVAL` | Short repoll delay while usage is active (default `60`) |
| `RATE_LIMIT_UNCHANGED_INTERVAL` | Long repoll delay after idle past the recent-change window (default `300`) |
| `RATE_LIMIT_RECENT_CHANGE_WINDOW` | Seconds after any usage change to keep using the short interval (default `600`) |
| `CLAUDE_PLAN_TYPE` | Default Claude plan label when not inferred |
| `CLAUDE_USAGE_LABEL` | Claude account label override |
| `CLAUDE_CREDENTIALS_PATH` | Force a single Claude credentials file |
| `CLAUDE_AUTH_PATH` | Alias for `CLAUDE_CREDENTIALS_PATH` |
| `CLAUDE_HOME` | Override the Claude config directory |
| `CLAUDE_USAGE_TTL` | Seconds to reuse a fresh Claude API cache entry |
| `CODEX_AUTH_PATH` | Force a single Codex auth file |
| `CODEX_HOME` | Override the Codex config directory |
| `CODEX_SQLITE_HOME` | Override Codex local state sqlite directory |
| `CODEX_AUTH_STORE_DIR` | Override the shared Codex auth store directory |
| `CODEX_USAGE_DEGENERATE_RETRIES` | Retries when Codex returns degenerate usage windows |
| `CODEX_LOCAL_RATE_LIMIT_MAX_AGE_SECONDS` | Max age for local Codex session rate-limit diagnostics |
| `CURSOR_AUTH_PATH` | Force a single Cursor auth file |
| `CURSOR_HOME` | Override the Cursor config directory |
| `CURSOR_AUTH_STORE_DIR` | Override the shared Cursor auth store directory |
| `GEMINI_ANTIGRAVITY_STATE_DIR` | Override Antigravity rotation state directory |
| `GEMINI_CODE_ASSIST_ENDPOINT` | Override the Antigravity API endpoint |
| `GEMINI_ANTIGRAVITY_CLI` | Override the `agy` executable |
| `GEMINI_AUTH_REFRESH_TIMEOUT_SECONDS` | Timeout for `agy` credential refresh |
| `GROK_AUTH_PATH` | Force a single Grok auth file |
| `GROK_HOME` | Override the Grok config directory |
| `GROK_CLI_CHAT_PROXY_BASE_URL` | Override the Grok billing API base URL |
| `OPENCODE_WORKSPACE_URL` | OpenCode Go dashboard URL to fetch |
| `OPENCODE_WORKSPACE_ID` | Workspace ID used to construct the dashboard URL when `OPENCODE_WORKSPACE_URL` is unset |
| `OPENCODE_FIREFOX_HOME` | Override `~/.mozilla/firefox` when reading the dashboard cookie |
| `OPENCODE_FIREFOX_PROFILE` | Firefox profile path or profile directory name under the Firefox home |
| `OPENCODE_FIREFOX_CONTAINER` | Firefox container name whose `opencode.ai` cookies should be used; matching is case-insensitive |
| `OPENCODE_COOKIE` | Optional Cookie header override; when unset, the fetcher reads `opencode.ai` cookies from Firefox |
| `OPENCODE_AUTH_COOKIE` | Backward-compatible alias for `OPENCODE_COOKIE` |
| `OPENCODE_USAGE_LABEL` | Label shown for the dashboard workspace |
| `COMMAND_CODE_API_KEY` | Optional API key; when set, it overrides `~/.commandcode/auth.json` (same as the CLI) |
| `COMMAND_CODE_USAGE_LABEL` | Row label when using `COMMAND_CODE_API_KEY` |
| `COMMAND_CODE_HOME` | Override the Command Code config directory (`~/.commandcode`) |
| `COMMANDCODE_HOME` | Alias for `COMMAND_CODE_HOME` |
| `COMMAND_CODE_AUTH_PATH` | Force a single Command Code auth file |
| `COMMANDCODE_AUTH_PATH` | Alias for `COMMAND_CODE_AUTH_PATH` |
| `COMMANDCODE_API_URL` | Override the Command Code API base URL |

Pioneer env vars (`PIONEER_API_KEY`, `PIONEER_USAGE_LABEL`, `PIONEER_MONTHLY_CREDIT_LIMIT`) were removed with the Pioneer rate-limit panel integration.

## Minecraft overlay

| Variable | Purpose |
| --- | --- |
| `MINECRAFT_SERVER` | Host and port as `host:port` |
| `MINECRAFT_SERVER_HOST` | Host when not using `MINECRAFT_SERVER` |
| `MINECRAFT_SERVER_PORT` | Port when not using `MINECRAFT_SERVER` |
| `MINECRAFT_SERVER_LABEL` | Panel label |
| `MINECRAFT_OVERLAY_ENABLED` | Set to `0` to disable |
| `MINECRAFT_GAP_X` | Horizontal gap from screen edge |
| `MINECRAFT_GAP_Y` | Vertical gap from screen edge (default `6`) |
| `MINECRAFT_REFRESH_SECONDS` | Fetch interval |
| `MINECRAFT_STATUS_TIMEOUT_SECONDS` | TCP status probe timeout |
| `MINECRAFT_PROTOCOL_VERSION` | Protocol version for status negotiation |
| `MINECRAFT_LAST_SEEN_MAX_GAP_SECONDS` | Max gap between successful polls to keep last-player idle time (default `300`) |

## PebbleHost Minecraft stats

| Variable | Purpose |
| --- | --- |
| `PEBBLEHOST_API_KEY` | PebbleHost API key for resource stats and player names |
| `PEBBLEHOST_SERVER_ID` | Force a specific server when auto-matching fails |
| `PEBBLEHOST_API_TIMEOUT_SECONDS` | PebbleHost API timeout |

## GitHub overlay

| Variable | Purpose |
| --- | --- |
| `GITHUB_USERNAME` | GitHub account to render |
| `GH_USERNAME` | Alias for `GITHUB_USERNAME` |
| `GITHUB_TOKEN` | Optional token for authenticated contribution requests |
| `GITHUB_OVERLAY_ENABLED` | Set to `0` to disable |
| `GITHUB_GAP_X` | Left offset in px; empty matches the rate limit panel's drawn frame |
| `GITHUB_GAP_Y` | Bottom offset in px; empty sits the skyline on the rate limit panel |
| `GITHUB_SKYLINE_HEIGHT` | Requested skyline window height (default `340`) |
| `GITHUB_SKYLINE_MIN_HEIGHT` | Floor after the Linear clearance is taken out (default `180`) |
| `GITHUB_LINEAR_CLEARANCE` | Gap kept between the Linear cards and the skyline (default `14`) |
| `GITHUB_ROOF_CLEARANCE` | Gap above the rate limit panel's title chips (default `11`) |
| `GITHUB_REFRESH_SECONDS` | Fetch interval |
| `GITHUB_TIMEOUT_SECONDS` | Request timeout |

## Weather and running overlay

| Variable | Purpose |
| --- | --- |
| `WEATHER_OVERLAY_ENABLED` | Set to `0` to disable |
| `WEATHER_LATITUDE` | Exact latitude; must be paired with longitude |
| `WEATHER_LONGITUDE` | Exact longitude; must be paired with latitude |
| `WEATHER_LOCATION` | City or postal code to geocode when coordinates are unset |
| `WEATHER_LOCATION_LABEL` | Override the displayed location name |
| `WEATHER_UNITS` | `imperial`, `metric`, or `auto` (IP country only); defaults to `imperial` |
| `WEATHER_GAP_X` | Horizontal gap from the right screen edge (default `6`) |
| `WEATHER_GAP_Y` | Vertical gap from the bottom screen edge (default `6`) |
| `WEATHER_REFRESH_SECONDS` | Weather and air-quality refresh interval |
| `WEATHER_TIMEOUT_SECONDS` | Timeout for each provider request |

Location resolution prefers exact coordinates, then `WEATHER_LOCATION`, then an approximate public-IP location. Exact coordinates are recommended for local conditions.

## System resource monitor

| Variable | Purpose |
| --- | --- |
| `RESOURCE_MONITOR_OVERLAY_ENABLED` | Set to `0` to disable |
| `RESOURCE_MONITOR_GAP_X` | Horizontal gap from the right screen edge |
| `RESOURCE_MONITOR_GAP_Y` | Optional vertical gap override; when unset, follows Linear’s per-monitor `gap_y` so gauge tops stay flush with cards |
| `RESOURCE_HISTORY_SAMPLES` | Samples retained for sparklines; defaults to `90` |
| `RESOURCE_NET_GAUGE_WINDOW` | Moving-average window (samples) for the NET gauge; defaults to `6` |

The transparent HUD is generated on every monitor. It reads local Linux telemetry for CPU, memory, network throughput, `/` and `/home` disk usage, load average, and uptime. Each display retains its own recent samples for the active Conky session. NET sparkline scale uses the max IN/OUT rate recorded in the last 7 days (`cache/resource-net-peaks.tsv`). Bottom readouts fill a 3-column grid in column-major order under the gauges (LOAD/UP, `/`/`/home`, IN/OUT); see [Layout](README.md#layout).

## Affine billing map

| Variable | Purpose |
| --- | --- |
| `BILLING_OVERLAY_ENABLED` | Set to `0` to disable |
| `BILLING_GAP_X` | Optional right-edge gap; empty centers the map on the weather panel |
| `BILLING_GAP_Y` | Optional top offset; empty sits the map just above the weather panel |
| `BILLING_REFRESH_SECONDS` | Provider refresh interval (default `900`) |
| `BILLING_TIMEOUT_SECONDS` | Per-provider command/request timeout (default `30`) |
| `BILLING_AWS_ENABLED` | Set to `1` to plot month-to-date AWS spend against the live monthly COST budget |
| `BILLING_AWS_ACCESS_KEY_ID` | Access key for the Terraform-provisioned billing-read IAM user |
| `BILLING_AWS_SECRET_ACCESS_KEY` | Secret for that access key; takes precedence over a profile |
| `BILLING_AWS_PROFILE` | Optional AWS profile when no access key is set; otherwise the default boto3 chain applies |
| `BILLING_AWS_BUDGET_NAME` | Optional budget name when more than one monthly COST budget exists |
| `BILLING_AWS_CACHE_TTL_SECONDS` | Optional AWS Cost Explorer query cache TTL in seconds (default `86400`, daily refresh) |
| `BILLING_AZURE_ENABLED` | Set to `1` to plot this month's Azure credit spend against the live starting balance |
| `BILLING_AZURE_SUBSCRIPTION_ID` | Optional subscription for month-to-date spend; otherwise the Azure CLI active subscription is used |
| `BILLING_AZURE_API_VERSION` | Cost Management API version override (default `2025-03-01`) |
| `OPENROUTER_API_KEY` | OpenRouter management key for live credits and trailing usage |
| `BILLING_GITHUB_ACTIONS_ENABLED` | Set to `1` to plot the authenticated `gh` user's private-repository standard-runner minutes against the plan allowance; the token needs `user` scope |
| `BILLING_BLACKSMITH_ENABLED` | Set to `1` to plot Blacksmith x64 2vCPU minutes against the advertised 3,000-minute free allowance |
| `BILLING_BLACKSMITH_ORG` | Optional GitHub org login passed to `blacksmith usage --org`; otherwise the CLI's current org is used |

Only configured providers are fetched. AWS uses boto3 with the IAM user from
`scripts/apply_aws_billing_iam.sh`; Azure uses the authenticated Azure CLI;
OpenRouter uses its official API; GitHub Actions uses the official API
through `gh`; Blacksmith uses the authenticated `blacksmith` CLI. Live usage,
balances, and ceilings do not have environment-variable overrides. See
[Affine billing map](billing.md) for the normalization and forecast semantics.

## Git status overlay

| Variable | Purpose |
| --- | --- |
| `GIT_OVERLAY_ENABLED` | Set to `0` to disable |
| `GIT_REPO_PATHS` | Optional pin list always merged into the fleet (before blacklist) |
| `GIT_REPO_BLACKLIST` | Basename or path excludes (applied to pin + scan) |
| `GIT_SCAN_ROOT` | Directory to scan for git repos (default `$HOME`) |
| `GIT_SCAN_DAYS` | Keep scanned repos with a commit in the last N days (default `14`) |
| `GIT_SCAN_MAX_DEPTH` | Max walk depth under the scan root (default `3`) |
| `GIT_SCAN_TTL_SECONDS` | Discovery cache TTL (default `300`) |
| `GIT_GAP_X` | Horizontal gap from the left screen edge |
| `GIT_GAP_Y` | Vertical gap from the top screen edge |
| `GIT_REFRESH_SECONDS` | Fetch interval (default `30`) |
| `GIT_TIMEOUT_SECONDS` | Per-repo git command timeout (default `2`) |
| `GIT_MAX_REPOS` | Max rows after severity / last-modified sort (default `6`) |
| `GIT_HIDE_CLEAN` | `1` hides clean repos |
| `GIT_INCLUDE_STASH` | `0` skips stash list |
| `GIT_DEFAULT_BRANCHES` | Default branch names for muted styling and idle-row hiding |
| `GIT_ACTIONS_ENABLED` | `0` disables the per-row GitHub Actions pip |
| `GIT_ACTIONS_TTL_SECONDS` | Cache TTL for completed Actions pips (default `180`) |
| `GIT_ACTIONS_RUNNING_TTL_SECONDS` | Cache TTL while a workflow is running (default `20`) |
| `GIT_ACTIONS_EMPTY_TTL_SECONDS` | Cache TTL when a GitHub repo has no recent runs (default `300`) |
| `GIT_ACTIONS_TIMEOUT_SECONDS` | `gh run list` timeout (falls back to `GITHUB_TIMEOUT_SECONDS`) |

See [Git status overlay](git.md) for layout, severity rules, and the rotating ticker.

## Sessions overlay

| Variable | Purpose |
| --- | --- |
| `SESSIONS_OVERLAY_ENABLED` | Set to `0` to disable |
| `SESSIONS_GAP_X` | Left offset in px; empty meets the rate limit panel's left edge |
| `SESSIONS_GAP_Y` | Bottom offset in px; empty shares the contribution skyline's baseline |
| `SESSIONS_REFRESH_SECONDS` | Fetch interval (default `20`) |

See [Sessions overlay](sessions.md) for the login-to-session join and what each element means.

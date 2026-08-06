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
| `LINEAR_DONE_LOOKBACK_HOURS` | How long completed cards stay visible |
| `LINEAR_PRIMARY_MONITOR_INDEX` | Monitor index for primary placement |
| `PRIMARY_WAIT_SECONDS` | Startup wait before placing on the primary monitor |

## Rate limit panel

| Variable | Purpose |
| --- | --- |
| `RATE_LIMIT_PANEL_ENABLED` | Set to `0` to disable |
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
| `MINECRAFT_GAP_Y` | Vertical gap from screen edge |
| `MINECRAFT_REFRESH_SECONDS` | Fetch interval |
| `MINECRAFT_STATUS_TIMEOUT_SECONDS` | TCP status probe timeout |
| `MINECRAFT_PROTOCOL_VERSION` | Protocol version for status negotiation |

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
| `GITHUB_GAP_X` | Horizontal gap from screen edge |
| `GITHUB_GAP_Y` | Vertical gap from screen edge |
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
| `WEATHER_GAP_X` | Horizontal gap from the right screen edge |
| `WEATHER_GAP_Y` | Vertical gap from the bottom screen edge |
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

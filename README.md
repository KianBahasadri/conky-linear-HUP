# Conky Linear + Codex Overlay

Desktop Conky widgets for keeping Linear work, Codex quota pressure, and Minecraft server population visible across all monitors.

## Run

```bash
./scripts/start_conky_overlays.sh
./scripts/stop_conky_overlays.sh
```

`start_conky_overlays.sh` kills prior matching overlays, starts fetch loops, and generates one Linear, Codex, and Minecraft config per detected monitor.

## Caches

- `cache/linear-cards.json`: Linear cards consumed by the Cairo renderer.
- `cache/codex-usage.json`: Codex account/window usage consumed by the Cairo renderer.
- `cache/minecraft-status.json`: Minecraft Java server status consumed by the Cairo renderer.
- `cache/conky-linear.log`: Linear fetch, launcher, and Linear Conky output.
- `cache/conky-codex.log`: Codex fetch and Codex Conky output.
- `cache/conky-minecraft.log`: Minecraft fetch, launcher, and Minecraft Conky output.
- Fetch loops refresh Linear every `180s`, Codex every `300s`, and Minecraft every `60s`.

## Linear Rules

- Card colors are stateful: green is recently completed, red is due today, cyan is normal active work.
- If any unfinished card is due today, non-due unfinished cards are hidden so urgent work dominates the overlay.
- Unfinished issues in the `Competitions` project due in the next 3 days are always shown, with their due date beside the issue id.
- Cancelled and duplicate issues are never shown.
- Recently completed cards remain visible for `LINEAR_DONE_LOOKBACK_HOURS`.

## Codex Rules

- The orange chevron marks the currently selected Codex auth file, meaning the auth file whose path resolves to `~/.codex/auth.json`.
- Multiple Codex accounts are discovered from `~/.codex/auth.json.*`; `CODEX_AUTH_PATH` forces a single auth file.
- Weekly and 5h pace markers are per account: each bar uses that window's own reset time.
- Combined usage is the average weekly `usedPercent` across accounts.
- Under pace by at least `10%` shows an amber fast-mode chip, except during the first `10%` of the weekly cycle.
- Over pace by at least `10%` shows a red warning chip, including early in the cycle.
- The pace chip is centered across the whole Codex box and uses the combined weekly pace state.

## Minecraft Rules

- The Minecraft panel uses the Java server status protocol directly over TCP.
- If `PEBBLEHOST_API_KEY` is present, the fetcher also reads PebbleHost resource stats and player names.
- PebbleHost server lookup is automatic from `MINECRAFT_SERVER`; `PEBBLEHOST_SERVER_ID` can force a specific server identifier.
- The panel is launched in the bottom-left corner by default.
- Set `MINECRAFT_OVERLAY_ENABLED=0` to disable the Minecraft overlay and its refresh loop.
- `MINECRAFT_REFRESH_SECONDS`, `MINECRAFT_GAP_X`, and `MINECRAFT_GAP_Y` can tune refresh cadence and placement.

## Config

Create `.env` from `.env.example` for Linear:

```bash
LINEAR_API_KEY=lin_api_your_key_here
LINEAR_TASK_STATES=Todo,In Progress
LINEAR_TASK_LIMIT=20
LINEAR_COMPETITION_TASK_LIMIT=50
LINEAR_DONE_LOOKBACK_HOURS=18

MINECRAFT_SERVER=51.79.35.117:25600
MINECRAFT_SERVER_LABEL=Minecraft
MINECRAFT_OVERLAY_ENABLED=1
MINECRAFT_STATUS_TIMEOUT_SECONDS=5

PEBBLEHOST_API_KEY=ptlc_your_key_here
PEBBLEHOST_SERVER_ID=
PEBBLEHOST_API_TIMEOUT_SECONDS=10
```

Codex reads local Codex auth files and refreshes expired tokens in place.

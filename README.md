# Conky Linear + Codex Overlay

Desktop Conky widgets for keeping Linear work and Codex quota pressure visible across all monitors.

## Run

```bash
./scripts/start_conky_overlays.sh
./scripts/stop_conky_overlays.sh
```

`start_conky_overlays.sh` kills prior matching overlays, starts fetch loops, generates one Linear and one Codex config per detected monitor, and logs to `cache/conky-linear.log`.

## Caches

- `cache/linear-cards.json`: Linear cards consumed by the Cairo renderer.
- `cache/codex-usage.json`: Codex account/window usage consumed by the Cairo renderer.
- Fetch loops refresh Linear every `180s` and Codex every `300s`.

## Linear Rules

- Card colors are stateful: green is recently completed, red is due today, cyan is normal active work.
- If any unfinished card is due today, non-due unfinished cards are hidden so urgent work dominates the overlay.
- Recently completed cards remain visible for `LINEAR_DONE_LOOKBACK_HOURS`.

## Codex Rules

- The orange chevron marks the currently selected Codex auth file, meaning the auth file whose path resolves to `~/.codex/auth.json`.
- Multiple Codex accounts are discovered from `~/.codex/auth.json.*`; `CODEX_AUTH_PATH` forces a single auth file.
- Weekly and 5h pace markers are per account: each bar uses that window's own reset time.
- Combined usage is the average weekly `usedPercent` across accounts.
- Under pace by at least `10%` shows an amber fast-mode chip, except during the first `10%` of the weekly cycle.
- Over pace by at least `10%` shows a red warning chip, including early in the cycle.
- The pace chip is centered across the whole Codex box and uses the combined weekly pace state.

## Config

Create `.env` from `.env.example` for Linear:

```bash
LINEAR_API_KEY=lin_api_your_key_here
LINEAR_TASK_STATES=Todo,In Progress
LINEAR_TASK_LIMIT=20
LINEAR_DONE_LOOKBACK_HOURS=18
```

Codex reads local Codex auth files and refreshes expired tokens in place.

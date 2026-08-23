# Getting started

Python fetchers, tests, and helper scripts run through
[uv](https://docs.astral.sh/uv/). Install `uv`, then from the repo root:

```bash
uv sync
./scripts/start_conky_overlays.sh
./scripts/stop_conky_overlays.sh
```

`start_conky_overlays.sh` kills prior matching overlays, starts fetch loops, and generates one Linear, rate limit panel, Minecraft, GitHub, weather, system-resource, affine-billing, git-status, and sessions config per detected monitor.

Each overlay can be disabled with its `*_OVERLAY_ENABLED=0` variable in `.env`. See [Configuration](configuration.md) for setup.

## Iterating on overlays

After editing anything under `conky/` (Lua renderers, entrypoints, or `*.conkyrc`), re-run `./scripts/start_conky_overlays.sh` so `conky/generated/*.conkyrc` is regenerated from the templates and the live Conky windows reload. This is how the user sees the change on the desktop — always do it after a conky change, then verify with `uv run python scripts/render_desktop.py` per [Desktop render](desktop-render.md) (or `--generate-only` for a headless check).

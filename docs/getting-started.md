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

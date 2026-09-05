# Getting started

Python fetchers, tests, and helper scripts run through
[uv](https://docs.astral.sh/uv/). Install `uv`, then from the repo root:

```bash
uv sync
./scripts/start_conky_overlays.sh
./scripts/stop_conky_overlays.sh
```

`start_conky_overlays.sh` stages one Linear, rate limit panel, Minecraft, GitHub,
weather, system-resource, billing, git-status, and sessions config per
detected monitor. It installs the complete set only after every config succeeds,
then replaces the owned overlay windows and fetch loops; a generation failure
therefore leaves the running desktop and last complete config set intact.

`./scripts/start_conky_overlays.sh --generate-only` only replaces the complete
generated config set. It does not stop or launch windows, stop or launch fetch
loops, or rotate logs, so it is safe to use while the live desktop is running.

The launcher installs the bundled IBM Plex fonts and computes a bounded layout
for each monitor; see [Desktop design system](design-system.md).

Each overlay can be disabled with its `*_OVERLAY_ENABLED=0` variable in `.env`. See [Configuration](configuration.md) for setup.

For GNOME login startup, run `./scripts/install_autostart.sh`. It installs a
desktop entry for the whole overlay suite with a five-second GNOME startup
delay. Rerun it if the repository moves so the absolute executable path stays
current.

## Iterating on overlays

After editing anything under `conky/` (Lua renderers, entrypoints, or `*.conkyrc`), re-run `./scripts/start_conky_overlays.sh` so `conky/generated/*.conkyrc` is regenerated from the templates and the live Conky windows reload. This is how the user sees the change on the desktop — always do it after a conky change, then verify with `uv run python scripts/render_desktop.py` per [Desktop render](desktop-render.md) (or `--generate-only` for a headless check).

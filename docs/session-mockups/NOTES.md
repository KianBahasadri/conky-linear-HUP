# Session overlay design study

Concepts for a panel showing active tmux sessions and active remote logins.
`02-patch-bay.png` shipped — see [Sessions overlay](../sessions.md) for the
overlay it became. This file is the survey it was picked from, kept for the
alternatives and the reasoning.

Render with:

```bash
uv run --with pycairo python docs/session-mockups/render_sessions.py
uv run --with pycairo python docs/session-mockups/render_annunciator.py
```

Both scripts reuse the billing study's Cairo primitives from
`../billing-mockups/trajectory_variants/render_variants.py`, so the mockups
carry the shipped overlay palette and frame treatment.

## The finding that shaped every concept

Remote access on this machine is **Tailscale SSH**, not `sshd`. There is no
TCP listener on port 22 — only `sshd-unix-local.socket`. A fetcher that greps
for `sshd` children or watches port 22 would report zero remote sessions while
one is live.

At capture time the real state was:

```
pixel-8a (android, 100.94.58.124)
  └─ pts/6 ──▶ tmux attach ──▶ session "0"
                                 └─ pane "⌘ Repo Review"  ~/clusterfork
```

Two consequences:

- `tailscale whois <ip>` resolves a tailnet address to a device name, OS, and
  account. Every concept labels inbound edges with the device name and an OS
  glyph rather than an IP.
- tmux sessions and remote logins are not two lists. `who` maps tty to remote
  host, tmux maps `client_tty` to session; joining them yields the chain above.
  The coupling is the thing worth drawing.

## Concepts

| File | Concept | Reads |
| --- | --- | --- |
| `01-patch-bay-maps.png` | Patch bay + pane micro-maps | Inbound jacks, patch cables, and a scale wireframe of each session's panes |
| `02-patch-bay.png` | Patch bay | Cables only; smallest footprint, clearest device→session read |
| `03-pane-maps.png` | Pane micro-maps | Session cards only, with an attached-from badge |
| `04-radar.png` | Ingress radar | Bearing per device, radius = staleness, sweep + blips |
| `05-patch-bay-alert.png` | Patch bay, unknown device | Alert state: dead-ended cable, red frame, master caption |
| `06-annunciator.png` | Master caution panel | Cross-cutting bonus: aggregates every overlay's alarm state |

### Pane micro-maps

`tmux list-windows -F '#{window_layout}'` returns a recursive geometry string
(`c69d,56x57,0,0,0`; `[]` stacks, `{}` splits side by side). It parses into
exact pane rectangles, so a session card can show a true-to-scale wireframe of
the real layout rather than a pane count.

### Radar geometry

Radius encodes staleness — dead centre is active now, the outer ring is the
idle horizon. Bearing comes from a golden-angle slot per device so blips spread
instead of stacking. In a shipped version the bearing should be a stable hash of
the device name with collision nudging, so a blip keeps its bearing between
frames and only walks inward or outward.

## Placement

`render_placement.py` reflows the patch bay to **456px** — the `minimum_width`
billing and weather already use — and the `render_layout_*.py` scripts composite
it, plus the [contribution skyline](../github-mockups/NOTES.md), onto a real
`scripts/render_desktop.py` frame rendered with the GitHub rail switched off.

```bash
uv run --with pycairo python docs/session-mockups/render_placement.py cache/desktop-render.png
uv run python scripts/render_desktop.py --monitor 0 --overlay linear --overlay rate-limit-panel \
  --overlay weather --overlay resource-monitor --overlay billing --overlay git -o /tmp/norail.png
uv run --with pycairo python docs/session-mockups/render_layout_v2.py /tmp/norail.png
uv run --with pycairo python docs/session-mockups/render_layout_v3.py /tmp/norail.png
```

Head 0 leaves two usable holes: the band between the Linear cards (bottom 288)
and the rate limit panel (top 769), and the right column's gap between the
resource monitor (bottom 296) and the billing map (top 630).

- `placement-right-column.png` slots the patch bay into the right column at
  `gap_x = 6`, completing the existing gauges → billing → weather stack.
- `placement-layout-v2.png` frees the left column by turning the rail into a
  skyline, but the skyline floats in the middle of the band with nothing to
  align to, and has to run at 16px per week (80%) to clear the billing map.
- `placement-layout-v3.png` is the arrangement to build. The skyline switches
  to the level lattice and lands **on the rate limit panel's top edge**, so the
  two read as one stack instead of two objects sharing a band.

### Measure the drawn panel, not the window

The rate limit panel's window is 1548px wide, but the frame it actually paints
is 1008px centred inside it (`x = 458..1466`, top edge `y ≈ 769`, with the
provider chips straddling that edge from `y = 760`). Sizing the roof to the
window would overhang the panel by 270px a side. The constants in
`render_layout_v3.py` come off a real render, measured rather than assumed.

That fixes the v2 scale problem too: matched to the drawn panel the skyline is
1008px at 17.8px per week — wider *and* larger than v2's 913px, because it no
longer has to reach across to the billing map's column.

### What the stack lines up on

- Roof deck bottom at `y = 758`, 2px above the chips.
- Roof left and right edges at the panel's, `x = 458` and `1466`.
- Patch bay right edge at `x = 458` and bottom at `y = 758`, so the bay meets
  the stack at a seam and shares its baseline — one horizontal line across the
  screen instead of three loose objects.
- Busiest day 205px tall, which puts the tallest tower at `y = 471` and leaves
  the Linear cards clear.

### Pane maps were dropped

The session that is actually live here is one window with one pane, so its
wireframe is a single empty rectangle. The map only pays for itself when
sessions differ structurally, and at overlay scale a two-pane and a three-pane
split are hard to tell apart. It costs ~38px of panel height per row.
`02-patch-bay.png` is the instrument; `01` and `03` are kept as the record.

## Implementation notes carried out of the study

- `pane_current_command` returned empty for the captured pane under tmux 3.7c
  (the child process had renamed itself). Prefer `pane_title`, then fall back to
  walking `pgrep -P #{pane_pid}`.
- `JetBrains Mono` is not installed here; fontconfig resolves it to
  `Noto Sans Mono`, which has no `⌘` glyph. Pane titles need a coverage check or
  a substitution before they reach Cairo.
- An inbound device with no tailnet identity is the state worth making loud.
  The alert variant is the argument for a known-device allowlist.

## Illustrative values

Session `0` and the `pixel-8a` edge are real. The `build` and `notes` sessions,
the `azure` idle edge, and the `10.0.0.99` unknown device are invented so the
panels show a populated layout and their alert states.

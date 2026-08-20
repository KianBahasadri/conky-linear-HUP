# Desktop render

`scripts/render_desktop.py` draws the overlays to a PNG without screenshotting
anything. It needs no X display, no compositor, and no running Conky, so an
agent can see what the desktop looks like on its own.

```bash
./scripts/render_desktop.py                     # whole virtual desktop
./scripts/render_desktop.py --monitor 0         # one monitor, cropped
./scripts/render_desktop.py --overlay weather   # one overlay (repeatable)
./scripts/render_desktop.py --list              # window table, no render
./scripts/render_desktop.py --check             # model vs the live X windows
```

Output defaults to `cache/desktop-render.png`; `-o` puts it elsewhere.
`--scale 0.5` halves the output, `--background RRGGBB[AA]` replaces the opaque
black ground, and `--monitors WxH+X+Y[,...]` overrides the detected layout.

This is not a mockup. It loads the shipped Lua renderers and the current
contents of `cache/`, so it shows the same pixels and the same data as the live
overlays.

## How it works

1. Every `conky/generated/*-overlay-*.conkyrc` is parsed for its alignment,
   gaps, minimum size, `xinerama_head`, entrypoint and draw hook. Configs whose
   draw hook no longer exists (leftovers from a removed overlay) are skipped
   with a note on stderr.
2. `scripts/render_desktop.lua` evaluates each self-sizing panel's
   `${lua_parse ..._height_spacer}` so the tool knows how tall those windows
   grow.
3. Each window is placed on the virtual desktop (see below).
4. The Lua worker draws every overlay into its own transparent image surface —
   the stand-in for its ARGB Conky window — then composites them over the
   background in launch order, so later overlays land on top.

Steps 2 and 4 run under a Lua interpreter matching Conky's compiled Cairo
binding (usually `lua5.4` with `/usr/lib/conky/libcairo.so`). Both are found
automatically from `conky --version`; set `CONKY_LUA_CPATH` to a `?.so` pattern
if they live somewhere unusual.

## Window geometry

`gap_x`/`gap_y` are measured from the monitor edge to the window's *text area*,
and the window then extends `border_inner_margin + border_outer_margin +
border_width` further out on every side — 4px for these configs, since they set
only `border_width = 0` and inherit Conky's other defaults.

A panel that grows itself with a `${voffset N}` spacer ends up with a text area
of `max(minimum_height, N + one line height)`. That line height is the
`TEXT_LINE_HEIGHT_PX` constant in the script, calibrated for
`JetBrains Mono:size=10`; rerun `--check` after changing the overlay font.

`--check` matches each modelled window against the live X windows and prints
the offsets. All overlays match exactly except the git panel, which is the only
one using `own_window_type = 'normal'` (see
[Conky windows and input](conky-windows-and-input.md)) and so is positioned by
the window manager rather than by Conky — it lands a few pixels off, and on the
primary monitor it is pushed below the GNOME top bar.

## Monitor layout

Detected with `xrandr --listmonitors` and cached to `cache/monitor-layout.json`.
With no display reachable, the cached layout is used, which is what lets the
tool run headless; `--monitors` overrides both.

## Renderer contract

A renderer must take its surface from `shared.create_surface()`, which prefers
the `conky_surface()` global that both Conky and this tool provide. Building an
Xlib surface directly works only under a real Conky and segfaults here on the
nil display, so the worker replaces `cairo_xlib_surface_create` with a stub that
raises instead.

The generated configs are gitignored. On a fresh clone, run
`./scripts/start_conky_overlays.sh --generate-only` before the first render.

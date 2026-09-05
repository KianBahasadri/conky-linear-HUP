# Desktop render

`scripts/render_desktop.py` draws the overlays to a PNG without screenshotting
anything. It needs no X display, no compositor, and no running Conky, so an
agent can see what the desktop looks like on its own.

```bash
uv run python scripts/render_desktop.py                     # whole virtual desktop
uv run python scripts/render_desktop.py --monitor 0         # one monitor, cropped
uv run python scripts/render_desktop.py --overlay weather   # one overlay (repeatable)
uv run python scripts/render_desktop.py --list              # window table, no render
uv run python scripts/render_desktop.py --check             # model vs the live X windows
```

Output defaults to `cache/desktop-render.png`; `-o` puts it elsewhere.
Completed renders atomically replace the output while preserving an existing
file's mode and following an existing output symlink to its regular-file target.
`--scale 0.5` halves the output (the factor must be finite and positive),
`--background RRGGBB[AA]` replaces the opaque
black ground, and `--monitors WxH+X+Y[,...]` overrides the detected layout;
signed coordinates such as `1920x1080-1920+0` are accepted.

This is not a mockup. It loads the shipped Lua renderers and the current
contents of `cache/`, so it shows the same pixels and the same data as the live
overlays.

## How it works

1. Every `conky/generated/*-overlay-*.conkyrc` is parsed for its alignment,
   gaps, minimum size, `xinerama_head`, entrypoint and draw hook. Configs whose
   draw hook no longer exists (leftovers from a removed overlay) are skipped
   with a note on stderr.
2. `scripts/render_desktop.lua` checks draw hooks and can still evaluate a
   legacy `${lua_parse ..._height_spacer}`. Current templates use explicit
   bounded sizes from the launcher and have empty text blocks.
3. Each window is placed on the virtual desktop (see below).
4. The Lua worker draws every overlay into its own transparent image surface —
   the stand-in for its ARGB Conky window — then composites them over the
   background in launch order, so later overlays land on top.

Steps 2 and 4 run under a Lua interpreter matching Conky's compiled Cairo
binding (usually `lua5.4` with `/usr/lib/conky/libcairo.so`). Both are found
automatically from `conky --version`; set `CONKY_LUA_CPATH` to a `?.so` pattern
if they live somewhere unusual.

## Window geometry

All current templates use `top_left` alignment with explicit monitor-local
`gap_x` and `gap_y`. They set `border_inner_margin`, `border_outer_margin`, and
`border_width` to zero, so modelled content and window rectangles are identical.
The composition planner is documented in [Desktop design system](design-system.md).

The parser retains support for legacy configs with Conky's default margins
and `${voffset}` sizing. Its 19px legacy text-line constant describes the old
JetBrains Mono spacer configs; current windows have no spacer text.

`--check` compares modelled sizes and positions with live X windows. Git is
still the sole `normal` window and its window-manager offsets are diagnostic;
size and presence remain checked. In the redesigned three-monitor layout,
all 24 window rectangles were verified to match, including git.

## Monitor layout

Detected with `xrandr --listmonitors` and cached to `cache/monitor-layout.json`.
With no display reachable, the cached layout is used, which is what lets the
tool run headless; `--monitors` overrides both. Cached and overridden layouts
are validated before geometry is calculated, and live layout updates replace
the cache atomically so an interrupted write cannot leave a partial layout.

## Renderer contract

A renderer must take its surface from `shared.create_surface()`, which prefers
the `conky_surface()` global that both Conky and this tool provide. Building an
Xlib surface directly works only under a real Conky and segfaults here on the
nil display, so the worker replaces `cairo_xlib_surface_create` with a stub that
raises instead.

The generated configs are gitignored. On a fresh clone, run
`./scripts/start_conky_overlays.sh --generate-only` before the first render.

The output PNG is staged and checked before it replaces the previous render.
If the Lua worker crashes before finishing the file, the last complete PNG is
left in place instead of being mistaken for the new render.

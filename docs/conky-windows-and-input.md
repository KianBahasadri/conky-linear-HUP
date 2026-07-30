# Conky windows and input

Conky is a passive desktop overlay: it draws and refreshes. There are no click handlers, tabs, focus models, or show/hide APIs in this repo’s Lua renderers.

## Separate windows

Each overlay is its own Conky process and X window (`own_window = true`, usually `own_window_type = 'desktop'` with `undecorated,below,sticky,skip_taskbar,skip_pager`). Linear and the rate limit panel share the same `gap_x` and width and nearly the same `gap_y`, so they stack on top of each other.

## Why clicks appear to toggle panels

Clicking Linear cards vs the rate limit panel can raise one window over the other. That is window-manager stacking (and click-through on transparent pixels), not Conky interactivity. Opaque drawn pixels can receive the click; transparent areas often pass through to the window underneath.

## Fake tabs via overlapping windows (future note)

Overlapping Conky windows can approximate tabs: click a visible opaque region, the WM raises that window, others look hidden. This is fragile:

- No real tab state, active styling, or exclusive selection
- Behavior depends on the WM/compositor and on `desktop` / `below` hints
- Transparent hit areas pass clicks through; opaque art must cover intended click targets
- Each tab costs another Conky process and redraw loop

For intentional tabbing later, prefer something that owns input (a small GTK/Qt/EWW widget, or one Conky plus an external click tool that writes a state file the renderer reads). Do not treat stacked Conky windows as a designed UI.

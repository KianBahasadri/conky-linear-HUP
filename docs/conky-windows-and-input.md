# Conky windows and input

Conky is a passive desktop overlay: it draws and refreshes. There are no click
handlers, tabs, focus models, or show/hide APIs in the Lua renderers.

Each overlay is a separate Conky process and X window. The launcher gives them
non-overlapping regions per the [Desktop design system](design-system.md).
The usual window type is `desktop`, with
`undecorated,below,sticky,skip_taskbar,skip_pager` hints.

Every template explicitly selects `output_backend = 'x11'`, so GNOME Wayland
sessions use Xwayland. Conky 1.25 otherwise selects native Wayland automatically;
the 1.25.2 build crashes here in `display_output_wayland::set_font`, and GNOME
lacks the layer-shell protocol needed for native desktop overlay placement.
Keep the backend explicit when adding templates. See Conky's
[output backend settings](https://conky.cc/config_settings#output_backend).

The git overlay retains `own_window_type = 'normal'` plus `below`: under
GNOME/Xwayland the desktop layer previously failed to composite that window
at the leftmost monitor edge. Its placement is therefore owned by the window
manager; `render_desktop.py --check` reports any positional offset separately.

Clicking opaque drawn pixels may affect window-manager stacking; transparent
pixels may pass clicks through to another window. This is not a UI interaction.
The earlier overlapping Linear/quota windows could appear to toggle when
clicked. The coordinated layout removes that accidental overlap.

Intentional interaction would require a runtime that owns input, such as
GTK/Qt/EWW, or an external input handler and explicit state. Do not implement
fake controls or tabs by overlapping passive Conky windows.

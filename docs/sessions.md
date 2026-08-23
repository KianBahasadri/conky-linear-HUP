# Sessions overlay

A Drift patch bay: height is time. Fresh origins float at the top of the
field, stale ones sink, and a taut line connects every live login to the tmux
session it is driving. Idle origins show a short sag, unresolved remotes a
broken red stub. It answers "who is on this machine, what are they attached
to, and how stale is it" in one read. The concept survey it came out of,
including the alternatives that were not built, is the
[session overlay design study](session-mockups/NOTES.md).

## The finding the panel is built around

Remote access here is **Tailscale SSH**, not `sshd`. There is no TCP listener on
port 22 — only `sshd-unix-local.socket`. Anything that greps for `sshd` children
or watches port 22 reports zero remote sessions while one is live. The footer
states which of the two is actually open.

The join that does work:

```
who               tty  -> origin address
tmux list-clients tty  -> session name
tailscale status  addr -> device name, OS
```

`who` gives the origin, tmux gives the session, and the tty is the key between
them. That chain — device, then session — is the thing the panel draws.

## Data

`scripts/fetch_sessions.py` → `cache/sessions.json`, with two arrays:

- `devices`: one per inbound login. `name` is the tailnet device where the origin
  resolves to a peer, otherwise the tty (local) or the raw address (unknown).
  `state` is `live` (driving a session), `idle` (no session), or `alert`.
  `age` is a human string and `ageSeconds` is the numeric login age that drives
  the drift.
- `sessions`: one per tmux session, with window and pane counts, working
  directory, which devices are attached, and `idle` / `idleSeconds` for the
  time since that session last had activity.

`tailscale status --json` is called once, not per address, and only device names
and OS strings are taken from it. The tailnet account identity in that payload is
deliberately left alone.

Two cases worth knowing:

- **tmux's own panes appear in `who`**, registered with utmp as `tmux(PID).%N`.
  They are not inbound logins, and counting them as unidentified remotes turns
  the whole panel red the moment a tmux server starts, so they are dropped.
- **A remote login with no tailnet identity** is the state worth making loud. It
  gets the `alert` state, which switches the panel's accent to red and draws a
  warning glyph instead of a device icon.

With no tmux server running the sessions column says so rather than going blank;
that is the normal state between sessions, not an error.

## Placement

Alignment is **`bottom_left`**. The panel is 360px wide and occupies the lower-left
column below the Git status panel. Its default `gap_x` is 20px and its default
`gap_y` is 14px, leaving a small screen margin while keeping the tall rail clear
of the top Linear cards.

The renderer is the Drift instrument. It is transparent like the [Affine
billing map](billing.md) — no outer frame, panel fill, or card background.
Height *is* time: a fresh login floats at the top of the field and a stale
one sinks toward the bottom on a log scale (0 to 48h). A live login that is
driving a session sinks with that session's `idleSeconds` instead of its own
`ageSeconds`, so an old but active session stays high.

The window self-sizes through `${lua_parse sessions_height_spacer}`, the same
mechanism the [rate limit panel](rate-limit-panel.md) uses. Because it is
bottom-anchored the field grows upward. The field is a fixed 358px drift at
minimum; an extra row of tmux destinations beyond three will make the window
taller than its 760px minimum, and the socket row is hidden entirely when no
tmux server is running. Only real tmux sessions produce diamonds — empty
placeholder sockets are never drawn, so a single session shows a single
diamond, not a padded row of three. `minimum_height` is seeded at launch from
`fetch_sessions.py --print-overlay-height`.

| Variable | Purpose |
| --- | --- |
| `SESSIONS_OVERLAY_ENABLED` | `0` disables overlay + fetch loop |
| `SESSIONS_GAP_X` | Left offset in px (default `20`) |
| `SESSIONS_GAP_Y` | Bottom offset in px (default `14`) |
| `SESSIONS_REFRESH_SECONDS` | Fetch interval (default `20`) |

See [Configuration](configuration.md) for the full variable table.

## Reading the panel

| Element | Meaning |
| --- | --- |
| Height | Freshness. Top is now, bottom is stale (sunk). Three faint isobars are only depth guides. |
| Dot | Ingress origin. Filled green is live and driving a session, hollow dim is idle, filled red is an unresolved remote. Known devices show a glyph-derived icon instead of a dot — `phone` for Android/iOS (e.g., Pixel 8a) and `laptop` for `terminal`/`laptop`/`monitor` (e.g., `tty2`, linux/macOS). Unknown origins fallback to a plain dot; alerts always stay as a red dot + X. Icon stroke/fill still encodes the state. |
| Diamond | Tmux destination. Filled green has a client attached, hollow dim is open. No empty placeholder diamonds are drawn — the strip shows exactly one diamond per tmux session. |
| Thread | Live is a taut green line from dot to its diamond. Idle is a short dim sag that stops in the field. Alert is a short red stub that ends in an X and never reaches a diamond. |
| Footer | How many live vs idle origins, whether any are unresolved, and whether `sshd` is listening. |

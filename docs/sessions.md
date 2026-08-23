# Sessions overlay

A patch bay: inbound logins on the left, tmux sessions on the right, and a patch
cable for every login that is driving one. It answers "who is on this machine and
what are they attached to" in one read. The concept survey it came out of,
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
- `sessions`: one per tmux session, with window and pane counts, working
  directory, and which devices are attached.

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

The window self-sizes through `${lua_parse sessions_height_spacer}`, the same
mechanism the [rate limit panel](rate-limit-panel.md) uses. Because it is
bottom-anchored it grows *upward* as devices and sessions appear. The live layout
keeps three source rows and three destination sockets visible, with a 760px
minimum height; additional rows extend the window upward. `minimum_height` is
seeded at launch from `fetch_sessions.py --print-overlay-height`.

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
| Device glyph | Phone, laptop, monitor or console, from the peer's OS; a warning triangle for an unidentified remote |
| Jack | Lit when that login is attached to a tmux session, dark when it is not |
| Cable | Which session the login is driving; the beads ride from the jack toward the card |
| Card stripe | Green while a session has a client attached, dim once every client detaches |
| Footer | Whether `sshd` is listening, next to the Tailscale SSH path that actually carries the logins |

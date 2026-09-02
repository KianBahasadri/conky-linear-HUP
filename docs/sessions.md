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
or watches port 22 reports zero remote sessions while one is live.

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
  time since that session last had activity. Each session also carries flat
  `codeview*` fields (see [Codeview moons](#codeview-moons)).

`tailscale status --json` is called once, not per address, and only device names
and OS strings are taken from it. The tailnet account identity in that payload is
deliberately left alone. The cache also records whether `sshd` is listening for
diagnostics; the transparent patch bay does not render a separate status footer.

Three cases worth knowing:

- **tmux's own panes appear in `who`**, registered with utmp as `tmux(PID).%N`.
  They are not inbound logins, and counting them as unidentified remotes turns
  the whole panel red the moment a tmux server starts, so they are dropped.
- **A remote login with no tailnet identity** is the state worth making loud. It
  gets the `alert` state, which switches the panel's accent to red and draws a
  warning glyph instead of a device icon.
- **The local VT (`tty2`) is filtered** — it sits `2d` idle and would sink to the
  bottom while its Kittty `pts/*` clients drive `tmux` on `xterm-kitty`. `who`
  never lists those `pts/N` as logins, so the `tty`→`session` join misses them.
  `fetch_sessions.py` instead synthesizes a `laptop` ingress per orphan `tmux`
  client (`pts/1`, `pts/8`, …) using the tailnet Self HostName (`kianWorkLaptop`)
  and the session's `idleSeconds` so the dot floats at the top and the diamond
  fills green.

With no tmux server running the sessions column says so rather than going blank;
that is the normal state between sessions, not an error.

## Codeview moons

Each session diamond can wear a moon: the mark of a running codeview dashboard
daemon for that session's repo (codeview is clusterfork's per-repo introspection
dashboard; the design study is
[codeview-mockups/codeview-moon-gallery.html](codeview-mockups/codeview-moon-gallery.html)).

`fetch_sessions.py` probes `<repo>/.codeview/daemon.json` once per distinct
session path per cycle, walking up from the pane's working directory so a pane
parked in a subdirectory still finds the repo root. A daemon counts as running
only if the recorded pid answers and its cmdline still looks like the codeview
server — the same test `bin/codeview status` uses. The per-session cache fields
are `codeviewPresent`, `codeviewRunning`, `codeviewPort`, and
`codeviewIndexAgeSeconds` (age of the newest file under
`.codeview/cache/`, `-1` when unknown).

A moon survives its session closing. Each cycle also probes the fleet list
(the git panel's `cache/git-repo-discovery.json`, with a shallow `$HOME` scan
as fallback) for any repo with a `.codeview/daemon.json`. A repo whose tmux
session is gone still shows in the bay as an unattached destination diamond —
tinted with the repo's fleet color, wearing the same moon the session diamond
would — so a serving dashboard is never hidden just because its session ended.
`SESSIONS_CODEVIEW_REPO_PATHS` pins extra roots and `SESSIONS_CODEVIEW_SCAN_ROOT`
overrides the scan root.

What the moon shows:

- **Orbiting moon** (tinted with the repo's fleet color, same hash as the
  diamond and filaments) — the dashboard daemon is serving.
- **Phase** — full under 30 minutes of index age, gibbous under 2 hours,
  crescent beyond; a rescan or `codeview reload` resets it to full. The moon
  dims with the phase.
- **Eclipse** — a dark parked moon with a red rim on a broken ring: the daemon
  died but `daemon.json` is still there. No moon at all means the repo has no
  dashboard.

Motion: the moon's angle is `os.time() / 420s × 360°`, recomputed on every
Cairo draw, so nothing accumulates across redraws or restarts. The sessions
window ticks at `update_interval = 1` (in `conky/sessions-overlay.conkyrc`),
which advances the orbit ~0.86° (about a quarter pixel) per frame — a
continuous slow drift rather than visible steps. The fetch loop stays on its
own 20 s timer; the 1 s tick only costs redraws (≤ 0.5 % CPU observed).
Orbit direction flips per repo name hash so neighboring moons diverge.

## Placement

Alignment is **`bottom_left`**. The panel is 440px wide, flush with the left edge,
and occupies the lower-left area below the Git status panel. Its default `gap_x`
is 4px and its default `gap_y` is 6px, using the full collision-free gutter before
the rate-limit panel.

The renderer is the Constellation instrument. It is transparent like the [Affine
billing map](billing.md) — no outer frame, panel fill, or card background.
Height *is* time: a fresh login floats at the top of the field and a stale
one sinks toward the bottom linearly (0 to 48h). A live login that is
driving a session sinks with that session's `idleSeconds` instead of its own
`ageSeconds`, so an old but active session stays high. Origins are stars on
a faint starfield spanning the full transparent bay — glowing phone/laptop
icons for known devices (with a soft halo), plain star dots otherwise — linked
by glowing constellation filaments to their destination diamonds. Micro-stars add
depth; idle origins show a short fading tail, alerts
a red burst, with a 24px clear margin at the top and a 48px clear margin at the bottom. Destination diamonds are arranged in staggered formation across rows so no diamond sits directly above or below another, filaments curve around intermediate diamonds to prevent clipping, and a faint dashed arc links the
session diamonds.

The window self-sizes through `${lua_parse sessions_height_spacer}`, the same
mechanism the [rate limit panel](rate-limit-panel.md) uses. Because it is
bottom-anchored the field grows upward. The expanded drift field fills the lower-left space below Git, and destinations
are bottom-aligned within their zone. Ingress points use a substantial 72px
vertical inset while preserving the same lower drift endpoint. An extra row of
tmux destinations beyond three will make the window taller than its 790px
minimum, and the socket row is hidden entirely when no
tmux server is running. Only real tmux sessions produce diamonds — empty
placeholder sockets are never drawn, so a single session shows a single
diamond, not a padded row of three. `minimum_height` is seeded at launch from
`fetch_sessions.py --print-overlay-height`.

See [Configuration](configuration.md#sessions-overlay) for the variable
defaults and complete inventory.

## Reading the panel

| Element | Meaning |
| --- | --- |
| Height | Freshness. Top is now, bottom is stale (sunk). |
| Star / icon | Ingress origin on the starfield. Glowing phone (`phone`/Pixel) or laptop (`terminal`/`laptop`/`monitor`/`tty*`) for known devices, plain star dot otherwise; filled green is live, hollow dim is idle, filled red with burst is unresolved. Halo and fill encode state. |
| Diamond | Tmux / fleet codeview destination. Glowing filled green when attached, hollow dim when open. No empty placeholder diamonds — exactly one per active session or serving codeview dashboard. A faint dashed arc links them. |
| Filament | Live is a glowing constellation line from icon/star to its diamond, kissing each edge. Idle is a short fading tail. Alert has no filament — its burst sits at the star. |
| Moon | Codeview dashboard daemon for the repo. Orbiting = serving (tint = repo color), phase = index age, dark parked moon with red rim = dead daemon, absent = no dashboard. See [Codeview moons](#codeview-moons). |

# Sessions overlay

The left rail lists inbound logins and tmux sessions with explicit connection,
idle, and codeview states. Names, destinations, ages, windows, and panes are
readable as aligned text. The former constellation is preserved in the
[session design study](session-mockups/NOTES.md). Shared styling and bounded
paging are owned by the [Desktop design system](design-system.md).

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
  `age` is a human string and `ageSeconds` is the numeric login age for the readout.
- `sessions`: one per tmux session, with window and pane counts, working
  directory, which devices are attached, and `idle` / `idleSeconds` for the
  time since that session last had activity. Each session also carries flat
  `codeview*` fields (see [Codeview status](#codeview-status)).

`tailscale status --json` is called once, not per address, and only device names
and OS strings are taken from it. The tailnet account identity in that payload is
deliberately left alone. The cache also records whether `sshd` is listening for
diagnostics; the list does not render a separate status footer.

Three cases worth knowing:

- **tmux's own panes appear in `who`**, registered with utmp as `tmux(PID).%N`.
  They are not inbound logins, and counting them as unidentified remotes turns
  the whole panel red the moment a tmux server starts, so they are dropped.
- **A remote login with no tailnet identity** is the state worth making loud. It
  gets the `alert` state and a square `Unknown remote` danger badge.
- **The local VT (`tty2`) is filtered** — it sits `2d` idle and would sink to the
  bottom while its Kittty `pts/*` clients drive `tmux` on `xterm-kitty`. `who`
  never lists those `pts/N` as logins, so the `tty`→`session` join misses them.
  `fetch_sessions.py` instead synthesizes a `laptop` ingress per orphan `tmux`
  client (`pts/1`, `pts/8`, …) using the tailnet Self HostName (`kianWorkLaptop`)
  and the session's `idleSeconds` for its activity age.

With no tmux server running the sessions column says so rather than going blank;
that is the normal state between sessions, not an error.

## Codeview status

The list retains per-repo codeview daemon status (codeview is clusterfork's
introspection dashboard). The former moon treatment is archived in the
[codeview study](codeview-mockups/codeview-moon-gallery.html).

`fetch_sessions.py` probes `<repo>/.codeview/daemon.json` once per distinct
session path per cycle, walking up from the pane's working directory so a pane
parked in a subdirectory still finds the repo root. A daemon counts as running
only if the recorded pid answers and its cmdline still looks like the codeview
server — the same test `bin/codeview status` uses. The per-session cache fields
are `codeviewPresent`, `codeviewRunning`, `codeviewPort`, and
`codeviewIndexAgeSeconds` (age of the newest file under
`.codeview/cache/`, `-1` when unknown).

A codeview record survives its tmux session closing. Each cycle probes the
fleet list (with a shallow home scan fallback), so a discovered dashboard
remains visible as a `Dashboard` row even when no tmux session remains.
`SESSIONS_CODEVIEW_REPO_PATHS` pins extra roots and `SESSIONS_CODEVIEW_SCAN_ROOT`
overrides the scan root.

Each record is two lines: its name with a state badge, then its detail at the
left and its note at the right. A login's detail is its origin and destination
session with the login age; a session's is its window and pane counts with idle
time. The note says `Codeview serving` with the index age, or `Codeview stopped`
when a recorded daemon no longer runs. A serving index at least two hours old
uses caution text; a stopped daemon uses danger text. Sessions without codeview
show their attached device or working directory instead.

## Placement

Sessions occupy the left rail below repositories. Logins precede session rows;
attached sessions remain first in the fetcher's ordering. The allocated region
stays fixed until restart, and additional records rotate without overlapping
the neighboring windows. Fetching remains on its independent 20-second timer.
See [Configuration](configuration.md#sessions-overlay) for position overrides.

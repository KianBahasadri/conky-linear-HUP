# Sessions in the repository panel

Sessions and CodeView status share the top-left repository list. A repository
appears once with its Git health and session presence. The former constellation is preserved in the
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

`conky/repository-presence.lua` joins these records to the visible Git fleet.
A session path matches the longest enclosing repository path; a unique `repo`
name is the fallback when paths are unavailable. Equal basenames with distinct
paths remain separate. A dashboard record with zero windows contributes
CodeView state but does not count as a tmux session. Glyphs come from the device
records: split the session's comma-joined `attached` field and look up each name.

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

With no sessions, the repository list remains visible without device marks.
Missing or failed session data gets an explicit `Sessions` / `Unavailable` row;
it does not erase Git data or imply that there are no sessions.

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
remains visible even when no tmux session remains.
`SESSIONS_CODEVIEW_REPO_PATHS` pins extra roots and `SESSIONS_CODEVIEW_SCAN_ROOT`
overrides the scan root.

## Reading presence

Attached devices show neutral Lucide laptop, phone, or monitor glyphs sitting
horizontally next to the CodeView glyph in the row's presence section on the right,
eliminating the left gutter. A terminal glyph stands for a session with no resolved
device. Up to three device glyphs sit side-by-side; after three glyphs, a `+n`
count represents any others. Devices sharing a name are drawn once per repository.

The metadata shows time since session activity. Running CodeView has an open
Lucide eye with the index age beside it; stopped CodeView has a closed eye with
no status text. Neither `tmux`, `cv`, nor `off` is printed. Eyes and index ages
always use neutral grey, including old indexes. CodeView age does not trigger
a yellow or red treatment. Unknown
ages say `unknown`, while zero activity says `0s`.

For several sessions in one repository, `2× 1m` means two sessions with the most
recent activity one minute ago. Individual session names, window counts, and
pane counts are omitted from joined repository rows. They remain in the cache.

Settled rows normally take 18px and rows with Git badges 44px. Crowded metadata
can add lines. Branches truncate first, preserving the Git
counts and presence; counts wrap as complete tokens when necessary. Repository
health badges retain the ordering described in [Git status](git.md).

Logins driving no session, sessions outside the visible Git fleet, and orphan
dashboards follow the repositories after an 8px gap. Session names remain on
these unmatched rows. Unknown remote logins retain their square danger badge,
even when they are attached to a session already shown in a repository row.

## Placement

When Git and sessions are enabled, the launcher creates one Git window per
monitor and removes the previous standalone sessions configs. It allocates that
window from the joined cache records, with the left rail available down to
Minecraft when enabled. Cairo measures the actual rows and rotates whole records
in 30-second pages if the fixed allocation fills. Session data is reread each
draw and fetching remains on its independent 20-second timer.

Disabling session data leaves the Git list without presence. If Git is disabled,
the legacy standalone sessions renderer remains available at the bottom left;
it retains its original detailed rows. See
[Configuration](configuration.md#sessions-overlay) for enablement and position overrides.

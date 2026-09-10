# Workout data source

Decision record for how run workouts get from the phone to this machine.
`fetch_workouts.py` parses the uploaded TCX files into
`cache/workouts-status.json`, which feeds the training section of the
[weather and running overlay](weather.md). The phone app supports upload to: a
local file, Dropbox, Endurain, Runalyze, RunKeeper, Strava, and WebDAV.

## Decision

WebDAV, served from this machine. `rclone serve webdav` (rclone is installed at
`/usr/bin/rclone`) serves the workouts directory on loopback, run as a systemd
system service so it survives reboots, and `tailscale serve --https=443` fronts
it to the tailnet at `https://kianlaptop.tail3a78b9.ts.net/` with a real
Let's Encrypt certificate. The HTTPS front door exists because Android's
cleartext-HTTP policy blocks RunnerUp's uploads (see Phone clients); Material
Files is the only client that could use plain HTTP. `tailscale serve` is
tailnet-only — Funnel is the public-internet variant, and it is not used.

Because uploads land directly on this machine's disk, the fetcher needs no
network code at all — it just globs the local directory. The phone can reach
the server over Tailscale; SSH access is irrelevant since the app speaks HTTP,
but Tailscale makes it reachable.

## Options considered

- **WebDAV (chosen)** — plain HTTP with basic auth, no OAuth ceremony, no
  external account. Only one-time cost is a small systemd service.
- **File** — even simpler data (local GPX export), but needs something like
  Syncthing to move files off the phone automatically.
- **Dropbox** — easy push from the phone (one tap, existing OAuth), 2 GB free
  is far more than GPX files need (~200 KB each). Rejected because the pull
  side is heavier: creating a developer app, an OAuth authorize dance on a
  headless box (`rclone authorize "dropbox"` needs a browser), and the fetcher
  gains a network dependency plus token management.
- **Strava** — richest, most structured API, but OAuth2 refresh plus rate
  limits make it the most annoying option for a desktop panel.
- **RunKeeper** — API access is gated behind app approval.
- **Runalyze** — API is poorly documented.
- **Endurain** — easy only if self-hosted, which adds infrastructure for no
  gain here.

## Future option: offsite backup

If cloud backup is wanted later, rclone can sync the local workouts directory
to Dropbox independently of the upload path. This keeps the phone-side flow and
the fetcher untouched.

## Setup

This laptop runs the root-managed system unit
`/etc/systemd/system/rclone-workouts.service`, enabled at boot. It serves
`127.0.0.1:9876` as the dedicated `rclone-workouts` account, without
administrative groups. `ProtectHome=tmpfs` hides the home directories; a scoped
bind exposes only `/home/kian/conky-linear-HUP/cache/workouts` at
`/srv/rclone-workouts` inside the service. This includes the `weight/`
subdirectory and its uploaded ZIP. The service also uses seccomp,
`NoNewPrivileges`, and network access restricted to IPv4 loopback.

The original file contents and host paths were preserved. Workout files are
owned by the service account, with named `kian` read/write ACLs; directory
default ACLs give new uploads the same host access. `kian` can still read, edit,
and manage the files. The service can update file contents and modification
times during ordinary WebDAV operations.

The HTTPS listener remains `tailscale serve`, configured separately from the
unit to proxy to `http://127.0.0.1:9876`. Manage the backend with:

```bash
systemctl status rclone-workouts.service
sudo systemctl restart rclone-workouts.service
journalctl -u rclone-workouts.service
```

The previous `rclone-webdav.service` user unit is disabled. Its definition is
retained in the rollback snapshot and at `systemd/rclone-webdav.service`.
`scripts/install_webdav_service.py` checks for the managed system unit before
changing authentication, environment files, or user units. If it is active,
the installer reports the preserved phone setup and exits successfully. If it
exists but is inactive, the installer exits with instructions to run
`sudo systemctl start rclone-workouts.service`; it does not fall back to the
legacy user unit. On systems without the managed unit, the installer retains
its original user-service setup behavior.

Moving this repo requires an administrator to update the system unit's bind
source, reload systemd, and restart the service. Rerunning the user installer
does not change that root-managed path. `WEBDAV_PUBLIC_URL` only overrides the
phone URL printed by the installer; it does not reconfigure Tailscale Serve.

Authentication still uses the original bcrypt htpasswd entry, copied unchanged
to `/etc/rclone-workouts/webdav.htpasswd`. Systemd passes it to the service
through `LoadCredential`. The original `~/.config/rclone/webdav.htpasswd` and
the plaintext phone credential at `~/.config/rclone/webdav-password.txt`
(`0600`) remain in place. The phone username and password did not change.

Credential rotation now requires an administrator to replace the root-managed
htpasswd entry and restart `rclone-workouts.service`, keeping the saved client
credential and phone configuration consistent. Deleting the legacy files alone
does not rotate the active service's credential.

Migration checks verified the existing credentials through the HTTPS URL and
PUT, GET, host editing, overwrite, MOVE, and DELETE in both the root directory
and `weight/`. They also verified that unrelated home paths are hidden and the
service has no administrative groups. These were automated service checks;
they did not exercise the phone apps' interfaces.

The phone apps talk to `https://kianlaptop.tail3a78b9.ts.net/` with the `kian`
login from the password file above. (Before the serve front door existed, the
bare `http://kianlaptop:9876/` MagicDNS URL also worked for cleartext-tolerant
clients.)

## Phone clients

- **RunnerUp** (the workout uploader) — its plain-HTTP requests never reached
  the server: Android's cleartext-HTTP policy makes the HTTP stack abort
  before sending a packet, and RunnerUp does not opt in to cleartext. Working
  over the `tailscale serve` HTTPS front door; TCX chosen as the upload format
  for its structured laps.
- **Material Files** — verified end to end (browse, PROPFIND, PUT, GET) over
  plain HTTP before the HTTPS pivot; cleartext-tolerant, unlike RunnerUp. It
  does not expose its WebDAV remotes through SAF, so other apps cannot write
  into them (the maintainer declined a DocumentsProvider in issue #191).

The system service logs at `INFO`; inspect it with
`journalctl -u rclone-workouts.service`. It no longer uses the legacy unit's
`-vv` request logging, so absent log entries alone do not establish where an
upload failed. Check the HTTP response and the HTTPS path as well as service
status when diagnosing phone uploads.

## Weight backups from openScale

The same WebDAV server exposes `cache/workouts/weight/` at
`https://kianlaptop.tail3a78b9.ts.net/weight/` for openScale files. Prepare this
directory through WebDAV when setting up another server so it receives the
server's upload ownership and access rules described under [Setup](#setup).

In [RSAF](https://github.com/chenxiaolong/RSAF) on Android, add a remote named
`Weight`, select WebDAV with vendor `rclone`, enter that URL and the existing
WebDAV credentials, and leave the bearer token empty. RSAF exposes the remote
through Android's system folder picker, where it can be selected as openScale's
backup location. Tailscale must be connected and the laptop reachable for
remote file operations.

`scripts/fetch_weight.py` reads the newest uploaded ZIP by file modification
time. It supports the openScale 3 database schema, joining measurements and
values to the `WEIGHT` type by key. Values already use the unit configured in
openScale (`KG`, `LB`, or `ST`); they must not be converted a second time.
For directory and user selection, see [Configuration](configuration.md#weather-and-running-overlay).

The verified upload, `openScale.db_auto_backup.zip`, contains the SQLite
database and its `-wal` and `-shm` sidecars. The fetcher copies those exact
members into a private temporary directory and opens the copied database in
read-only mode, so SQLite includes measurements in the write-ahead log while
the original ZIP remains untouched. Other ZIP members are ignored.

The weight fetcher runs independently of workout parsing. The workout fetcher
reads only TCX files directly under `cache/workouts/`, so files in the weight
subdirectory are outside its input. Cache files and polling intervals are
documented in [Caches](caches.md); displayed metrics belong to the
[weather and running overlay](weather.md).

## Tailscale policy

The tailnet (`kianbahasadri@gmail.com`) also contains devices shared in from
`xwh256@gmail.com` (`azure`, `mac-mini`). They are **shared-in devices, not
members**, which Tailscale automatically quarantines to reply-only — they
cannot initiate connections toward this tailnet's devices, even under an
allow-all policy. The admin console shows them with a "Shared in" badge; note
that `tailscale status --json` does not expose any shared flag, and the owner
login shown there is just provenance — check the console, not the CLI.

The policy file (Access Controls in the admin console, not managed from this
repo) carries an explicit allow so a future edit cannot silently change the
model:

```jsonc
"grants": [
	{"src": ["kianbahasadri@gmail.com"], "dst": ["*"], "ip": ["*"]},
],
"tests": [
	{"src": "kianbahasadri@gmail.com",
	 "accept": ["100.123.102.71:22", "100.123.102.71:9876"]},
	{"src": "xwh256@gmail.com",
	 "deny": ["100.123.102.71:22", "100.123.102.71:9876"]},
],
```

Lessons from setting this up:

- The trailing-`@` principal shorthand (`kianbahasadri@`) matched **nothing**
  in `grants`, silently turning the whole policy into deny-all — it broke SSH
  and the WebDAV path from the phone while locally-originated traffic still
  worked (local traffic never traverses the tailnet packet filter, which made
  the breakage look like a client bug). Use the full email.
- The `tests` section runs on every policy save and **rejects the save** if an
  assertion fails, so a policy that breaks legitimate access cannot go live.
  Pair any hand-written policy with accept/deny tests.
- ufw runs here with `default deny incoming` and no `tailscale0` rule, and that
  did **not** block tailnet traffic — tailscaled's own netfilter chains accept
  what the packet filter already vetted. No ufw change was needed.

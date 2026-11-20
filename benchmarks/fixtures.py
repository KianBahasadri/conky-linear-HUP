"""Versioned synthetic inputs and provider boundaries for the complete suite.

Production code is copied without importing the developer's .env or credentials.
Only acquisition boundaries are replaced; parsing, normalization, caching, scans,
analysis, renderer code, launcher loops and helper process creation still run.
"""
import datetime as dt
import functools
import io
import json
import os
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request

NOW = 1794484800  # 2026-11-12 12:00 UTC
FETCHERS = ["linear_tasks", "codex_usage", "cursor_usage", "gemini_usage",
            "minecraft_status", "github_contributions", "weather", "workouts",
            "weight", "billing_usage", "git_status", "sessions"]
OUTPUTS = ["linear-cards", "codex-usage", "cursor-usage", "gemini-usage",
           "minecraft-status", "github-contributions", "weather-status",
           "workouts-status", "weight-status", "billing-usage", "git-status", "sessions"]


def instrument_source(path):
    """Patch copied entrypoints after imports, without tracing Python imports."""
    import ast
    source = path.read_text()
    module = ast.parse(source, filename=str(path))
    guards = [node for node in module.body if isinstance(node, ast.If)
              and isinstance(node.test, ast.Compare)
              and isinstance(node.test.left, ast.Name) and node.test.left.id == "__name__"
              and len(node.test.ops) == 1 and isinstance(node.test.ops[0], ast.Eq)
              and len(node.test.comparators) == 1
              and isinstance(node.test.comparators[0], ast.Constant)
              and node.test.comparators[0].value == "__main__"]
    if len(guards) != 1:
        raise RuntimeError(f"expected one entrypoint guard: {path.name}")
    lines = source.splitlines(keepends=True)
    first = guards[0].body[0].lineno - 1
    indent = lines[first][:len(lines[first]) - len(lines[first].lstrip())]
    lines.insert(first, f"{indent}from fixtures import instrument_entrypoint\n"
                        f"{indent}instrument_entrypoint(globals(), {path.name!r})\n")
    path.write_text("".join(lines))


def record_invocation(name, kind):
    root = Path(os.environ["CONKY_BENCH_ROOT"])
    with (root / "cache/benchmark-invocations").open("a") as output:
        output.write(json.dumps({"name": name, "pid": os.getpid(), "kind": kind,
            "time": time.monotonic(), "phase": (root / "cache/benchmark-phase").read_text()}) + "\n")


def instrument_entrypoint(namespace, name):
    patch_globals(namespace, name)
    key = "sample" if name == "sample_gpu_usage.py" else "main"
    original = namespace[key]

    @functools.wraps(original)
    def invoke(*args, **kwargs):
        record_invocation(name, "start")
        try:
            return original(*args, **kwargs)
        finally:
            record_invocation(name, "end")

    namespace[key] = invoke


def dump(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


# Fetchers the pinned baseline and the pre-optimization revision do not start.
# Coverage follows the copied launcher so those revisions are not required to
# run a loop they never launch.
LAUNCHER_FETCHERS = {
    "opencode": ("opencode_usage", "opencode-usage"),
}


def launcher_fetch_keys(root):
    import re
    text = (Path(root) / "scripts/start_conky_overlays.sh").read_text()
    match = re.search(r"^fetch_keys=\(([^)]*)\)", text, re.M)
    if not match:
        raise RuntimeError(f"start script has no fetch_keys list: {root}")
    return match.group(1).split()


def active_workload(root):
    """Return the fetchers and cache outputs the copied launcher starts."""
    fetchers = list(FETCHERS)
    outputs = list(OUTPUTS)
    for key in launcher_fetch_keys(root):
        extra = LAUNCHER_FETCHERS.get(key)
        if extra and extra[0] not in fetchers:
            fetchers.append(extra[0])
            outputs.append(extra[1])
    return fetchers, outputs


def prepare(root, monitors, python, real_conky):
    """Build fixed data outside the measured cgroup; no personal cache is copied."""
    import math
    import shlex
    import sqlite3
    import subprocess
    import zipfile
    data = root / "benchmark-data"
    data.mkdir()
    cache = root / "cache"
    cache.mkdir(exist_ok=True)
    (data / "home").mkdir()
    (data / "bin").mkdir()
    dump(data / "monitors.json", monitors)
    shared_gpu = "gpu-usage.tsv" in (root / "conky/resource-monitor-renderer.lua").read_text()
    fetchers, _outputs = active_workload(root)
    dump(data / "workload.json", {"shared_gpu_sampler": shared_gpu, "fetch_loops": len(launcher_fetch_keys(root))})
    (data / "python").write_text(python)
    (data / "conky").write_text(real_conky)
    (cache / "benchmark-phase").write_text("startup")
    repos = []
    git_env = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
               "GIT_AUTHOR_DATE": "2026-11-12T10:00:00Z", "GIT_COMMITTER_DATE": "2026-11-12T10:00:00Z"}
    for i in range(12):
        repo = data / "home" / f"repo-{i:02d}"
        repo.mkdir()
        for j in range(48):
            (repo / f"source-{j:02d}.txt").write_text(f"fixture {i} {j}\n" * 16)
        for args in (["init", "-q", "-b", "main"], ["add", "."],
                     ["-c", "user.name=Benchmark", "-c", "user.email=bench@example.invalid", "commit", "-qm", "Fixture"],
                     ["remote", "add", "origin", f"https://github.com/benchmark/repo-{i:02d}.git"]):
            subprocess.run(["git", "-C", str(repo), *args], env=git_env, check=True, capture_output=True)
        if i % 3 == 0:
            (repo / "source-00.txt").write_text("dirty fixture\n")
        repos.append(str(repo))
    dump(data / "repos.json", repos)
    workouts = cache / "workouts"
    workouts.mkdir()
    for i in range(14):
        start = NOW - (27 - i * 2) * 86400 - 3600
        track = []
        distance = 0.0
        previous = None
        for j in range(900):
            angle = j / 180 * math.tau
            x, y = 120 * math.cos(angle), 80 * math.sin(angle)
            if previous:
                distance += math.hypot(x - previous[0], y - previous[1])
            previous = x, y
            stamp = dt.datetime.fromtimestamp(start + j * 2, dt.timezone.utc).isoformat()
            track.append(f"<Trackpoint><Time>{stamp}</Time><DistanceMeters>{distance}</DistanceMeters>"
                         f"<Position><LatitudeDegrees>{40+y/111320}</LatitudeDegrees>"
                         f"<LongitudeDegrees>{-75+x/85276}</LongitudeDegrees></Position>"
                         "<HeartRateBpm><Value>145</Value></HeartRateBpm>"
                         "<Extensions><TPX><RunCadence>82</RunCadence></TPX></Extensions></Trackpoint>")
        (workouts / f"run-{i:02d}.tcx").write_text(
            '<TrainingCenterDatabase><Activities><Activity Sport="Running"><Lap>'
            f"<TotalTimeSeconds>1798</TotalTimeSeconds><DistanceMeters>{distance}</DistanceMeters>"
            f"<Calories>240</Calories><Track>{''.join(track)}</Track></Lap><Notes>8 3 11</Notes>"
            "</Activity></Activities></TrainingCenterDatabase>")
    weight = workouts / "weight"
    weight.mkdir()
    database = data / "openScale.db"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE Measurement (id INTEGER PRIMARY KEY, userId INTEGER, timestamp INTEGER);
            CREATE TABLE MeasurementType (id INTEGER PRIMARY KEY, key TEXT, unit TEXT);
            CREATE TABLE MeasurementValue (measurementId INTEGER, typeId INTEGER, floatValue REAL, intValue INTEGER);
            INSERT INTO MeasurementType VALUES (1, 'WEIGHT', 'KG');
        """)
        for i in range(90):
            connection.execute("INSERT INTO Measurement VALUES (?, 1, ?)", (i, (NOW - (90-i)*86400)*1000))
            connection.execute("INSERT INTO MeasurementValue VALUES (?, 1, ?, NULL)", (i, 90-i*0.02))
    with zipfile.ZipFile(weight / "backup.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(database, "openScale.db")
    prepare_usage_profiles(root, data)
    drm = data / "drm"
    for card, driver, device in ((0, "i915", "0000:00:02.0"), (1, "nvidia", "0000:01:00.0")):
        directory = drm / f"card{card}" / "device"
        directory.mkdir(parents=True)
        (directory / "uevent").write_text(f"DRIVER={driver}\nPCI_SLOT_NAME={device}\n")
    for i in range(32):
        directory = data / "proc" / str(1000+i)
        (directory / "fd").mkdir(parents=True)
        (directory / "fdinfo").mkdir()
        (directory / "fd" / "3").symlink_to("/dev/dri/renderD128")
        (directory / "fdinfo" / "3").write_text(
            f"drm-pdev: 0000:00:02.0\ndrm-client-id: {i}\ndrm-engine-render: 2000000000 ns\n")
    # These are executable acquisition stubs. The real callers still spawn and
    # wait for subprocesses; git and uv themselves are never mocked.
    monitor_lines = [f"Monitors: {len(monitors)}"]
    for i, (w, h, x, y) in enumerate(monitors):
        monitor_lines.append(f" {i}: +{'*' if i == 0 else ''}bench-{i} {w}/1x{h}/1{x:+d}{y:+d} bench-{i}")
    (data / "xrandr.txt").write_text("\n".join(monitor_lines)+"\n")
    sessions = [f"session-{i}\t2\t{repos[i]}\t{NOW-60*i}" for i in range(6)]
    (data / "sessions.txt").write_text("\n".join(sessions)+"\n")
    (data / "panes.txt").write_text("\n".join(f"session-{i}" for i in range(6) for _ in range(2))+"\n")
    (data / "clients.txt").write_text("/dev/pts/1\tsession-0\n/dev/pts/2\tsession-1\n")
    dump(data / "tailscale.json", {"Self": {"HostName": "fixture-laptop", "OS": "linux", "TailscaleIPs": ["100.64.0.1"]}, "Peer": {}})
    commands = {
        "xrandr": 'cat "$CONKY_BENCH_ROOT/benchmark-data/xrandr.txt"',
        "gsettings": "if [ \"$1\" = monitor ]; then exec /usr/bin/sleep 86400; else echo \"'prefer-dark'\"; fi",
        "tmux": """case "$*" in
          *";"*)
            for kind in session pane client; do
              case "$kind" in session) file=sessions;; pane) file=panes;; client) file=clients;; esac
              while IFS= read -r line; do printf '%s|%s\\n' "$kind" "$line"; done < "$CONKY_BENCH_ROOT/benchmark-data/$file.txt"
            done;;
          *)
            case "$1" in list-sessions) file=sessions;; list-panes) file=panes;; list-clients) file=clients;; *) exit 1;; esac
            while IFS= read -r line; do printf '%s\\n' "$line"; done < "$CONKY_BENCH_ROOT/benchmark-data/$file.txt";;
        esac""",
        "tailscale": 'cat "$CONKY_BENCH_ROOT/benchmark-data/tailscale.json"',
        "who": "echo 'fixture pts/1 2026-11-12 11:00 (100.64.0.1)'",
        "ss": "echo 'LISTEN 0 128 0.0.0.0:22 0.0.0.0:*'",
        "iwgetid": "echo fixture-wifi",
        "nvidia-smi": "echo '00000000:01:00.0, 32'",
        "gh": "echo '[{\"status\":\"completed\",\"conclusion\":\"success\",\"headBranch\":\"main\"}]'",
    }
    for name, body in commands.items():
        path = data / "bin" / name
        path.write_text("#!/bin/sh\n"+body+"\n")
        path.chmod(0o755)
    shim = data / "bin" / "conky"
    shim.write_text(f"#!/bin/sh\nexec {shlex.quote(python)} {shlex.quote(str(Path(__file__).with_name('conky_wrapper.py')))} \"$@\"\n")
    shim.chmod(0o755)
    for name in [f"fetch_{key}.py" for key in fetchers] + ["sample_gpu_usage.py"]:
        instrument_source(root / "scripts" / name)


def prepare_usage_profiles(root, data):
    # The pinned baseline and regression revision still use the snapshot CLI.
    if (root / "scripts/clusterfork_usage.py").is_file():
        import hashlib

        for provider in ("codex", "cursor"):
            accounts = []
            for i in range(2):
                accounts.append({"provider": provider, "account_id": hashlib.sha256(f"{provider}-{i}".encode()).hexdigest(),
                                 "aliases": [f"fixture-{i}"], "cloud_available": True, "local_available": False,
                                 "usage": {"freshness": "fresh", "observed_at": NOW, "attempted_at": NOW,
                                           "windows": [{"name": f"{provider}/{label}", "used_percent": 25+i*20,
                                                        "duration_minutes": duration, "resets_at": NOW+duration*60}
                                                       for label, duration in (("primary", 300), ("secondary", 10080))]}})
            dump(data / f"{provider}-snapshot.json", {"schema_version": 1, "provider": provider,
                 "local_scope": "host", "generated_at": NOW, "accounts": accounts})
        (data / "accounts.py").write_text(
            "import os, pathlib, sys\n"
            "provider=sys.argv[sys.argv.index('--provider')+1]\n"
            "print((pathlib.Path(os.environ['CONKY_BENCH_ROOT'])/'benchmark-data'/"
            "(provider+'-snapshot.json')).read_text())\n")
        return

    import base64

    store = data / "home/.local/share/clusterfork-auth"
    for provider in ("codex", "cursor"):
        directory = store / provider
        directory.mkdir(parents=True)
        for i in range(2):
            subject = f"{provider}-{i}"
            if provider == "codex":
                auth = {"tokens": {"account_id": subject, "access_token": "fixture"}}
            else:
                claims = base64.urlsafe_b64encode(json.dumps({"sub": subject}).encode()).decode()
                auth = {"accessToken": f"fixture.{claims}.fixture"}
            dump(directory / f"auth.json.fixture-{i}", auth)
        (directory / "current").symlink_to("auth.json.fixture-0")


def payload(url, body):
    parsed = urllib.parse.urlsplit(url)
    if parsed.hostname == "api.github.com" and parsed.path == "/graphql":
        days = []
        for i in range(401):
            day = dt.datetime.fromtimestamp(NOW-i*86400, dt.timezone.utc).date().isoformat()
            days.append({"date": day, "contributionCount": i % 19, "contributionLevel": "SECOND_QUARTILE"})
        return {"data": {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": [{"contributionDays": days}]}}}}}
    if "open-meteo.com" in (parsed.hostname or ""):
        if "archive" in (parsed.hostname or ""):
            params = urllib.parse.parse_qs(parsed.query)
            start = dt.datetime.fromisoformat(params["start_date"][0]).replace(tzinfo=dt.timezone.utc).timestamp()
            end = dt.datetime.fromisoformat(params["end_date"][0]).replace(tzinfo=dt.timezone.utc).timestamp()
            times = list(range(int(start), int(end)+3600, 3600))
            variables = ("temperature_2m", "relative_humidity_2m", "dew_point_2m", "wind_speed_10m", "shortwave_radiation")
            return {"hourly": {"time": times, **{key: [20.0]*len(times) for key in variables}},
                    "hourly_units": dict(zip(("time",)+variables, ("unixtime", "°C", "%", "°C", "km/h", "W/m²")))}
        if "air-quality" in parsed.hostname:
            return {"current": {"us_aqi": 25, "pm2_5": 3, "uv_index": 2},
                    "hourly": {"time": [f"2026-11-12T{h:02d}:00" for h in range(12, 20)],
                               "us_aqi": [25]*8, "pm2_5": [3.0]*8, "uv_index": [2.0]*8}}
        dates = [(dt.datetime.fromtimestamp(NOW, dt.timezone.utc)-dt.timedelta(days=i)).date().isoformat() for i in range(7, -1, -1)]
        return {"current": {"time": "2026-11-12T12:00", "temperature_2m": 20, "apparent_temperature": 20,
                "relative_humidity_2m": 50, "weather_code": 2, "wind_speed_10m": 5, "wind_gusts_10m": 8,
                "wind_direction_10m": 180, "visibility": 15000, "is_day": 1},
                "current_units": {"temperature_2m": "°C"}, "daily_units": {"temperature_2m_mean": "°C"},
                "utc_offset_seconds": 0, "daily": {"time": dates, "temperature_2m_mean": [19.0]*8,
                "sunrise": [d+"T06:30" for d in dates], "sunset": [d+"T17:00" for d in dates]},
                "hourly": {"time": [f"2026-11-12T{h:02d}:00" for h in range(12, 20)],
                           "temperature_2m": [20.0]*8, "precipitation_probability": [0]*8,
                           "relative_humidity_2m": [50]*8, "apparent_temperature": [20.0]*8,
                           "weather_code": [2]*8, "wind_speed_10m": [5.0]*8,
                           "wind_gusts_10m": [8.0]*8, "visibility": [15000]*8}}
    if parsed.hostname == "opencode.ai" and parsed.path == "/zen/go/v1/usage":
        return {"usage": {
            "rolling": {"status": "ok", "percent": 0, "resetsAt": "2026-11-12T17:00:00Z"},
            "weekly": {"status": "ok", "percent": 7, "resetsAt": "2026-11-16T00:00:00Z"},
            "monthly": {"status": "ok", "percent": 3, "resetsAt": "2026-12-14T02:03:33Z"},
        }}
    raise RuntimeError(f"unmocked provider request: {parsed.hostname}{parsed.path}")


def patch_globals(namespace, name):
    from decimal import Decimal
    if name == "fetch_linear_tasks.py":
        issues = [{"identifier": f"BENCH-{i}", "title": f"Representative task {i}: keep the desktop responsive",
                   "priorityLabel": "High" if i % 3 == 0 else "Medium", "dueDate": None,
                   "completedAt": None, "url": f"https://example.invalid/{i}", "labels": {"nodes": []},
                   "project": {"name": "Benchmark Project", "icon": ":rocket:"},
                   "state": {"name": "In Progress" if i % 2 else "Todo", "type": "started"}} for i in range(16)]
        def graphql(_key, query, _variables):
            if "query DueIssues" in query:
                return {"data": {"dueIssues": {"nodes": [], "pageInfo": {"hasNextPage": False}}}}
            return {"data": {"workflowStates": {"nodes": [{"name": "In Progress", "type": "started", "issues": {"nodes": issues}}]},
                             "competitionIssues": {"nodes": []}, "backlogDueSoon": {"nodes": []}}}
        namespace["linear_graphql_request"] = graphql
    elif name == "fetch_codex_usage.py":
        def codex_request(auth):
            used = 25 + 20 * int(auth["label"][-1])
            return 200, {"plan_type": "plus", "rate_limit": {
                name: {"used_percent": used, "limit_window_seconds": duration, "reset_at": NOW + duration}
                for name, duration in (("primary_window", 18000), ("secondary_window", 604800))
            }}
        namespace["codex_request"] = codex_request
    elif name == "fetch_cursor_usage.py":
        def cursor_request(auth, method):
            if method == "GetCurrentPeriodUsage":
                used = 25 + 20 * int(auth["label"][-1])
                return 200, {"billingCycleStart": NOW - 86400, "billingCycleEnd": NOW + 30 * 86400,
                             "planUsage": {"autoPercentUsed": used, "apiPercentUsed": used}}
            if method == "GetMe":
                return 200, {"userId": auth["account_id"]}
            if method == "GetPlanInfo":
                return 200, {"planInfo": {"planName": "Pro"}}
            raise ValueError(f"unexpected Cursor request: {method}")
        namespace["cursor_request"] = cursor_request
    elif name == "fetch_gemini_usage.py":
        namespace["read_auth"] = lambda *_: {"access_token": "fixture"}
        namespace["load_code_assist"] = lambda *_: ("fixture", {"currentTier": {"id": "pro"}})
        namespace["fetch_quota"] = lambda *_: {"groups": [{"displayName": "Gemini Models", "buckets": [
            {"bucketId": "gemini-5h", "displayName": "Five Hour Limit Remaining", "window": "5h",
             "resetTime": "2026-11-12T17:00:00Z", "remainingFraction": 0.7},
            {"bucketId": "gemini-weekly", "displayName": "Weekly Limit Remaining", "window": "weekly",
             "resetTime": "2026-11-19T12:00:00Z", "remainingFraction": 0.8}]}]}
    elif name == "fetch_minecraft_status.py":
        namespace["query_status"] = lambda *_: {"ok": True, "updatedAt": "2026-11-12T12:00:00+00:00",
            "address": "fixture.invalid:25565", "onlinePlayers": 3, "maxPlayers": 20,
            "latencyMs": 25, "version": "1.21", "players": ["Alex", "Sam", "Lee"]}
        namespace["query_pebblehost"] = lambda *_: {"serverInfoOk": True, "label": "Fixture server"}
    elif name == "fetch_billing_usage.py":
        namespace["resolve_aws_cap"] = lambda *_: (Decimal(100), "aws-budgets", "Fixture")
        namespace["fetch_aws_current"] = lambda *_: Decimal(22)
        namespace["fetch_openrouter_credits"] = lambda *_: {"balance": Decimal(40), "totalCredits": Decimal(100), "totalUsage": Decimal(60)}
        namespace["fetch_openrouter_daily_burn"] = lambda *_: Decimal("1.25")
    elif name == "sample_gpu_usage.py":
        data = Path(os.environ["CONKY_BENCH_ROOT"]) / "benchmark-data"
        namespace["discover_gpus"].__defaults__ = (data / "drm",)
        namespace["drm_clients"].__defaults__ = (data / "proc",)


def install():
    root = Path(os.environ["CONKY_BENCH_ROOT"])
    # Path.home is confined inside these Python subprocesses. The shell's HOME
    # and the developer's auth-store variables are never reassigned.
    Path.home = classmethod(lambda cls: root / "benchmark-data" / "home")
    original_datetime = dt.datetime
    class FixedDatetime(original_datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(NOW, tz) if tz else cls.fromtimestamp(NOW)
    dt.datetime = FixedDatetime
    time.time = lambda: float(NOW)
    def audit(event, args):
        if event == "socket.connect" and args[0].family != 1:
            with (root / "cache" / "benchmark-errors").open("a") as output:
                output.write(f"unmocked network attempt: {args[1]}\n")
            raise RuntimeError("network is disabled in benchmarks")
    sys.addaudithook(audit)
    def urlopen(request, *_args, **_kwargs):
        url = request if isinstance(request, str) else request.full_url
        body = None if isinstance(request, str) else request.data
        return io.BytesIO(json.dumps(payload(url, body)).encode())
    urllib.request.urlopen = urlopen

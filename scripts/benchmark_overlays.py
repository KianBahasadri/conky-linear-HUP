#!/usr/bin/env python3
"""Benchmark the entire overlay suite against a pinned commit on the same host.

uv run python scripts/benchmark_overlays.py
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import statistics
import subprocess
import sys
import tarfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks"
sys.path.insert(0, str(BENCH))
from fixtures import FETCHERS, prepare  # noqa: E402

MIB = 1024 * 1024
ENV_INTERVALS = {"MINECRAFT_REFRESH_SECONDS", "GITHUB_REFRESH_SECONDS", "WEATHER_REFRESH_SECONDS",
                 "WORKOUTS_REFRESH_SECONDS", "WEIGHT_REFRESH_SECONDS", "BILLING_REFRESH_SECONDS",
                 "GIT_REFRESH_SECONDS", "SESSIONS_REFRESH_SECONDS", "RATE_LIMIT_CHANGED_INTERVAL",
                 "RATE_LIMIT_UNCHANGED_INTERVAL", "RATE_LIMIT_RECENT_CHANGE_WINDOW"}


def xvfb_executable():
    installed = shutil.which("Xvfb")
    if installed:
        return installed
    cached = ROOT / "cache/benchmark-tools/usr/bin/Xvfb"
    return str(cached) if os.access(cached, os.X_OK) else None


def run(command, **kwargs):
    return subprocess.run(command, check=True, capture_output=True, text=True, **kwargs).stdout.strip()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value, indent=2)+"\n")
    temporary.replace(path)


def percentile(values, fraction):
    if not values or any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("missing or invalid measurement")
    return sorted(values)[max(0, math.ceil(len(values)*fraction)-1)]


def cgroup_snapshot(group):
    counters = dict(line.split() for line in (group / "cpu.stat").read_text().splitlines())
    pss = rss = 0
    count = 0
    for pid in (group / "cgroup.procs").read_text().split():
        try:
            memory = Path(f"/proc/{pid}/smaps_rollup").read_text()
        except (FileNotFoundError, ProcessLookupError):
            continue  # Exited between the cgroup enumeration and smaps read.
        fields = {line.split(":")[0]: int(line.split()[1]) for line in memory.splitlines()[1:] if ":" in line}
        pss += fields["Pss"] * 1024
        rss += fields["Rss"] * 1024
        count += 1
    if not count or not pss or not rss:
        raise RuntimeError("no readable workload memory measurements")
    return {"time": time.monotonic(), "cpu_seconds": int(counters["usage_usec"])/1e6,
            "pss_mib": pss/MIB, "rss_mib": rss/MIB, "processes": count,
            "cgroup_memory_mib": int((group / "memory.current").read_text())/MIB}


class Workload:
    """Keep detached production windows and even millisecond helpers accounted."""
    def __init__(self, root, settings, group_root):
        self.root = root
        self.settings = settings
        self.group_root = group_root
        self.unit = f"conky-benchmark-{uuid.uuid4().hex}.service"
        self.process = None
        self.group = None

    def __enter__(self):
        settings_path = self.root / "benchmark-data/settings.json"
        write_json(settings_path, self.settings)
        command = [sys.executable, str(BENCH / "workload.py"), str(self.root), str(settings_path)]
        try:
            if self.group_root:
                self.group = self.group_root / self.unit.removesuffix(".service")
                self.group.mkdir()
                def attach():
                    (self.group / "cgroup.procs").write_text(str(os.getpid()))
                self.process = subprocess.Popen(command, preexec_fn=attach, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                run(["systemd-run", "--user", "--quiet", "--unit", self.unit,
                     "--property=Delegate=yes", "--property=KillMode=control-group", "--property=TimeoutStopSec=5",
                     "--property=CPUAffinity="+" ".join(str(cpu) for cpu in sorted(os.sched_getaffinity(0))),
                     "--property=RuntimeMaxSec=180", *command])
                relative = run(["systemctl", "--user", "show", self.unit, "--property=ControlGroup", "--value"])
                if not relative.startswith("/") or relative == "/":
                    raise RuntimeError("no delegated cgroup from systemd")
                self.group = Path("/sys/fs/cgroup") / relative.lstrip("/")
            deadline = time.monotonic()+90
            while not (self.root / "cache/benchmark-ready").exists():
                self.check()
                if time.monotonic() > deadline:
                    raise RuntimeError(f"workload startup timed out: {self.root}")
                time.sleep(0.1)
            cgroup_snapshot(self.group)  # Prerequisites are mandatory.
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def check(self):
        error = self.root / "cache/benchmark-worker-error"
        if error.exists():
            raise RuntimeError(error.read_text())
        if self.process and self.process.poll() is not None:
            raise RuntimeError("workload supervisor exited")
        if not self.process and self.group and not (self.group / "cgroup.procs").exists():
            raise RuntimeError("workload cgroup disappeared")
        errors = self.root / "cache/benchmark-errors"
        if errors.exists() and errors.stat().st_size:
            raise RuntimeError(errors.read_text())

    def __exit__(self, *_):
        if self.group_root:
            if self.group and self.group.exists():
                (self.group / "cgroup.kill").write_text("1")
                if self.process:
                    self.process.wait(timeout=10)
                deadline = time.monotonic()+10
                while (self.group / "cgroup.procs").read_text().strip():
                    if time.monotonic() > deadline:
                        raise RuntimeError("workload cgroup did not empty")
                    time.sleep(0.05)
                self.group.rmdir()
        else:
            subprocess.run(["systemctl", "--user", "stop", self.unit], capture_output=True, timeout=15)
            subprocess.run(["systemctl", "--user", "reset-failed", self.unit], capture_output=True, timeout=10)


def copy_source(target, revision):
    if revision:
        archive = subprocess.run(["git", "-C", str(ROOT), "archive", revision, "conky", "scripts", "assets", "pyproject.toml", "uv.lock"], check=True, capture_output=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(target, filter="data")
    else:
        for name in ("conky", "scripts", "assets"):
            shutil.copytree(ROOT / name, target / name, ignore=shutil.ignore_patterns("generated", "__pycache__"))
        for name in ("pyproject.toml", "uv.lock"):
            shutil.copy2(ROOT / name, target / name)
    # Keep the interpreter and installed dependency versions identical between
    # reference and candidate. UV_NO_SYNC prevents any environment mutation.
    (target / ".venv").symlink_to(Path(sys.prefix))


def source_fingerprint(root):
    """Identify the actual copied files, including untracked working-tree code."""
    digest = hashlib.sha256()
    for directory in ("conky", "scripts", "assets"):
        for path in sorted((root / directory).rglob("*")):
            if path.is_file():
                digest.update(str(path.relative_to(root)).encode()+b"\0")
                digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def environment(root, display):
    env = {key: os.environ[key] for key in ("PATH", "HOME", "USER", "LANG") if key in os.environ}
    data = root / "benchmark-data"
    env.update({"PATH": str(data / "bin")+os.pathsep+os.environ["PATH"], "DISPLAY": display,
        "XDG_SESSION_TYPE": "x11", "XDG_DATA_HOME": str(data / "xdg-data"),
        "XDG_CONFIG_HOME": str(data / "xdg-config"), "XDG_CACHE_HOME": str(data / "xdg-cache"),
        "PYTHONPATH": str(BENCH), "CONKY_BENCH_ROOT": str(root), "UV_NO_SYNC": "1", "UV_OFFLINE": "1",
        "UV_PYTHON": sys.executable, "UV_PROJECT_ENVIRONMENT": str(root / ".venv"),
        "CLUSTERFORK_ACCOUNTS_SCRIPT": str(data / "accounts.py"), "CLUSTERFORK_PYTHON": sys.executable,
        "LINEAR_API_KEY": "fixture", "GITHUB_TOKEN": "fixture-token", "GITHUB_USERNAME": "fixture",
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "GIT_SCAN_ROOT": str(data / "home"),
        "GIT_SCAN_DAYS": "36500", "GIT_HIDE_CLEAN": "0", "GIT_TIMEOUT_SECONDS": "10",
        "WEATHER_LATITUDE": "40", "WEATHER_LONGITUDE": "-75", "WEATHER_LOCATION_LABEL": "Fixture",
        "MINECRAFT_SERVER": "fixture.invalid:25565", "BILLING_AWS_ENABLED": "1", "OPENROUTER_API_KEY": "fixture",
        "PRIMARY_WAIT_SECONDS": "0", "TZ": "UTC"})
    for name in ("LINEAR_OVERLAY_ENABLED", "RATE_LIMIT_PANEL_ENABLED", "MINECRAFT_OVERLAY_ENABLED", "GITHUB_OVERLAY_ENABLED",
                 "WEATHER_OVERLAY_ENABLED", "RESOURCE_MONITOR_OVERLAY_ENABLED", "BILLING_OVERLAY_ENABLED", "GIT_OVERLAY_ENABLED", "SESSIONS_OVERLAY_ENABLED"):
        env[name] = "1"
    return env


def measure_phase(workload, phase, duration, period, logical_cpus):
    phase_path = workload.root / "cache/benchmark-phase"
    staged = phase_path.with_suffix(".next")
    staged.write_text(phase)
    staged.replace(phase_path)
    start = cgroup_snapshot(workload.group)
    samples = [start]
    deadline = start["time"]+duration
    while time.monotonic() < deadline:
        time.sleep(min(period, max(0, deadline-time.monotonic())))
        workload.check()
        samples.append(cgroup_snapshot(workload.group))
    elapsed = samples[-1]["time"]-start["time"]
    cpu = samples[-1]["cpu_seconds"]-start["cpu_seconds"]
    return {"wall_seconds": elapsed, "cpu_seconds": cpu, "cpu_core_percent": cpu/elapsed*100,
            "cpu_capacity_percent": cpu/elapsed/logical_cpus*100,
            "pss_mib": statistics.median(s["pss_mib"] for s in samples),
            "rss_mib": statistics.median(s["rss_mib"] for s in samples),
            "peak_pss_mib": max(s["pss_mib"] for s in samples),
            "peak_rss_mib": max(s["rss_mib"] for s in samples),
            "max_sample_gap_seconds": max(b["time"]-a["time"] for a, b in zip(samples, samples[1:])), "samples": samples}


def extract_coverage(root, window_count, smoke):
    # Import here, outside the measured workload and without activating its
    # sitecustomize, to validate the cache and diagnostic contract.
    from workload import validate
    validate(root, window_count)
    frames = defaultdict(list)
    phases = defaultdict(set)
    for line in (root / "cache/benchmark-render.tsv").read_text().splitlines():
        name, phase, raw = line.split("\t")
        if phase in {"steady", "burst"}:
            frames[name].append(float(raw))
            phases[phase].add(name)
    if any(len(phases[p]) != window_count for p in ("steady", "burst")):
        raise RuntimeError("missing per-window steady/burst render measurements")
    events = [json.loads(line) for line in (root / "cache/benchmark-invocations").read_text().splitlines()]
    completed = {item["name"] for item in events if item["kind"] == "end" and item["phase"] == "burst"}
    required = {f"fetch_{key}.py" for key in FETCHERS} | {"sample_gpu_usage.py"}
    if required - completed:
        raise RuntimeError(f"refresh burst missed: {sorted(required-completed)}")
    if not smoke and any(len(values) < 5 for values in frames.values()):
        raise RuntimeError("too few render timing observations")
    return {"render_p95_cpu_ms": percentile([v for values in frames.values() for v in values], 0.95),
            "render_windows": {name: {"p95_cpu_ms": percentile(values, 0.95), "frames": len(values)} for name, values in sorted(frames.items())},
            "events": events}


def benchmark_one(output, profile, monitors, role, repetition, revision, settings, group_root, changes, smoke, inject=False):
    from select import select
    root = output / "workloads" / f"{profile}-{role}-{repetition}"
    root.mkdir(parents=True)
    copy_source(root, revision)
    source_sha256 = source_fingerprint(root)
    real_conky = shutil.which("conky")
    prepare(root, monitors, sys.executable, real_conky)
    if role == "candidate":
        for key, interval in changes["draw"].items():
            path = root / "conky" / f"{key}-overlay.conkyrc"
            if not path.exists():
                raise ValueError(f"unknown overlay: {key}")
            import re
            path.write_text(re.sub(r"(update_interval\s*=\s*)[\d.]+", lambda m: m[1]+str(interval), path.read_text()))
    width = max(m[0]+m[2] for m in monitors)
    height = max(m[1]+m[3] for m in monitors)
    with (root / "cache/xvfb.log").open("w") as log:
        xvfb = subprocess.Popen([xvfb_executable(), "-displayfd", "1", "-screen", "0", f"{width}x{height}x24", "-nolisten", "tcp", "-noreset"], stdout=subprocess.PIPE, stderr=log, text=True)
        try:
            if not select([xvfb.stdout], [], [], 10)[0]:
                raise RuntimeError("Xvfb did not allocate a display")
            display_number = xvfb.stdout.readline().strip()
            if not display_number.isdigit():
                raise RuntimeError(f"Xvfb failed: {(root / 'cache/xvfb.log').read_text()}")
            env = environment(root, ":"+display_number)
            if role == "candidate":
                env.update(changes["env"])
            if inject:
                env["CONKY_BENCH_INJECT_REGRESSION"] = "1"
            worker_settings = {"env": env, "expected_windows": 9*len(monitors),
                               "burst_period_seconds": settings["burst_period_seconds"]}
            print(f"{profile}: {role} repetition {repetition} — warming up", flush=True)
            with Workload(root, worker_settings, group_root) as workload:
                warmup = measure_phase(workload, "warmup", settings["warmup_seconds"], settings["sample_seconds"], len(os.sched_getaffinity(0)))
                result = {"profile": profile, "role": role, "repetition": repetition, "injected_regression": inject,
                          "source_sha256": source_sha256,
                          "warmup": warmup, "windows": worker_settings["expected_windows"], "fetch_loops": 13}
                for phase in ("steady", "burst"):
                    print(f"{profile}: {role} repetition {repetition} — {phase}", flush=True)
                    result[phase] = measure_phase(workload, phase, settings[phase+"_seconds"], settings["sample_seconds"], len(os.sched_getaffinity(0)))
                result.update(extract_coverage(root, worker_settings["expected_windows"], smoke))
                workload.check()
            return result
        finally:
            xvfb.terminate()
            xvfb.wait(timeout=10)


def metric(run_result, name):
    if "." not in name:
        return float(run_result[name])
    phase, key = name.split(".")
    return float(run_result[phase][key])


def compare(runs, policy, profiles, repeats):
    comparisons = []
    failures = []
    for profile in profiles:
        reference = [r for r in runs if r["profile"] == profile and r["role"] == "baseline"]
        candidate = [r for r in runs if r["profile"] == profile and r["role"] == "candidate" and r["repetition"] != "regression-proof"]
        if len(reference) != repeats or len(candidate) != repeats:
            raise ValueError(f"missing repetitions for {profile}")
        window_names = set(reference[0]["render_windows"])
        if any(set(r["render_windows"]) != window_names for r in reference+candidate):
            raise ValueError("baseline/candidate window coverage differs")
        names = list(policy["budgets"])+["window:"+name for name in sorted(window_names)]
        for name in names:
            budget = policy["budgets"]["render_p95_cpu_ms" if name.startswith("window:") else name]
            def value(r):
                v = r["render_windows"][name.removeprefix("window:")]["p95_cpu_ms"] if name.startswith("window:") else metric(r, name)
                if not math.isfinite(v) or v <= 0:
                    raise ValueError(f"invalid measurement: {name}")
                return v
            before = [value(r) for r in reference]
            after = [value(r) for r in candidate]
            center = statistics.median(before)
            limit = center*(1+budget["relative"])+budget["absolute"]
            observed = statistics.median(after)
            # Inconclusive noisy runs fail; neither a wider tolerance nor a new
            # baseline is silently substituted for the checked-in policy.
            noise = policy["noise"]
            noisy = max(before)-min(before) > max(center*noise["relative_range"], budget["absolute"]*noise["absolute_floor_multiple"])
            passed = observed <= limit and not noisy
            row = {"profile": profile, "metric": name, "baseline": center, "candidate": observed,
                   "limit": limit, "baseline_range": [min(before), max(before)], "candidate_range": [min(after), max(after)],
                   "passed": passed, "noisy": noisy}
            comparisons.append(row)
            if not passed:
                failures.append(f"{profile} {name}: {'baseline too noisy' if noisy else f'{observed:.3f} > {limit:.3f}'}")
    return comparisons, failures


def graph(runs, output, profile):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    candidate = next(r for r in runs if r["profile"] == profile and r["role"] == "candidate" and r["repetition"] != "regression-proof")
    samples = [s for phase in ("warmup", "steady", "burst") for s in candidate[phase]["samples"]]
    origin = samples[0]["time"]
    xs = [s["time"]-origin for s in samples]
    fig, axes = plt.subplots(3, 1, figsize=(14, 8), sharex=True, gridspec_kw={"height_ratios": [2, 2, 1.3]}, layout="constrained")
    cpu_x, cpu_y = [], []
    for i, sample in enumerate(samples):
        earlier = next((s for s in reversed(samples[:i]) if sample["time"]-s["time"] >= 1), None)
        if earlier:
            cpu_x.append(xs[i])
            cpu_y.append((sample["cpu_seconds"]-earlier["cpu_seconds"])/(sample["time"]-earlier["time"])*100)
    axes[0].plot(cpu_x, cpu_y, color="#3069b0", linewidth=1.6)
    axes[0].set_ylabel("CPU · % of one logical core\n(1 s trailing average)")
    axes[1].plot(xs, [s["pss_mib"] for s in samples], label="PSS · shared pages apportioned", color="#00876c")
    axes[1].plot(xs, [s["rss_mib"] for s in samples], label="Summed RSS · shared pages counted again", color="#b76e00", alpha=0.85)
    axes[1].set_ylabel("Memory · MiB")
    axes[1].legend(loc="upper left", fontsize=9)
    lanes = {"sample_gpu_usage.py": (0, "GPU sampling"), "fetch_git_status.py": (1, "Repository scans"),
             "fetch_workouts.py": (2, "Workout processing"), "fetch_billing_usage.py": (3, "Billing refresh")}
    starts = {}
    for event in candidate["events"]:
        identity = event["pid"], event["name"]
        if event["kind"] == "start":
            starts[identity] = event["time"]
        elif identity in starts and event["name"] in lanes:
            start, end = starts.pop(identity)-origin, event["time"]-origin
            if end >= 0:
                lane, _ = lanes[event["name"]]
                axes[2].broken_barh([(max(0, start), max(0.04, end-max(0, start)))], (lane-0.3, 0.6), facecolors="#744c9e")
    axes[2].set_yticks([v[0] for v in lanes.values()], [v[1] for v in lanes.values()])
    axes[2].set_xlabel("Seconds after warm-up begins")
    for phase, label, color in (("warmup", "Warm-up", "#dddfe3"), ("steady", "Steady / idle · production timers", "#d4eee0"),
                                ("burst", "Intensive · forced refreshes", "#ffe1b8")):
        start, end = candidate[phase]["samples"][0]["time"]-origin, candidate[phase]["samples"][-1]["time"]-origin
        for axis in axes:
            axis.axvspan(start, end, color=color, alpha=0.4, zorder=0)
        axes[0].text((start+end)/2, 1.02, label, transform=axes[0].get_xaxis_transform(), ha="center", fontsize=9)
    idle = candidate["steady"]
    intensive = candidate["burst"]
    fig.suptitle(f"Overlay resource usage · {profile} · {candidate['windows']} windows\n"
                 f"Steady: {idle['cpu_core_percent']:.1f}% core / {idle['pss_mib']:.0f} MiB PSS     "
                 f"Refresh bursts: {intensive['cpu_core_percent']:.1f}% core / {intensive['peak_rss_mib']:.0f} MiB sampled peak RSS", fontsize=13)
    for axis in axes:
        axis.grid(alpha=0.2)
        axis.set_xlim(0, xs[-1])
    fig.savefig(output / f"usage-{profile}.png", dpi=160)
    fig.savefig(output / f"usage-{profile}.svg")
    plt.close(fig)


def readable(report):
    lines = [f"# Overlay performance: {report['status'].upper()}", "", f"Candidate: `{report['commit']}` · baseline: `{report['baseline_commit']}`",
             f"CPU denominator: one core = 100%; total capacity = {report['environment']['affinity_cpus']} logical CPUs.", "",
             "Candidate medians across repetitions:", "",
             "| Profile | Phase | CPU seconds | CPU % core | CPU % capacity | Median PSS MiB | Peak PSS MiB | Peak summed RSS MiB |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for profile in report["profiles"]:
        candidates = [r for r in report["runs"] if r["role"] == "candidate" and r["profile"] == profile and r["repetition"] != "regression-proof"]
        if not candidates:
            continue
        for phase in ("steady", "burst"):
            values = [statistics.median(r[phase][key] for r in candidates) for key in (
                "cpu_seconds", "cpu_core_percent", "cpu_capacity_percent", "pss_mib", "peak_pss_mib", "peak_rss_mib")]
            lines.append(f"| {profile} | {phase} | "+" | ".join(f"{v:.2f}" for v in values)+" |")
    lines.extend(["", "| Profile | Metric | Baseline median | Candidate median | Limit | Result |", "|---|---|---:|---:|---:|---|"])
    for row in report.get("comparisons", []):
        lines.append(f"| {row['profile']} | {row['metric']} | {row['baseline']:.3f} | {row['candidate']:.3f} | {row['limit']:.3f} | {'PASS' if row['passed'] else 'FAIL'} |")
    for failure in report.get("failures", []):
        lines.extend(["", "- "+failure])
    for profile in report["profiles"]:
        if (Path(report["output"]) / f"usage-{profile}.png").exists():
            lines.extend(["", f"![{profile} resource timeline](usage-{profile}.png)"])
    return "\n".join(lines)+"\n"


def assignments(items, allowed=None):
    result = {}
    for raw in items:
        key, sep, value = raw.partition("=")
        number = float(value) if sep else float("nan")
        if not key or not math.isfinite(number) or number <= 0 or (allowed is not None and (key not in allowed or not number.is_integer())):
            raise ValueError(f"invalid interval override: {raw}")
        result[key] = str(int(number)) if allowed is not None else number
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["single", "dual"], action="append")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cgroup-root", type=Path, default=os.environ.get("CONKY_BENCH_CGROUP_ROOT"))
    parser.add_argument("--draw-interval", action="append", default=[], metavar="OVERLAY=SECONDS")
    parser.add_argument("--env", action="append", default=[], metavar="REFRESH_VARIABLE=SECONDS")
    parser.add_argument("--smoke", action="store_true", help="short harness check; never an acceptance result")
    parser.add_argument("--prove-regression", action="store_true", help="also run a measured CPU hog and require rejection")
    parser.add_argument("--inject-regression", action="store_true", help="add a CPU hog to candidate runs; must fail")
    parser.add_argument("--keep-workloads", action="store_true")
    args = parser.parse_args(argv)
    if args.smoke and args.inject_regression:
        parser.error("--inject-regression requires a full measurement")
    try:
        changes = {"draw": assignments(args.draw_interval), "env": assignments(args.env, ENV_INTERVALS)}
    except ValueError as error:
        parser.error(str(error))
    policy = json.loads((BENCH / "policy.json").read_text())
    profiles = args.profile or list(policy["profiles"])
    if len(profiles) != len(set(profiles)):
        parser.error("duplicate profiles")
    settings = dict(policy["settings"])
    if args.smoke:
        settings.update(repeats=1, warmup_seconds=1, steady_seconds=6, burst_seconds=6)
    output = (args.output or ROOT / "cache/benchmarks" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": 1, "status": "error", "commit": run(["git", "rev-parse", "HEAD"], cwd=ROOT),
              "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "dirty_diff_sha256": hashlib.sha256(run(["git", "diff", "HEAD", "--", "conky", "scripts", "assets", "pyproject.toml", "uv.lock"], cwd=ROOT).encode()).hexdigest(),
              "baseline_commit": policy["baseline_commit"], "policy_sha256": hashlib.sha256((BENCH / "policy.json").read_bytes()).hexdigest(),
              "fixture_version": policy["fixture_version"], "harness_sha256": hashlib.sha256(b"".join(p.read_bytes() for p in sorted(BENCH.glob("*.py")))+Path(__file__).read_bytes()).hexdigest(),
              "environment": {"kernel": platform.release(), "platform": platform.platform(), "python": sys.version,
                  "affinity_cpus": len(os.sched_getaffinity(0)), "online_cpus": os.cpu_count(),
                  "cpu_affinity": sorted(os.sched_getaffinity(0)),
                  "cpu_model": next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines() if line.startswith("model name")), "unknown")},
              "profiles": {p: policy["profiles"][p] for p in profiles}, "settings": settings, "smoke": args.smoke,
              "changes": changes,
              "output": str(output), "runs": [], "failures": [],
              "limits": ["Cgroup CPU includes exited children; memory is sampled and can miss peaks shorter than the sample interval.",
                         "PSS apportions shared pages; summed RSS counts them per process. Neither is GPU VRAM.",
                         "Xvfb, sampler, real compositor, GPU rendering/driver cost, network latency, battery and display-server cost are outside the measured cgroup.",
                         "Draw timings are Lua CPU milliseconds, excluding time waiting for helper subprocesses; helpers remain in total cgroup CPU."]}
    try:
        if not xvfb_executable():
            raise RuntimeError("missing prerequisite: Xvfb")
        report["environment"]["xvfb"] = xvfb_executable()
        for executable in ("conky", "uv", "git", "bash", "flock", "fc-cache", "timeout"):
            if not shutil.which(executable):
                raise RuntimeError(f"missing prerequisite: {executable}")
        report["environment"]["conky"] = run(["conky", "--version"])
        report["environment"]["uv"] = run(["uv", "--version"])
        for profile in profiles:
            for repetition in range(1, settings["repeats"]+1):
                order = ("baseline", "candidate") if repetition % 2 else ("candidate", "baseline")
                for role in order:
                    result = benchmark_one(output, profile, policy["profiles"][profile], role, repetition,
                        policy["baseline_commit"] if role == "baseline" else None, settings, args.cgroup_root,
                        report["changes"], args.smoke, inject=args.inject_regression and role == "candidate")
                    report["runs"].append(result)
                    write_json(output / "report.json", report)
            graph(report["runs"], output, profile)
        if not args.smoke:
            report["comparisons"], report["failures"] = compare(report["runs"], policy, profiles, settings["repeats"])
        if args.prove_regression and not args.smoke:
            profile = profiles[0]
            injected = benchmark_one(output, profile, policy["profiles"][profile], "candidate", "regression-proof", None,
                settings, args.cgroup_root, report["changes"], False, inject=True)
            # Compare measured injected CPU against the exact same policy limit.
            cpu_row = next(row for row in report["comparisons"] if row["profile"] == profile and row["metric"] == "steady.cpu_core_percent")
            rejected = injected["steady"]["cpu_core_percent"] > cpu_row["limit"]
            report["regression_proof"] = {"rejected": rejected, "observed_cpu_core_percent": injected["steady"]["cpu_core_percent"], "limit": cpu_row["limit"]}
            report["runs"].append(injected)
            if not rejected:
                report["failures"].append("intentional measured CPU regression was not rejected")
        report["status"] = "smoke" if args.smoke and not report["failures"] else "fail" if report["failures"] else "pass"
    except Exception as error:
        report["failures"].append(str(error))
    finally:
        write_json(output / "report.json", report)
        (output / "comparison.md").write_text(readable(report))
        if report["status"] in {"pass", "smoke"} and not args.keep_workloads:
            shutil.rmtree(output / "workloads", ignore_errors=True)
    print(f"{report['status'].upper()}: {output / 'comparison.md'}", flush=True)
    for failure in report["failures"]:
        print(failure, file=sys.stderr)
    return 0 if report["status"] in {"pass", "smoke"} else 1


if __name__ == "__main__":
    def terminate(_signum, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    raise SystemExit(main())

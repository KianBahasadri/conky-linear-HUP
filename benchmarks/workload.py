"""Cgroup workload supervisor. The sampler and Xvfb live outside this cgroup."""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback

from fixtures import FETCHERS, OUTPUTS


class NotReady(RuntimeError):
    pass


def process_info(pid):
    try:
        command = (Path("/proc") / str(pid) / "cmdline").read_bytes().split(b"\0")
        status = (Path("/proc") / str(pid) / "status").read_text()
    except FileNotFoundError:
        return None
    parent = int(next(line.split()[1] for line in status.splitlines() if line.startswith("PPid:")))
    return command, parent


def force_refresh(root):
    # Invalidate the expensive local paths before waking the actual launcher
    # loops. Killing their sleep child ends only the current timer, preserving
    # the real loop body, uv invocations and adaptive fingerprint bookkeeping.
    for name in ("git-repo-discovery.json", "git-actions-cache.json", "workouts-analysis.json", "billing-aws-cache.json"):
        (root / "cache" / name).unlink(missing_ok=True)
    for pid_path in (root / "cache").glob("*-fetch-loop.pid"):
        pid = int(pid_path.read_text())
        info = process_info(pid)
        if not info or b'project_root="$8"' not in b" ".join(info[0]):
            raise RuntimeError(f"fetch loop disappeared: {pid_path.name}")
        children_path = Path(f"/proc/{pid}/task/{pid}/children")
        for child in children_path.read_text().split():
            child_info = process_info(int(child))
            if child_info and child_info[1] == pid and Path(os.fsdecode(child_info[0][0])).name == "sleep":
                os.kill(int(child), signal.SIGTERM)


def validate(root, expected_windows):
    errors = root / "cache/benchmark-errors"
    if errors.exists() and errors.stat().st_size:
        raise RuntimeError(errors.read_text())
    for name in OUTPUTS:
        data = json.loads((root / "cache" / (name+".json")).read_text())
        if data.get("ok") is False or data.get("error") or data.get("errors"):
            raise RuntimeError(f"{name}: {data.get('error') or data.get('errors') or 'not ok'}")
    for log in (root / "cache").glob("conky-*.log"):
        for line in log.read_text(errors="replace").splitlines():
            if any(marker in line.lower() for marker in ("error:", "failed:", "lua error", "stack traceback")):
                raise RuntimeError(f"{log.name}: {line}")
    lines = (root / "cache/benchmark-render.tsv").read_text().splitlines()
    windows = {line.split("\t")[0] for line in lines}
    if len(windows) != expected_windows:
        raise NotReady(f"expected {expected_windows} drawing windows, got {len(windows)}")
    invocations = [json.loads(line) for line in (root / "cache/benchmark-invocations").read_text().splitlines()]
    completed = {item["name"] for item in invocations if item["kind"] == "end"}
    required = {f"fetch_{name}.py" for name in FETCHERS} | {"sample_gpu_usage.py"}
    if required - completed:
        raise NotReady(f"unfinished workload paths: {sorted(required - completed)}")


def check_health(root, expected_windows):
    relative = Path("/proc/self/cgroup").read_text().strip().split("::")[1]
    pids = (Path("/sys/fs/cgroup") / relative.lstrip("/") / "cgroup.procs").read_text().split()
    windows = 0
    for pid in pids:
        info = process_info(int(pid))
        if info and info[0][0] == b"conky" and os.fsencode(str(root / "conky/generated")) in b" ".join(info[0]):
            windows += 1
    if windows != expected_windows:
        raise RuntimeError(f"expected {expected_windows} running Conky processes, got {windows}")
    loops = list((root / "cache").glob("*-fetch-loop.pid"))
    if len(loops) != 13:
        raise RuntimeError(f"expected 13 running fetch loops, got {len(loops)}")
    for path in loops:
        info = process_info(int(path.read_text()))
        if not info or b'project_root="$8"' not in b" ".join(info[0]):
            raise RuntimeError(f"fetch loop disappeared: {path.name}")


def main():
    root = Path(sys.argv[1])
    settings = json.loads(Path(sys.argv[2]).read_text())
    os.environ.clear()
    os.environ.update(settings["env"])
    # Adopt the production launcher's detached loops/windows for reliable
    # cleanup and reaping; detached process groups remain inside the cgroup.
    if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "PR_SET_CHILD_SUBREAPER failed")
    with (root / "cache/benchmark-launcher.log").open("w") as log:
        subprocess.run([str(root / "scripts/start_conky_overlays.sh")], cwd=root,
                       check=True, stdout=log, stderr=subprocess.STDOUT, timeout=60)
    deadline = time.monotonic()+45
    while True:
        try:
            validate(root, settings["expected_windows"])
            break
        except (FileNotFoundError, NotReady):
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)
    (root / "cache/benchmark-ready").write_text("ready")
    if os.environ.get("CONKY_BENCH_INJECT_REGRESSION") == "1":
        subprocess.Popen([sys.executable, "-S", "-c", "while True: pass"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    next_burst = 0
    next_health = 0
    while True:
        phase = (root / "cache/benchmark-phase").read_text()
        if phase == "burst" and time.monotonic() >= next_burst:
            force_refresh(root)
            next_burst = time.monotonic()+settings["burst_period_seconds"]
        if time.monotonic() >= next_health:
            check_health(root, settings["expected_windows"])
            next_health = time.monotonic()+0.5
        # Reap any adopted child without waiting for the long-running suite.
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if not pid:
                break
            if status:
                raise RuntimeError(f"suite process {pid} exited unexpectedly: wait status {status}")
        time.sleep(0.1)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        root = Path(sys.argv[1])
        (root / "cache/benchmark-worker-error").write_text(traceback.format_exc())
        raise

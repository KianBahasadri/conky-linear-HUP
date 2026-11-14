#!/usr/bin/env python3
"""Emit per-device GPU readings and DRM client counters for the Conky sampler."""

import argparse
import csv
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

from fetch_common import atomic_write_text


def pci_address(value):
    match = re.fullmatch(r"([0-9a-fA-F]+):([0-9a-fA-F]{2}):([0-9a-fA-F]{2})\.([0-7])", value)
    if not match:
        return None
    domain, bus, device, function = match.groups()
    return f"{int(domain, 16):04x}:{bus.lower()}:{device.lower()}.{function}"


def discover_gpus(drm_root=Path("/sys/class/drm")):
    devices = {}
    for card in drm_root.glob("card[0-9]*"):
        if not re.fullmatch(r"card\d+", card.name):
            continue
        try:
            properties = dict(line.split("=", 1) for line in (card / "device/uevent").read_text().splitlines() if "=" in line)
        except OSError:
            continue
        device_id = pci_address(properties.get("PCI_SLOT_NAME", ""))
        if device_id:
            driver = properties.get("DRIVER", "")
            label = {"i915": "Intel", "xe": "Intel", "nvidia": "NVIDIA", "amdgpu": "AMD"}.get(driver, "GPU")
            devices[device_id] = {"label": label, "driver": driver, "percent": None}
    return devices


def nvidia_usage():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=pci.bus_id,utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=1, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    readings = {}
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) != 2:
            continue
        device_id = pci_address(row[0].strip())
        try:
            percent = float(row[1])
        except ValueError:
            continue
        if device_id and 0 <= percent <= 100:
            readings[device_id] = percent
    return readings


def parse_drm_client(content):
    fields = dict(line.split(":", 1) for line in content.splitlines() if ":" in line)
    device_id = pci_address(fields.get("drm-pdev", "").strip())
    client_id = fields.get("drm-client-id", "").strip()
    if not device_id or not client_id.isdigit():
        return None
    engines = {}
    for key, value in fields.items():
        match = re.fullmatch(r"drm-engine-(?!capacity-)([\w-]+)", key)
        counter = re.fullmatch(r"\s*(\d+)\s+ns\s*", value)
        if match and counter:
            engine = match[1]
            capacity = fields.get(f"drm-engine-capacity-{engine}", "1").strip()
            if capacity.isdigit() and int(capacity) > 0:
                engines[engine] = (int(counter[1]), int(capacity))
    return device_id, client_id, engines


def drm_clients(device_ids, proc_root=Path("/proc")):
    clients = {}
    if not device_ids:
        return clients
    for process in os.scandir(proc_root):
        if not process.name.isdigit():
            continue
        try:
            # Only inspect graphics handles, not every fdinfo file in the
            # desktop session. Other users' protected handles are skipped.
            handles = list(os.scandir(os.path.join(process.path, "fd")))
        except OSError:
            continue
        for handle in handles:
            try:
                if not os.readlink(handle.path).startswith("/dev/dri/"):
                    continue
                with open(os.path.join(process.path, "fdinfo", handle.name)) as source:
                    client = parse_drm_client(source.read())
            except OSError:
                continue
            if client is None or client[0] not in device_ids:
                continue
            device_id, client_id, engines = client
            previous = clients.setdefault((device_id, client_id), {})
            for engine, (counter, capacity) in engines.items():
                # Duplicated/shared descriptors refer to the same DRM client.
                old = previous.get(engine, (0, capacity))
                previous[engine] = (max(old[0], counter), capacity)
    return clients


def sample():
    devices = discover_gpus()
    clients = drm_clients({key for key, gpu in devices.items() if gpu["driver"] != "nvidia"})
    timestamp = time.monotonic()
    if any(gpu["driver"] == "nvidia" for gpu in devices.values()):
        for device_id, percent in nvidia_usage().items():
            if device_id in devices:
                devices[device_id]["percent"] = percent
    lines = [f"sample\t{timestamp:.9f}"]
    for device_id, gpu in sorted(devices.items()):
        percent = "" if gpu["percent"] is None else str(gpu["percent"])
        lines.append(f"gpu\t{device_id}\t{gpu['label']}\t{percent}")
    for (device_id, client_id), engines in sorted(clients.items()):
        for engine, (counter, capacity) in sorted(engines.items()):
            lines.append(f"engine\t{device_id}\t{client_id}\t{engine}\t{counter}\t{capacity}")
    return "\n".join(lines) + "\n"


def watch(output, interval, stop):
    """Publish one shared sample on a monotonic schedule, without restarting Python."""
    producer = f"{os.getpid()}:{time.monotonic_ns()}"
    output.parent.mkdir(parents=True, exist_ok=True)
    while not stop.is_set():
        started = time.monotonic()
        try:
            snapshot = sample()
        except OSError as error:
            snapshot = f"sample\t{time.monotonic():.9f}\nerror\tprobe\n"
            print(f"GPU sampling unavailable: {error}", file=sys.stderr, flush=True)
        snapshot += f"observed\t{time.time():.6f}\nproducer\t{producer}\n"
        atomic_write_text(output, snapshot)
        stop.wait(max(0, interval - (time.monotonic() - started)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "cache/gpu-usage.tsv")
    parser.add_argument("--interval", type=float, default=2)
    args = parser.parse_args(argv)
    if not 0 < args.interval < float("inf"):
        parser.error("--interval must be finite and positive")
    if not args.watch:
        print(sample(), end="")
        return 0
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    watch(args.output, args.interval, stop)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

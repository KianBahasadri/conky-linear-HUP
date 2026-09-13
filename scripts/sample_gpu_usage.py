#!/usr/bin/env python3
"""Emit per-device GPU readings and DRM client counters for the Conky sampler."""

import csv
import os
from pathlib import Path
import re
import subprocess
import time


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
    for process in proc_root.iterdir():
        if not process.name.isdigit():
            continue
        try:
            # Only inspect graphics handles, not every fdinfo file in the
            # desktop session. Other users' protected handles are skipped.
            handles = list((process / "fd").iterdir())
        except OSError:
            continue
        for handle in handles:
            try:
                if not os.readlink(handle).startswith("/dev/dri/"):
                    continue
                client = parse_drm_client((process / "fdinfo" / handle.name).read_text())
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


if __name__ == "__main__":
    print(sample(), end="")

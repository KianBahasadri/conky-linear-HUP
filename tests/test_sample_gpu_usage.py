import subprocess
from types import SimpleNamespace

import pytest

import sample_gpu_usage as gpu


INTEL = "0000:00:02.0"
NVIDIA = "0000:01:00.0"


def client_info(device=INTEL, client=30, counter=100, capacity=1):
    return (f"drm-driver:\ti915\ndrm-client-id:\t{client}\ndrm-pdev:\t{device}\n"
            f"drm-engine-render:\t{counter} ns\ndrm-engine-capacity-render:\t{capacity}\n")


def test_discovers_physical_gpus_once_despite_connectors_and_render_nodes(tmp_path):
    for name, device, driver in (("card8", NVIDIA, "nvidia"), ("card3", INTEL, "i915"),
                                 ("card3-DP-1", INTEL, "i915"), ("renderD128", INTEL, "i915")):
        node = tmp_path / name / "device"
        node.mkdir(parents=True)
        (node / "uevent").write_text(f"DRIVER={driver}\nPCI_SLOT_NAME={device}\n")
    devices = gpu.discover_gpus(tmp_path)
    assert set(devices) == {INTEL, NVIDIA}
    assert devices[INTEL]["label"] == "Intel"
    assert devices[NVIDIA]["label"] == "NVIDIA"
    assert all(value["percent"] is None for value in devices.values())


def test_nvidia_matches_pci_addresses_and_keeps_each_device_reading(monkeypatch):
    monkeypatch.setattr(gpu.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout="00000000:01:00.0, 64\n00000000:02:00.0, 23\n0000:03:00.0, N/A\n"
               "0000:04:00.0, nan\n0000:05:00.0, 101\n"))
    assert gpu.nvidia_usage() == {NVIDIA: 64, "0000:02:00.0": 23}


@pytest.mark.parametrize("error", [FileNotFoundError(), subprocess.TimeoutExpired("nvidia-smi", 1),
                                  subprocess.CalledProcessError(1, "nvidia-smi")])
def test_nvidia_failures_do_not_invent_idle_readings(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(gpu.subprocess, "run", fail)
    assert gpu.nvidia_usage() == {}


def test_drm_parser_separates_engine_counters_and_capacity():
    device, client, engines = gpu.parse_drm_client(client_info(capacity=2))
    assert (device, client) == (INTEL, "30")
    assert engines == {"render": (100, 2)}
    assert gpu.parse_drm_client(client_info(capacity=0))[2] == {}
    assert gpu.parse_drm_client("pos: 0\nflags: 0100000\n") is None


def test_shared_drm_handles_are_counted_once_and_devices_stay_separate(tmp_path):
    for pid, fd, content in ((10, 4, client_info(counter=100)),
                             (10, 5, client_info(counter=200)),
                             (11, 6, client_info(counter=150)),
                             (11, 7, client_info(client=31, counter=50)),
                             (12, 8, client_info(device=NVIDIA, counter=999))):
        process = tmp_path / str(pid)
        (process / "fd").mkdir(parents=True, exist_ok=True)
        (process / "fdinfo").mkdir(exist_ok=True)
        (process / "fd" / str(fd)).symlink_to("/dev/dri/renderD128")
        (process / "fdinfo" / str(fd)).write_text(content)
    assert gpu.drm_clients({INTEL}, tmp_path) == {
        (INTEL, "30"): {"render": (200, 1)},
        (INTEL, "31"): {"render": (50, 1)},
    }
    assert gpu.drm_clients(set(), tmp_path) == {}


def test_snapshot_keeps_intel_counters_and_nvidia_failure_independent(monkeypatch):
    monkeypatch.setattr(gpu, "discover_gpus", lambda: {
        NVIDIA: {"label": "NVIDIA", "driver": "nvidia", "percent": None},
        INTEL: {"label": "Intel", "driver": "i915", "percent": None},
    })
    monkeypatch.setattr(gpu, "nvidia_usage", lambda: {})
    monkeypatch.setattr(gpu, "drm_clients", lambda devices: {(INTEL, "30"): {"render": (300, 1)}})
    output = gpu.sample().splitlines()
    assert output[1:3] == [f"gpu\t{INTEL}\tIntel\t", f"gpu\t{NVIDIA}\tNVIDIA\t"]
    assert output[3] == f"engine\t{INTEL}\t30\trender\t300\t1"

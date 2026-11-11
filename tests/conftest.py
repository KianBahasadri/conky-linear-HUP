import math
import os
import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture
def circuit_positions():
    """A known oval course with an approach, exercise stops, and optional detours."""
    def build(turns=4.0, detour=False):
        xy = [(0.0, -350.0 + 2.0 * index) for index in range(136)]
        for index in range(1, int(240 * turns) + 1):
            angle = 2.0 * math.pi * index / 240 - math.pi / 2
            xy.append((120.0 * math.cos(angle), 80.0 * math.sin(angle)))
            if index % 60 == 0:
                xy.extend([xy[-1]] * 20)
        if detour:
            xy.extend((float(x), -80.0) for x in range(0, 102, 2))
            xy.extend((float(x), -80.0) for x in range(100, -2, -2))
        return [
            (1_800_000_000.0 + index, 40.0 + y / 111320.0,
             -75.0 + x / (111320.0 * math.cos(math.radians(40.0))))
            for index, (x, y) in enumerate(xy)
        ]
    return build


@pytest.fixture(autouse=True)
def restore_environ():
    # Fetchers call common.load_env(), which setdefault()s the developer's real
    # .env into os.environ. monkeypatch does not undo that, so without this the
    # values persist for the rest of the session and later tests depend on run
    # order and on local config.
    original = os.environ.copy()
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(original)


@pytest.fixture(autouse=True)
def prevent_live_fetcher_log_writes(monkeypatch):
    # Fetcher loggers are bound to real cache paths at module import time, so
    # redirecting CACHE_DIR/LOG_PATH inside a test does not redirect them.
    # Silence every imported fetcher by default; tests that assert diagnostics
    # replace log_event with their own capture after this fixture runs.
    for module_name, module in list(sys.modules.items()):
        if module_name.startswith("fetch_") and hasattr(module, "log_event"):
            monkeypatch.setattr(module, "log_event", lambda _message: None)

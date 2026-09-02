import os
import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


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

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

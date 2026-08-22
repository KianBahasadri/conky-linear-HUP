import os
import shutil
import subprocess
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent

LUA_HARNESSES = sorted((TESTS_DIR / "lua").glob("*.lua"))


def _lua_binary() -> str | None:
    # 5.4 preferred: the harnesses are written against 5.4 semantics.
    for candidate in ("lua5.4", "lua5.3", "lua"):
        if path := shutil.which(candidate):
            return path
    return None


@pytest.mark.parametrize("harness", LUA_HARNESSES, ids=[path.stem for path in LUA_HARNESSES])
def test_lua_characterization(harness: Path):
    lua = _lua_binary()
    if lua is None:
        if os.environ.get("CI"):
            pytest.fail("no lua interpreter on PATH in CI; the workflow must install it")
        pytest.skip("no lua interpreter on PATH")

    scratch = REPO_ROOT / "cache" / "test-scratch"
    scratch.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [lua, str(harness), str(REPO_ROOT), str(scratch)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"{harness.name} failed:\n{result.stdout}\n{result.stderr}"

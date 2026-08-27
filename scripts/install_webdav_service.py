#!/usr/bin/env python3
"""Install the rclone WebDAV workout-upload service as a systemd user unit."""

import os
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIT_SRC = ROOT / "systemd" / "rclone-webdav.service"
UNIT_NAME = UNIT_SRC.name
UNIT_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd" / "user"
UNIT_LINK = UNIT_DIR / UNIT_NAME
WORKOUTS_DIR = ROOT / "cache" / "workouts"
EXPECTED_ROOT = Path("/home/kian/conky-linear-HUP")
WEBDAV_URL = "http://100.123.102.71:9876/"
AUTH_DIR = Path.home() / ".config" / "rclone"
HTPASSWD_PATH = AUTH_DIR / "webdav.htpasswd"
PASSWORD_PATH = AUTH_DIR / "webdav-password.txt"
AUTH_USER = "kian"


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def write_private(path: Path, content: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(content)


def ensure_auth() -> None:
    if HTPASSWD_PATH.exists():
        print(f"Auth file exists: {HTPASSWD_PATH}")
        return
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    import bcrypt

    password = secrets.token_urlsafe(12)
    digest = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    write_private(HTPASSWD_PATH, f"{AUTH_USER}:{digest}\n")
    write_private(PASSWORD_PATH, f"{AUTH_USER}: {password}\n")
    print(f"Generated auth: {HTPASSWD_PATH} (password saved to {PASSWORD_PATH})")


def install_unit() -> None:
    WORKOUTS_DIR.mkdir(parents=True, exist_ok=True)
    UNIT_DIR.mkdir(parents=True, exist_ok=True)

    if UNIT_LINK.is_symlink():
        if UNIT_LINK.resolve() != UNIT_SRC.resolve():
            UNIT_LINK.unlink()
    elif UNIT_LINK.exists():
        print(f"warning: replacing pre-existing file {UNIT_LINK}", file=sys.stderr)
        UNIT_LINK.unlink()

    if not UNIT_LINK.exists():
        UNIT_LINK.symlink_to(UNIT_SRC)

    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "enable", UNIT_NAME)
    run("systemctl", "--user", "restart", UNIT_NAME)


def main() -> int:
    if ROOT != EXPECTED_ROOT:
        print(
            f"warning: repo lives at {ROOT} but {UNIT_NAME} hardcodes {EXPECTED_ROOT} in ExecStart; update the unit",
            file=sys.stderr,
        )

    ensure_auth()
    install_unit()

    print(f"Installed {UNIT_LINK} -> {UNIT_SRC}")
    print(f"Workouts directory: {WORKOUTS_DIR}")
    print(f"Phone WebDAV URL:   {WEBDAV_URL}")
    print(f"Phone WebDAV login: see {PASSWORD_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

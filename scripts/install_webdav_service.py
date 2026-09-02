#!/usr/bin/env python3
"""Install the rclone WebDAV workout-upload service as a systemd user unit."""

import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIT_SRC = ROOT / "systemd" / "rclone-webdav.service"
UNIT_NAME = UNIT_SRC.name
UNIT_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "systemd" / "user"
UNIT_LINK = UNIT_DIR / UNIT_NAME
WORKOUTS_DIR = ROOT / "cache" / "workouts"
DEFAULT_PHONE_WEBDAV_URL = "https://kianlaptop.tail3a78b9.ts.net/"
AUTH_DIR = Path.home() / ".config" / "rclone"
HTPASSWD_PATH = AUTH_DIR / "webdav.htpasswd"
PASSWORD_PATH = AUTH_DIR / "webdav-password.txt"
SERVICE_ENV_PATH = AUTH_DIR / "webdav-service.env"
AUTH_USER = "kian"


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def write_private(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary_path, path)
        path.chmod(0o600)
    finally:
        temporary_path.unlink(missing_ok=True)


def ensure_auth() -> None:
    if HTPASSWD_PATH.exists():
        HTPASSWD_PATH.chmod(0o600)
        if not PASSWORD_PATH.exists():
            raise RuntimeError(
                f"{HTPASSWD_PATH} exists but {PASSWORD_PATH} is missing; "
                "delete the htpasswd file and rerun to rotate the credential"
            )
        PASSWORD_PATH.chmod(0o600)
        print(f"Auth file exists: {HTPASSWD_PATH}")
        return
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    import bcrypt

    password = secrets.token_urlsafe(12)
    digest = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    # The htpasswd file is the completion marker. Write it last so an
    # interrupted install cannot look complete while lacking the plaintext
    # credential needed to configure the phone.
    write_private(PASSWORD_PATH, f"{AUTH_USER}: {password}\n")
    write_private(HTPASSWD_PATH, f"{AUTH_USER}:{digest}\n")
    print(f"Generated auth: {HTPASSWD_PATH} (password saved to {PASSWORD_PATH})")


def environment_value(value: Path) -> str:
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_service_environment() -> None:
    write_private(
        SERVICE_ENV_PATH,
        "\n".join(
            (
                f"RCLONE_WEBDAV_WORKOUTS_DIR={environment_value(WORKOUTS_DIR)}",
                f"RCLONE_WEBDAV_HTPASSWD_PATH={environment_value(HTPASSWD_PATH)}",
                "",
            )
        ),
    )


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
    if shutil.which("systemctl") is None:
        raise RuntimeError("systemctl is not installed")
    if not Path("/usr/bin/rclone").is_file():
        raise RuntimeError("/usr/bin/rclone is not installed")

    ensure_auth()
    write_service_environment()
    install_unit()

    phone_url = os.environ.get("WEBDAV_PUBLIC_URL", DEFAULT_PHONE_WEBDAV_URL)
    print(f"Installed {UNIT_LINK} -> {UNIT_SRC}")
    print(f"Workouts directory: {WORKOUTS_DIR}")
    print(f"Loopback backend:   http://127.0.0.1:9876/")
    print(f"Phone WebDAV URL:   {phone_url}")
    print(f"Phone WebDAV login: see {PASSWORD_PATH}")
    print(f"Service paths:      {SERVICE_ENV_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

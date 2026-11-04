#!/usr/bin/env python3
"""Share GNOME's current light/dark preference with every Conky window."""

import argparse
import signal
import subprocess
import sys
from pathlib import Path

from fetch_common import atomic_write_text


ROOT = Path(__file__).resolve().parents[1]
THEME_PATH = ROOT / "cache" / "desktop-theme"
SCHEMA = "org.gnome.desktop.interface"
THEME_KEYS = {"color-scheme", "gtk-theme"}


def read_setting(key: str) -> str | None:
    try:
        result = subprocess.run(
            ["gsettings", "get", SCHEMA, key],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip().strip("'\"") or None


def detect_theme() -> str:
    scheme = read_setting("color-scheme")
    if scheme == "prefer-dark":
        return "dark"
    if scheme == "prefer-light":
        return "light"
    # GNOME's default has no preference; honor older/custom dark GTK themes.
    gtk_theme = read_setting("gtk-theme")
    if gtk_theme:
        return "dark" if "dark" in gtk_theme.lower() else "light"
    return "light" if scheme == "default" else "dark"


def update_theme(path: Path = THEME_PATH) -> None:
    content = detect_theme() + "\n"
    try:
        if path.read_text(encoding="utf-8") == content:
            return
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, content)


def watch_theme(path: Path = THEME_PATH) -> int:
    try:
        monitor = subprocess.Popen(
            ["gsettings", "monitor", SCHEMA], stdout=subprocess.PIPE, text=True,
        )
    except OSError as error:
        update_theme(path)
        print(f"desktop theme monitor unavailable: {error}", file=sys.stderr)
        return 1

    try:
        # Start listening before taking the snapshot so queued changes get read.
        update_theme(path)
        for line in monitor.stdout:
            if line.partition(":")[0].strip() in THEME_KEYS:
                update_theme(path)
        return monitor.wait() or 1  # The launcher retries a disconnected monitor.
    finally:
        if monitor.poll() is None:
            monitor.terminate()
        monitor.wait()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="write the current theme and exit")
    args = parser.parse_args(argv)
    if args.once:
        update_theme()
        return 0
    # Let standalone termination run watch_theme's child-process cleanup too.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    return watch_theme()


if __name__ == "__main__":
    raise SystemExit(main())

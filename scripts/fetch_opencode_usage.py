#!/usr/bin/env python3
import configparser
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "opencode-usage.json"
RENDER_PATH = CACHE_DIR / "opencode-usage-render.tsv"
LOG_PATH = CACHE_DIR / "conky-rate-limit-panel.log"
WEB_CACHE_PATH = CACHE_DIR / "opencode-web-cache.json"

FIVE_HOUR_LIMIT_USD = 12.0
WEEKLY_LIMIT_USD = 30.0
MONTHLY_LIMIT_USD = 60.0

FIVE_HOUR_WINDOW_SECONDS = common.FIVE_HOUR_WINDOW_SECONDS
WEEKLY_WINDOW_SECONDS = common.WEEKLY_WINDOW_SECONDS
MONTHLY_WINDOW_SECONDS = 31 * 24 * 60 * 60

WORKSPACE_URL_ENV = "OPENCODE_WORKSPACE_URL"
WORKSPACE_ID_ENV = "OPENCODE_WORKSPACE_ID"
COOKIE_ENV_NAMES = ("OPENCODE_COOKIE", "OPENCODE_AUTH_COOKIE")
FIREFOX_PROFILE_ENV = "OPENCODE_FIREFOX_PROFILE"
FIREFOX_HOME_ENV = "OPENCODE_FIREFOX_HOME"
COOKIE_HOST_SUFFIX = "opencode.ai"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36"


log_event = common.make_logger(LOG_PATH, "fetch_opencode_usage")
flatten_bars = common.flatten_bars


def workspace_url():
    configured = os.environ.get(WORKSPACE_URL_ENV, "").strip()
    if configured:
        return configured

    workspace_id = os.environ.get(WORKSPACE_ID_ENV, "").strip()
    if workspace_id:
        return f"https://opencode.ai/workspace/{workspace_id}/go"

    raise RuntimeError(
        f"{WORKSPACE_URL_ENV} or {WORKSPACE_ID_ENV} must be set for the OpenCode dashboard"
    )


def _normalize_cookie_env_value(env_name, value):
    # Accept a raw Cookie header, while allowing a single token to be
    # supplied as the historical auth-cookie shorthand.
    parts = [part.strip() for part in value.split(";") if part.strip()]
    if not parts:
        raise RuntimeError(f"{env_name} must contain a valid Cookie header")
    if all("=" in part for part in parts):
        return "; ".join(parts)
    if len(parts) == 1:
        return f"auth={parts[0]}"
    raise RuntimeError(f"{env_name} must contain a valid Cookie header")


def firefox_home():
    configured = os.environ.get(FIREFOX_HOME_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".mozilla" / "firefox"


def _profiles_ini_path(home):
    return Path(home) / "profiles.ini"


def resolve_firefox_profile_dir(home=None):
    """Pick the Firefox profile whose cookies.sqlite should supply auth."""
    home = Path(home or firefox_home())
    configured = os.environ.get(FIREFOX_PROFILE_ENV, "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.is_dir():
            return path
        candidate = home / configured
        if candidate.is_dir():
            return candidate
        raise RuntimeError(f"Firefox profile not found: {configured}")

    profiles_ini = _profiles_ini_path(home)
    if not profiles_ini.is_file():
        raise RuntimeError(f"Firefox profiles.ini missing: {profiles_ini}")

    parser = configparser.ConfigParser()
    parser.read(profiles_ini)

    def section_path(section):
        raw = parser.get(section, "Path", fallback="").strip()
        if not raw:
            return None
        path = Path(raw)
        if parser.getboolean(section, "IsRelative", fallback=True):
            path = home / path
        return path if path.is_dir() else None

    # Install* Default= is what current Firefox actually launches.
    for section in parser.sections():
        if not section.startswith("Install"):
            continue
        default_path = parser.get(section, "Default", fallback="").strip()
        if not default_path:
            continue
        path = Path(default_path)
        if not path.is_absolute():
            path = home / path
        if path.is_dir():
            return path

    for section in parser.sections():
        if not section.startswith("Profile"):
            continue
        if parser.get(section, "Default", fallback="") != "1":
            continue
        path = section_path(section)
        if path:
            return path

    for section in parser.sections():
        if not section.startswith("Profile"):
            continue
        path = section_path(section)
        if path and (path / "cookies.sqlite").is_file():
            return path

    raise RuntimeError(f"no usable Firefox profile found under {home}")


def _cookie_expiry_epoch_seconds(expiry):
    try:
        value = int(expiry)
    except (TypeError, ValueError):
        return 0
    # Some Firefox builds store moz_cookies.expiry in milliseconds.
    if value > 10_000_000_000:
        return value // 1000
    return value


def read_firefox_opencode_cookies(profile_dir=None):
    """Return name->value cookies for opencode.ai from Firefox's cookie DB."""
    profile_dir = Path(profile_dir or resolve_firefox_profile_dir())
    db_path = profile_dir / "cookies.sqlite"
    if not db_path.is_file():
        raise RuntimeError(f"Firefox cookies.sqlite missing: {db_path}")

    # Copy the live DB (and WAL siblings) so a locked Firefox profile still works.
    with tempfile.TemporaryDirectory(prefix="opencode-ff-cookies-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        tmp_db = tmp_root / "cookies.sqlite"
        shutil.copy2(db_path, tmp_db)
        for suffix in ("-wal", "-shm"):
            sibling = Path(str(db_path) + suffix)
            if sibling.is_file():
                shutil.copy2(sibling, Path(str(tmp_db) + suffix))

        connection = sqlite3.connect(f"file:{tmp_db}?mode=ro", uri=True)
        try:
            rows = connection.execute(
                """
                SELECT name, value, host, expiry
                FROM moz_cookies
                WHERE host = ? OR host = ? OR host LIKE ?
                ORDER BY name COLLATE NOCASE
                """,
                (COOKIE_HOST_SUFFIX, f".{COOKIE_HOST_SUFFIX}", f"%.{COOKIE_HOST_SUFFIX}"),
            ).fetchall()
        finally:
            connection.close()

    now = int(time.time())
    cookies = {}
    for name, value, _host, expiry in rows:
        if not name or value is None:
            continue
        expiry_seconds = _cookie_expiry_epoch_seconds(expiry)
        if expiry_seconds and expiry_seconds < now:
            continue
        cookies[str(name)] = str(value)

    if "auth" not in cookies:
        raise RuntimeError(
            f"Firefox profile {profile_dir.name} has no live opencode.ai auth cookie; "
            "log into opencode.ai in Firefox"
        )
    return cookies


def cookie_header_from_firefox(profile_dir=None):
    cookies = read_firefox_opencode_cookies(profile_dir)
    # Prefer auth first so the header matches a logged-in dashboard request.
    names = ["auth"] + sorted(name for name in cookies if name != "auth")
    return "; ".join(f"{name}={cookies[name]}" for name in names)


def cookie_header():
    for env_name in COOKIE_ENV_NAMES:
        value = os.environ.get(env_name, "").strip()
        if value:
            return _normalize_cookie_env_value(env_name, value)

    try:
        return cookie_header_from_firefox()
    except Exception as error:
        raise RuntimeError(
            "OpenCode dashboard cookie is missing; log into opencode.ai in Firefox "
            f"or set OPENCODE_COOKIE ({error})"
        ) from error


def parse_reset_time_to_seconds(reset_str):
    if not reset_str:
        return 0
    reset_str = unescape(str(reset_str)).lower().strip()

    def extract_unit(pattern):
        return sum(int(value) for value in re.findall(pattern, reset_str))

    days = extract_unit(r"(\d+)\s*(?:days?|d\b)")
    hours = extract_unit(r"(\d+)\s*(?:hours?|hrs?|h\b)")
    minutes = extract_unit(r"(\d+)\s*(?:minutes?|mins?|m\b)")
    seconds = extract_unit(r"(\d+)\s*(?:seconds?|secs?|s\b)")
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _slot_text(chunk, slot):
    match = re.search(
        rf'data-slot\s*=\s*["\']{re.escape(slot)}["\'][^>]*>(.*?)</',
        chunk,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return ""
    return re.sub(r"<[^>]+>", "", unescape(match.group(1))).strip()


def _window_key(label):
    normalized = label.lower().replace("–", "-").replace("—", "-")
    if (
        re.search(r"\b5\s*(?:h|hours?|hour)\b", normalized)
        or "5-hour" in normalized
        or "rolling" in normalized
    ):
        return "5h"
    if "week" in normalized:
        return "weekly"
    if "month" in normalized:
        return "monthly"
    return None


def _window_spec(label):
    return {
        "5h": (FIVE_HOUR_LIMIT_USD, FIVE_HOUR_WINDOW_SECONDS),
        "weekly": (WEEKLY_LIMIT_USD, WEEKLY_WINDOW_SECONDS),
        "monthly": (MONTHLY_LIMIT_USD, MONTHLY_WINDOW_SECONDS),
    }[label]


def parse_usage_html(html, now_epoch=None):
    """Parse the three usage cards rendered by the OpenCode dashboard."""
    now_epoch = int(now_epoch if now_epoch is not None else datetime.now(timezone.utc).timestamp())
    windows = {}

    # The dashboard marks each card with usage-item. Keep the card boundary so
    # similarly named elements elsewhere on the page cannot be mixed together.
    chunks = re.split(r"(?=usage-item\b)", html, flags=re.IGNORECASE)[1:]
    for chunk in chunks:
        label = _slot_text(chunk[:4000], "usage-label")
        value = _slot_text(chunk[:4000], "usage-value")
        window = _window_key(label)
        if not window or not re.fullmatch(r"\d+(?:\.\d+)?%", value):
            continue

        used_percent = max(0.0, min(100.0, float(value[:-1])))
        reset_text = _slot_text(chunk[:4000], "reset-time")
        reset_text = re.sub(r"^resets in\s*", "", reset_text, flags=re.IGNORECASE).strip()
        reset_after_seconds = parse_reset_time_to_seconds(reset_text)
        reset_at_epoch = now_epoch + reset_after_seconds if reset_after_seconds > 0 else 0
        resets_at = (
            datetime.fromtimestamp(reset_at_epoch, tz=timezone.utc).isoformat()
            if reset_at_epoch > 0
            else None
        )
        limit_usd, window_seconds = _window_spec(window)
        windows[window] = {
            "label": window,
            "usedPercent": round(used_percent, 1),
            "remainingPercent": round(100.0 - used_percent, 1),
            "resetsAt": resets_at,
            "resetAtEpoch": reset_at_epoch,
            "resetAfterSeconds": reset_after_seconds,
            "windowSeconds": window_seconds,
            "costUsd": round((used_percent / 100.0) * limit_usd, 4),
            "limitUsd": limit_usd,
        }

    expected = ("5h", "weekly", "monthly")
    missing = [label for label in expected if label not in windows]
    if missing:
        raise RuntimeError(f"OpenCode dashboard usage cards missing: {', '.join(missing)}")
    return [windows[label] for label in expected]


def fetch_usage_from_web(url=None, cookies=None):
    """Fetch usage from the OpenCode web dashboard only."""
    url = url or workspace_url()
    cookies = cookies or cookie_header()
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Cookie": cookies,
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            final_url = response.geturl()
            if any(marker in final_url.lower() for marker in ("/login", "/authorize", "auth.opencode.ai")):
                raise RuntimeError("OpenCode dashboard session expired (redirected to login)")
            html = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"OpenCode dashboard returned HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"OpenCode dashboard request failed: {error.reason}") from error

    return parse_usage_html(html)


def save_web_cache(windows, url):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        common.atomic_write_json(
            WEB_CACHE_PATH,
            {
                "fetched_at": int(datetime.now(timezone.utc).timestamp()),
                "workspace_url": url,
                "windows": windows,
            },
        )
    except OSError:
        pass


def load_web_cache(url):
    try:
        raw = json.loads(WEB_CACHE_PATH.read_text(encoding="utf-8"))
        if raw.get("workspace_url") != url:
            return None
        windows = raw.get("windows")
        if isinstance(windows, list) and len(windows) == 3:
            return windows
    except (FileNotFoundError, json.JSONDecodeError, OSError, AttributeError):
        pass
    return None


def account_payload(label, windows, stale=False, error="", ok=True):
    account = {
        "ok": ok,
        "label": label,
        "email": "",
        "accountId": "",
        "planType": "go",
        "isSelected": True,
        "windows": windows,
        "staleCache": stale,
    }
    if error:
        account["error"] = error
    return account


def empty_usage_windows():
    """Placeholder 5h/weekly/monthly bars so the row stays visible on hard failure."""
    return [
        {
            "label": label,
            "usedPercent": 0.0,
            "remainingPercent": 100.0,
            "resetsAt": None,
            "resetAtEpoch": 0,
            "resetAfterSeconds": 0,
            "windowSeconds": window_seconds,
            "costUsd": 0.0,
            "limitUsd": limit_usd,
        }
        for label, limit_usd, window_seconds in (
            ("5h", FIVE_HOUR_LIMIT_USD, FIVE_HOUR_WINDOW_SECONDS),
            ("weekly", WEEKLY_LIMIT_USD, WEEKLY_WINDOW_SECONDS),
            ("monthly", MONTHLY_LIMIT_USD, MONTHLY_WINDOW_SECONDS),
        )
    ]


def write_error(message, label="default"):
    account = account_payload(
        label,
        empty_usage_windows(),
        stale=True,
        error=message,
        ok=False,
    )
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "OpenCode",
        "ok": False,
        "error": message,
        "accounts": [account],
        "bars": flatten_bars([account]),
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
    log_event(f"error: {message}")


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()
    label = os.environ.get("OPENCODE_USAGE_LABEL", "default").strip() or "default"

    try:
        url = workspace_url()
        windows = fetch_usage_from_web(url)
        save_web_cache(windows, url)
        account = account_payload(label, windows)
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "OpenCode",
            "ok": True,
            "accounts": [account],
            "bars": flatten_bars([account]),
        }
        common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
        log_event(f"completed web fetch account={label} wrote={OUTPUT_PATH.name}")
        print(json.dumps(output, indent=2))
        return 0
    except Exception as web_error:
        log_event(f"web fetch failed ({web_error})")
        try:
            url = workspace_url()
        except RuntimeError:
            url = ""
        cached_windows = load_web_cache(url) if url else None
        if cached_windows:
            error = f"using stale web cache after {web_error}"
            account = account_payload(label, cached_windows, stale=True, error=error)
            output = {
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "provider": "OpenCode",
                "ok": True,
                "accounts": [account],
                "bars": flatten_bars([account]),
            }
            common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
            log_event(f"using stale web usage cache for account={label}")
            print(json.dumps(output, indent=2))
            return 0

        write_error(f"OpenCode web usage fetch failed: {web_error}", label=label)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

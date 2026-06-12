#!/usr/bin/env python3
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "claude-usage.json"
RENDER_PATH = CACHE_DIR / "claude-usage-render.tsv"
LOG_PATH = CACHE_DIR / "conky-codex.log"
DEFAULT_CREDENTIALS_NAME = ".credentials.json"
CREDENTIALS_PREFIX = ".credentials.json."
USAGE_URL = "https://api.anthropic.com/v1/messages"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
PROFILE_URL = "https://api.anthropic.com/api/oauth/profile"
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
TOKEN_REFRESH_MARGIN_SECONDS = 300
DEFAULT_TOKEN_LIFETIME_SECONDS = 8 * 60 * 60
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
SYSTEM_PROMPT = "You are Claude Code, Anthropic's official CLI for Claude."
FIVE_HOUR_WINDOW_SECONDS = common.FIVE_HOUR_WINDOW_SECONDS
WEEKLY_WINDOW_SECONDS = common.WEEKLY_WINDOW_SECONDS


class QuotaAuthError(RuntimeError):
    """The usage probe was rejected because the access token is expired or revoked."""


log_event = common.make_logger(LOG_PATH, "fetch_claude_usage")
atomic_write_json = common.atomic_write_json
as_float = common.as_float
as_int = common.as_int
flatten_bars = common.flatten_bars


def claude_home():
    return Path(os.environ.get("CLAUDE_HOME", Path.home() / ".claude")).expanduser()


def default_credentials_path():
    return claude_home() / DEFAULT_CREDENTIALS_NAME


def usage_cache_ttl_seconds():
    return as_int(os.environ.get("CLAUDE_USAGE_TTL"), 300)


def configured_credentials_path():
    configured = os.environ.get("CLAUDE_CREDENTIALS_PATH", "").strip()
    if not configured:
        configured = os.environ.get("CLAUDE_AUTH_PATH", "").strip()
    return Path(configured).expanduser() if configured else None


def discover_credentials():
    default_token = default_access_token()
    configured_path = configured_credentials_path()
    if configured_path:
        return [(configured_label(configured_path), configured_path, is_selected_credentials(configured_path, default_token))]

    suffixed_paths = sorted(path for path in claude_home().glob(f"{DEFAULT_CREDENTIALS_NAME}.*") if path.is_file())
    if suffixed_paths:
        return [(credentials_label(path), path, is_selected_credentials(path, default_token)) for path in suffixed_paths]

    path = default_credentials_path()
    return [(configured_label(path), path, is_selected_credentials(path, default_token))]


def configured_label(path):
    return os.environ.get("CLAUDE_USAGE_LABEL", "").strip() or credentials_label(path)


def credentials_label(path):
    name = path.name
    if name.startswith(CREDENTIALS_PREFIX) and len(name) > len(CREDENTIALS_PREFIX):
        return name[len(CREDENTIALS_PREFIX):]
    if name == DEFAULT_CREDENTIALS_NAME:
        return "default"
    if name.endswith(".json"):
        return name[:-5].lstrip(".") or path.stem
    return path.stem.lstrip(".") or name


def credentials_access_token(path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    oauth = raw.get("claudeAiOauth")
    return (oauth.get("accessToken", "") or "") if isinstance(oauth, dict) else ""


def default_access_token():
    return credentials_access_token(default_credentials_path())


def is_selected_credentials(path, default_token=""):
    """A credentials file marks the live login when it is the default file
    itself or carries the same access token as the default file. Claude Code
    replaces the default file on login and token refresh, so path identity
    (symlinks) cannot be relied on."""
    default_path = default_credentials_path()
    try:
        if default_path.resolve() == path.resolve():
            return True
    except OSError:
        if default_path == path:
            return True
    return bool(default_token) and credentials_access_token(path) == default_token


def read_credentials(label, path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"missing Claude credentials file: {path}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid Claude credentials JSON: {error}") from error

    oauth = raw.get("claudeAiOauth") or {}
    access_token = oauth.get("accessToken", "")
    if not access_token:
        raise RuntimeError(f"credentials file has no claudeAiOauth.accessToken: {path}")

    return {
        "label": label,
        "path": path,
        "access_token": access_token,
        "refresh_token": oauth.get("refreshToken", ""),
        "expires_at": epoch_seconds(oauth.get("expiresAt")),
        "plan_type": os.environ.get("CLAUDE_PLAN_TYPE", "").strip()
        or oauth.get("subscriptionType", "")
        or oauth.get("rateLimitTier", ""),
        "email": "",
    }


def epoch_seconds(value):
    """Claude Code stores expiresAt in milliseconds; accept seconds too."""
    epoch = as_int(value)
    return epoch // 1000 if epoch > 10**11 else epoch


def token_needs_refresh(auth):
    if not auth.get("refresh_token") or not auth.get("expires_at"):
        return False
    now = int(datetime.now(timezone.utc).timestamp())
    return auth["expires_at"] - now < TOKEN_REFRESH_MARGIN_SECONDS


def persist_credentials(auth):
    path = auth["path"]
    write_path = path.resolve() if path.is_symlink() else path
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    oauth = raw.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        oauth = {}
        raw["claudeAiOauth"] = oauth
    oauth["accessToken"] = auth["access_token"]
    oauth["refreshToken"] = auth["refresh_token"]
    oauth["expiresAt"] = auth["expires_at"] * 1000

    tmp_path = write_path.with_name(f".{write_path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
        tmp_file.write(json.dumps(raw, indent=2))
    os.replace(tmp_path, write_path)


def refresh_credentials(auth):
    if not auth.get("refresh_token"):
        raise RuntimeError(f"credentials file has no claudeAiOauth.refreshToken: {auth['path']}")

    body = json.dumps(
        {
            "grant_type": "refresh_token",
            "refresh_token": auth["refresh_token"],
            "client_id": OAUTH_CLIENT_ID,
        }
    ).encode("utf-8")
    request = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    request.add_header("content-type", "application/json")
    request.add_header("user-agent", "claude-cli/2.1.162 (external, cli)")

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"Claude OAuth token refresh failed: HTTP {error.code}: {detail}") from error
    except (urllib.error.URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Claude OAuth token refresh failed: {error}") from error

    access_token = payload.get("access_token", "")
    if not access_token:
        raise RuntimeError("Claude OAuth token refresh returned no access_token")

    lifetime_seconds = as_int(payload.get("expires_in"), DEFAULT_TOKEN_LIFETIME_SECONDS)
    auth["access_token"] = access_token
    auth["refresh_token"] = payload.get("refresh_token") or auth["refresh_token"]
    auth["expires_at"] = int(datetime.now(timezone.utc).timestamp()) + lifetime_seconds
    persist_credentials(auth)
    log_event(f"account={auth['label']} refreshed Claude OAuth token lifetime={lifetime_seconds}s")
    return auth


def fetch_profile_email(access_token):
    request = urllib.request.Request(PROFILE_URL)
    request.add_header("authorization", f"Bearer {access_token}")
    request.add_header("anthropic-beta", "oauth-2025-04-20")
    request.add_header("user-agent", "claude-cli/2.1.162 (external, cli)")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Claude profile request failed: {error}") from error
    return (payload.get("account") or {}).get("email", "") or ""


def discover_account_email(auth):
    try:
        return fetch_profile_email(auth["access_token"])
    except RuntimeError as error:
        log_event(f"account={auth['label']} profile lookup failed: {error}")
        return ""


def is_invalid_grant(error):
    return "invalid_grant" in str(error)


def adopt_default_credentials(auth, expected_email, error):
    """Claude Code rotates the refresh token of the logged-in account, which kills any
    copied credentials file for that account. When that happens, take the credentials
    from the live default file, but only after the profile email confirms it is the
    same account."""
    if not is_invalid_grant(error) or not expected_email:
        return False

    default_path = default_credentials_path()
    try:
        if default_path.resolve() == auth["path"].resolve():
            return False
        default_auth = read_credentials(auth["label"], default_path)
        if token_needs_refresh(default_auth):
            # Claude Code owns the default file: never refresh (write) it here.
            # Wait for Claude Code to rotate it and adopt on a later pass.
            return False
        if fetch_profile_email(default_auth["access_token"]) != expected_email:
            return False
    except (OSError, RuntimeError):
        return False

    auth["access_token"] = default_auth["access_token"]
    auth["refresh_token"] = default_auth["refresh_token"]
    auth["expires_at"] = default_auth["expires_at"]
    persist_credentials(auth)
    log_event(f"account={auth['label']} adopted credentials from {default_path.name} after refresh token rotation")
    return True


def detect_default_rotation(default_token):
    """True exactly once each time the default file's access token changes."""
    if not default_token:
        return False
    marker_path = CACHE_DIR / "claude-default-token.fingerprint"
    fingerprint = hashlib.sha256(default_token.encode("utf-8")).hexdigest()
    try:
        if marker_path.read_text(encoding="utf-8").strip() == fingerprint:
            return False
    except OSError:
        pass
    try:
        marker_path.write_text(fingerprint, encoding="utf-8")
    except OSError:
        pass
    return True


def sync_copies_with_default(credentials):
    """Claude Code rotated the login tokens and no copied file carries them yet.
    Copy them into the suffixed file whose recorded email matches the live
    account so that file's grant never goes stale. Never writes the default
    file."""
    try:
        default_auth = read_credentials("default", default_credentials_path())
    except RuntimeError:
        return
    if token_needs_refresh(default_auth):
        return
    try:
        email = fetch_profile_email(default_auth["access_token"])
    except RuntimeError as error:
        log_event(f"default credentials profile lookup failed: {error}")
        return
    if not email:
        return
    for label, path, is_selected in credentials:
        if is_selected:
            continue
        cached = read_account_cache(label)
        if not isinstance(cached, dict) or (cached.get("email", "") or "") != email:
            continue
        auth = {
            "label": label,
            "path": path,
            "access_token": default_auth["access_token"],
            "refresh_token": default_auth["refresh_token"],
            "expires_at": default_auth["expires_at"],
        }
        persist_credentials(auth)
        log_event(f"account={label} synced credentials from {DEFAULT_CREDENTIALS_NAME} after token rotation")


def optional_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def optional_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def quota_request(auth):
    model = os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", DEFAULT_MODEL)
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 1,
            "system": [{"type": "text", "text": SYSTEM_PROMPT}],
            "messages": [{"role": "user", "content": "quota"}],
        }
    ).encode("utf-8")
    request = urllib.request.Request(USAGE_URL, data=body, method="POST")
    request.add_header("authorization", f"Bearer {auth['access_token']}")
    request.add_header("anthropic-version", "2023-06-01")
    request.add_header("anthropic-beta", "oauth-2025-04-20")
    request.add_header("content-type", "application/json")
    request.add_header("user-agent", "claude-cli/2.1.162 (external, cli)")

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.headers, ""
    except urllib.error.HTTPError as error:
        body_text = error.read().decode("utf-8", errors="replace")
        return error.code, error.headers, body_text[:500]
    except urllib.error.URLError as error:
        raise RuntimeError(f"Claude usage API request failed: {error.reason}") from error


def usage_from_headers(headers):
    usage = {}
    for window, key in (("5h", "five_hour"), ("7d", "seven_day")):
        utilization = optional_float(headers.get(f"anthropic-ratelimit-unified-{window}-utilization"))
        reset_at = optional_int(headers.get(f"anthropic-ratelimit-unified-{window}-reset"))
        if utilization is None:
            continue
        usage[key] = {
            "used_percentage": max(0.0, min(100.0, utilization * 100)),
            "resets_at": reset_at,
        }
    return usage


def fetch_quota_usage(auth):
    status, headers, body_text = quota_request(auth)
    usage = usage_from_headers(headers)
    if usage:
        return usage, status

    detail = f": {body_text}" if body_text else ""
    message = f"Claude usage API returned no rate-limit headers: HTTP {status}{detail}"
    if status == 401:
        raise QuotaAuthError(message)
    raise RuntimeError(message)


def shares_default_grant(auth):
    """True when these credentials hold the same OAuth grant (refresh token) as
    the live login file. Refreshing that grant here would rotate it and revoke
    the refresh token Claude Code holds, forcing the user to log in again."""
    if not auth.get("refresh_token"):
        return False
    try:
        raw = json.loads(default_credentials_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    oauth = raw.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        return False
    return oauth.get("refreshToken", "") == auth["refresh_token"]


def refresh_or_adopt(auth, expected_email):
    if shares_default_grant(auth):
        raise RuntimeError(
            "token expired but its grant is shared with the live Claude Code login; "
            "waiting for Claude Code to rotate it"
        )
    try:
        refresh_credentials(auth)
    except RuntimeError as error:
        if not adopt_default_credentials(auth, expected_email, error):
            raise


def fetch_fresh_usage(auth, expected_email=""):
    refreshed = False
    if token_needs_refresh(auth):
        refresh_or_adopt(auth, expected_email)
        refreshed = True
    try:
        return fetch_quota_usage(auth)
    except QuotaAuthError:
        if refreshed:
            raise
        refresh_or_adopt(auth, expected_email)
        return fetch_quota_usage(auth)


def safe_cache_label(label):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("._")
    return safe or "default"


def account_cache_path(label):
    return CACHE_DIR / f"claude-usage-cache-{safe_cache_label(label)}.json"


def read_account_cache(label):
    try:
        return json.loads(account_cache_path(label).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_account_cache(label, usage, status, email=""):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(usage)
    payload["fetched_at"] = int(datetime.now(timezone.utc).timestamp())
    payload["source"] = "api"
    payload["status"] = status
    if email:
        payload["email"] = email
    atomic_write_json(account_cache_path(label), payload)


def normalize_window(label, raw_window, fetched_at):
    if not isinstance(raw_window, dict):
        return None

    used_percent = max(0.0, min(100.0, as_float(raw_window.get("used_percentage"))))
    reset_at = as_int(raw_window.get("resets_at"))
    if reset_at <= int(fetched_at.timestamp()):
        return None

    reset_after_seconds = max(0, reset_at - int(fetched_at.timestamp()))
    window_seconds = WEEKLY_WINDOW_SECONDS if label == "weekly" else FIVE_HOUR_WINDOW_SECONDS

    return {
        "label": label,
        "usedPercent": round(used_percent, 1),
        "remainingPercent": max(0, round(100 - used_percent, 1)),
        "resetsAt": datetime.fromtimestamp(reset_at, tz=timezone.utc).isoformat(),
        "resetAtEpoch": reset_at,
        "resetAfterSeconds": reset_after_seconds,
        "windowSeconds": window_seconds,
    }


def windows_from_usage(usage):
    fetched_at = datetime.now(timezone.utc)
    windows = []
    for label, key in (("5h", "five_hour"), ("weekly", "seven_day")):
        window = normalize_window(label, usage.get(key), fetched_at)
        if window:
            windows.append(window)
    return windows


def cache_is_fresh(cache):
    if not isinstance(cache, dict) or not windows_from_usage(cache):
        return False
    return int(datetime.now(timezone.utc).timestamp()) - as_int(cache.get("fetched_at")) < usage_cache_ttl_seconds()


def account_from_usage(auth, usage, is_selected, error="", stale=False):
    windows = windows_from_usage(usage)
    account = {
        "ok": bool(windows),
        "label": auth["label"],
        "email": auth.get("email", ""),
        "planType": auth.get("plan_type", ""),
        "isSelected": is_selected,
        "windows": windows,
    }
    if error:
        account["error"] = error
    if stale:
        account["staleCache"] = True
    if not windows and not error:
        account["error"] = "Claude usage API returned no future rate-limit windows."
    return account


def normalize_error(label, message, is_selected=False):
    return {
        "ok": False,
        "label": label,
        "error": message,
        "isSelected": is_selected,
        "windows": [],
    }


def fetch_account(label, path, is_selected):
    try:
        auth = read_credentials(label, path)
        cached = read_account_cache(label)
        if isinstance(cached, dict):
            auth["email"] = cached.get("email", "") or ""
        if cache_is_fresh(cached):
            account = account_from_usage(auth, cached, is_selected)
            log_event(f"account={label} using cached Claude usage windows={len(account['windows'])}")
            return account

        try:
            usage, status = fetch_fresh_usage(auth, auth.get("email", ""))
            if not auth.get("email"):
                auth["email"] = discover_account_email(auth)
            write_account_cache(label, usage, status, auth.get("email", ""))
            account = account_from_usage(auth, usage, is_selected)
            log_event(
                f"account={label} completed plan={account['planType'] or 'unknown'} "
                f"windows={len(account['windows'])} status={status}"
            )
            return account
        except Exception as error:
            if isinstance(cached, dict) and windows_from_usage(cached):
                account = account_from_usage(auth, cached, is_selected, f"using stale cache after {error}", stale=True)
                log_event(f"account={label} using stale Claude usage cache after error: {error}")
                return account
            raise
    except Exception as error:
        return normalize_error(label, str(error), is_selected)


def write_error(message):
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "Claude",
        "ok": False,
        "error": message,
        "accounts": [],
        "bars": [],
    }
    common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
    log_event(f"error: {message}")


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()
    credentials = discover_credentials()
    labels = ",".join(label for label, _, _ in credentials)
    log_event(f"starting Claude usage fetch accounts={labels or 'none'}")

    if detect_default_rotation(default_access_token()) and not any(selected for _, _, selected in credentials):
        sync_copies_with_default(credentials)
        credentials = discover_credentials()

    try:
        accounts = [fetch_account(label, path, is_selected) for label, path, is_selected in credentials]
        ok_count = sum(1 for account in accounts if account.get("ok"))
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "Claude",
            "ok": ok_count > 0,
            "accounts": accounts,
            "bars": flatten_bars(accounts),
        }
        common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
        log_event(f"completed fetch accounts={len(accounts)} ok={ok_count} wrote={OUTPUT_PATH.name}")
        print(json.dumps(output, indent=2))
        return 0 if ok_count > 0 else 1
    except Exception as error:
        write_error(f"Claude usage fetch failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

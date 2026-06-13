#!/usr/bin/env python3
import base64
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "codex-usage.json"
RENDER_PATH = CACHE_DIR / "codex-usage-render.tsv"
LOG_PATH = CACHE_DIR / "conky-rate-limit-panel.log"
DEFAULT_AUTH_PATH = Path.home() / ".codex" / "auth.json"
CODEX_HOME = Path.home() / ".codex"
CODEX_SQLITE_HOME = CODEX_HOME
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
FIVE_HOUR_WINDOW_SECONDS = common.FIVE_HOUR_WINDOW_SECONDS
WEEKLY_WINDOW_SECONDS = common.WEEKLY_WINDOW_SECONDS
LONG_WINDOW_THRESHOLD_SECONDS = 24 * 60 * 60
DEGENERATE_RETRIES = 4
LOCAL_RATE_LIMIT_MAX_AGE_SECONDS = 21600
LOCAL_WINDOW_RESET_TOLERANCE_SECONDS = 5


log_event = common.make_logger(LOG_PATH, "fetch_codex_usage")
atomic_write_json = common.atomic_write_json
as_float = common.as_float
as_int = common.as_int
parse_iso_epoch = common.parse_iso_epoch
flatten_bars = common.flatten_bars


def configure_from_env():
    global CODEX_HOME
    global CODEX_SQLITE_HOME
    global DEGENERATE_RETRIES
    global LOCAL_RATE_LIMIT_MAX_AGE_SECONDS

    CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    CODEX_SQLITE_HOME = Path(os.environ.get("CODEX_SQLITE_HOME", CODEX_HOME)).expanduser()
    DEGENERATE_RETRIES = int(os.environ.get("CODEX_USAGE_DEGENERATE_RETRIES", "4"))
    LOCAL_RATE_LIMIT_MAX_AGE_SECONDS = int(os.environ.get("CODEX_LOCAL_RATE_LIMIT_MAX_AGE_SECONDS", "21600"))


def discover_auth_files():
    configured_path = os.environ.get("CODEX_AUTH_PATH", "").strip()
    if configured_path:
        path = Path(configured_path).expanduser()
        return [(auth_label(path), path, is_selected_auth(path))]

    suffixed_paths = sorted(DEFAULT_AUTH_PATH.parent.glob("auth.json.*"))
    if suffixed_paths:
        return [(auth_label(path), path, is_selected_auth(path)) for path in suffixed_paths if path.is_file()]

    return [("default", DEFAULT_AUTH_PATH, is_selected_auth(DEFAULT_AUTH_PATH))]


def is_selected_auth(path):
    try:
        return DEFAULT_AUTH_PATH.resolve() == path.resolve()
    except OSError:
        return False


def auth_label(path):
    name = path.name
    prefix = "auth.json."
    if name.startswith(prefix) and len(name) > len(prefix):
        return name[len(prefix):]
    return path.stem


def read_auth(label, path):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"missing auth file: {path}")
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid auth JSON: {error}") from error

    tokens = raw.get("tokens") or {}
    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    account_id = tokens.get("account_id", "")
    id_token = tokens.get("id_token", "")

    if not access_token:
        raise RuntimeError(f"auth file has no tokens.access_token: {path}")

    return {
        "label": label,
        "path": path,
        "raw": raw,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "account_id": account_id,
        "email": extract_email(raw, id_token),
    }


def extract_email(raw, id_token):
    user = raw.get("user")
    if isinstance(user, dict) and user.get("email"):
        return user["email"]

    if raw.get("email"):
        return raw["email"]

    return email_from_jwt(id_token)


def email_from_jwt(token):
    parts = token.split(".")
    if len(parts) < 2:
        return ""

    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        data = base64.urlsafe_b64decode(payload.encode("ascii"))
        claims = json.loads(data.decode("utf-8"))
    except Exception:
        return ""

    return claims.get("email", "")


def codex_request(auth):
    request = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {auth['access_token']}",
            "Accept": "application/json",
            "User-Agent": "conky-rate-limit-panel",
        },
        method="GET",
    )

    if auth["account_id"]:
        request.add_header("ChatGPT-Account-Id", auth["account_id"])

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"error": body[:500]}
        return error.code, parsed


def refresh_token(auth):
    if not auth["refresh_token"]:
        raise RuntimeError("auth file has no tokens.refresh_token")

    payload = urllib.parse.urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": auth["refresh_token"],
            "client_id": CLIENT_ID,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        TOKEN_URL,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))

    access_token = result.get("access_token")
    if not access_token:
        raise RuntimeError("refresh response did not include access_token")

    tokens = auth["raw"].setdefault("tokens", {})
    tokens["access_token"] = access_token
    if result.get("refresh_token"):
        tokens["refresh_token"] = result["refresh_token"]

    auth["access_token"] = access_token
    auth["refresh_token"] = tokens.get("refresh_token", auth["refresh_token"])
    atomic_write_json(auth["path"], auth["raw"])
    os.chmod(auth["path"], 0o600)


def latest_rollout_paths(limit=20):
    db_path = CODEX_SQLITE_HOME / "state_5.sqlite"
    if db_path.is_file():
        try:
            connection = sqlite3.connect(db_path)
            try:
                rows = connection.execute(
                    "select rollout_path from threads where archived = 0 order by updated_at desc limit ?",
                    (limit,),
                ).fetchall()
            finally:
                connection.close()
            paths = [Path(row[0]).expanduser() for row in rows if row and row[0]]
            if paths:
                return paths
        except sqlite3.Error as error:
            log_event(f"could not read Codex state sqlite for local rate limits: {error}")

    return sorted(CODEX_HOME.glob("sessions/**/*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)[:limit]


def read_latest_local_rate_limits():
    now = int(datetime.now(timezone.utc).timestamp())
    best = None

    for path in latest_rollout_paths():
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as rollout:
                for line in rollout:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    payload = row.get("payload") or {}
                    if not isinstance(payload, dict) or not isinstance(payload.get("rate_limits"), dict):
                        continue
                    event_epoch = parse_iso_epoch(row.get("timestamp"))
                    if not event_epoch:
                        continue
                    rate_limits = payload["rate_limits"]
                    if not local_rate_limits_have_future_window(rate_limits, now):
                        continue
                    if now - event_epoch > LOCAL_RATE_LIMIT_MAX_AGE_SECONDS:
                        continue
                    if not best or event_epoch > best["eventEpoch"]:
                        best = {
                            "eventEpoch": event_epoch,
                            "path": path,
                            "rateLimits": rate_limits,
                        }
        except OSError as error:
            log_event(f"could not read Codex rollout for local rate limits path={path}: {error}")

    return best


def local_rate_limits_have_future_window(rate_limits, now):
    for key in ("primary", "secondary"):
        window = rate_limits.get(key)
        if isinstance(window, dict) and as_int(window.get("window_minutes")) > 0 and as_int(window.get("resets_at")) > now:
            return True
    return False


def local_rate_limit_windows(local_rate_limits):
    if not local_rate_limits:
        return []

    rate_limits = local_rate_limits["rateLimits"]
    now = int(datetime.now(timezone.utc).timestamp())
    windows = []
    primary = normalize_local_rate_limit_window("5h", rate_limits.get("primary"), now)
    secondary = normalize_local_rate_limit_window("weekly", rate_limits.get("secondary"), now)
    if primary:
        windows.append(primary)
    if secondary:
        windows.append(secondary)
    return windows


def normalize_local_rate_limit_window(label, window, now):
    if not isinstance(window, dict):
        return None

    reset_at = as_int(window.get("resets_at"))
    window_seconds = as_int(window.get("window_minutes")) * 60
    used_percent = max(0.0, min(100.0, as_float(window.get("used_percent"))))
    if reset_at <= now or window_seconds <= 0:
        return None

    return {
        "label": label,
        "usedPercent": round(used_percent, 1),
        "remainingPercent": max(0, round(100 - used_percent, 1)),
        "resetsAt": datetime.fromtimestamp(reset_at, tz=timezone.utc).isoformat(),
        "resetAtEpoch": reset_at,
        "resetAfterSeconds": max(0, reset_at - now),
        "windowSeconds": window_seconds,
    }


def meaningful_window_count(usage):
    rate_limit = usage.get("rate_limit") if isinstance(usage, dict) else None
    if not isinstance(rate_limit, dict):
        return 0

    count = 0
    now = int(datetime.now(timezone.utc).timestamp())
    for key in ("primary_window", "secondary_window"):
        window = rate_limit.get(key)
        if not isinstance(window, dict):
            continue
        if as_int(window.get("limit_window_seconds")) > 0 and as_int(window.get("reset_at")) > now:
            count += 1
    return count


def should_retry_degenerate_usage(usage):
    if not isinstance(usage, dict):
        return False
    plan_type = str(usage.get("plan_type", "")).lower()
    if plan_type not in ("plus", "pro", "team", "enterprise"):
        return False
    return meaningful_window_count(usage) == 0


def is_paid_plan(plan_type):
    return str(plan_type or "").lower() in ("plus", "pro", "team", "enterprise")


def retry_degenerate_usage(auth, label, usage):
    best_usage = usage
    best_score = meaningful_window_count(usage)

    if not should_retry_degenerate_usage(usage):
        return usage

    for attempt in range(1, DEGENERATE_RETRIES + 1):
        time.sleep(1)
        status, retry_usage = codex_request(auth)
        if status != 200:
            log_event(f"account={label} degenerate retry={attempt} returned HTTP {status}")
            continue

        score = meaningful_window_count(retry_usage)
        log_event(f"account={label} degenerate retry={attempt} meaningful_windows={score}")
        if score > best_score:
            best_usage = retry_usage
            best_score = score
        if score >= 2:
            break

    return best_usage


def load_previous_accounts():
    try:
        previous = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    accounts = {}
    for account in previous.get("accounts", []):
        label = account.get("label", "")
        if label:
            accounts[label] = account
    return accounts


def future_windows(account):
    now = int(datetime.now(timezone.utc).timestamp())
    windows = []
    for window in account.get("windows", []):
        reset_at = as_int(window.get("resetAtEpoch"))
        if reset_at > now:
            windows.append(window)
    return windows


def carry_forward_previous_windows(account, previous_accounts):
    previous = previous_accounts.get(account.get("label", ""))
    if not previous:
        return account

    previous_windows = future_windows(previous)
    if not previous_windows:
        return account

    current_has_future_window = any(as_int(window.get("resetAtEpoch")) > 0 for window in account.get("windows", []))
    if current_has_future_window:
        return account

    plan_type = str(account.get("planType") or previous.get("planType") or "").lower()
    if plan_type not in ("plus", "pro", "team", "enterprise"):
        return account

    account["windows"] = previous_windows
    account["carriedForward"] = True
    account["error"] = account.get("error", "")
    return account


def normalize_window(label, window, fetched_at):
    if not isinstance(window, dict):
        return None

    limit_window_seconds = as_int(window.get("limit_window_seconds"))
    used_percent = max(0.0, min(100.0, as_float(window.get("used_percent"))))
    reset_at = as_float(window.get("reset_at"))
    reset_after_seconds = as_int(window.get("reset_after_seconds"))
    resets_at_iso = None

    if reset_at:
        resets_at_iso = datetime.fromtimestamp(reset_at, tz=timezone.utc).isoformat()
        if reset_after_seconds <= 0:
            reset_after_seconds = max(0, int(reset_at - fetched_at.timestamp()))
    elif reset_after_seconds > 0:
        reset_at = fetched_at.timestamp() + reset_after_seconds
        resets_at_iso = datetime.fromtimestamp(reset_at, tz=timezone.utc).isoformat()

    if used_percent <= 0 and reset_after_seconds <= 0:
        reset_at = 0
        resets_at_iso = None

    normalized_label = label
    if label == "5h" and reset_after_seconds > LONG_WINDOW_THRESHOLD_SECONDS:
        normalized_label = "weekly"
    window_seconds = limit_window_seconds if limit_window_seconds > 0 else WEEKLY_WINDOW_SECONDS if normalized_label == "weekly" else FIVE_HOUR_WINDOW_SECONDS

    return {
        "label": normalized_label,
        "usedPercent": round(used_percent, 1),
        "remainingPercent": max(0, round(100 - used_percent, 1)),
        "resetsAt": resets_at_iso,
        "resetAtEpoch": int(reset_at) if reset_at else 0,
        "resetAfterSeconds": max(0, reset_after_seconds),
        "windowSeconds": window_seconds,
    }


def normalize_usage(auth, usage, is_selected):
    rate_limit = usage.get("rate_limit") or {}
    plan_type = usage.get("plan_type", "")
    fetched_at = datetime.now(timezone.utc)
    windows = []
    labels_seen = set()

    if is_paid_plan(plan_type) and meaningful_window_count(usage) == 0:
        return {
            "ok": True,
            "label": auth["label"],
            "email": auth["email"],
            "accountId": auth["account_id"],
            "planType": plan_type,
            "isSelected": is_selected,
            "windows": [],
            "error": "Codex usage API returned a degenerate paid-account quota response.",
        }

    for label, key in (("5h", "primary_window"), ("weekly", "secondary_window")):
        normalized = normalize_window(label, rate_limit.get(key), fetched_at)
        if not normalized:
            continue
        if normalized["label"] in labels_seen:
            log_event(f"account={auth['label']} skipped duplicate {normalized['label']} window from {key}")
            continue
        labels_seen.add(normalized["label"])
        windows.append(normalized)

    return {
        "ok": True,
        "label": auth["label"],
        "email": auth["email"],
        "accountId": auth["account_id"],
        "planType": plan_type,
        "isSelected": is_selected,
        "windows": windows,
    }


def normalize_error(label, message, is_selected=False):
    return {
        "ok": False,
        "label": label,
        "error": message,
        "isSelected": is_selected,
        "windows": [],
    }


def matching_local_window_count(account, local_windows):
    account_windows = {
        window.get("label"): window
        for window in account.get("windows", [])
        if window.get("label")
    }
    matched = 0

    for local_window in local_windows:
        account_window = account_windows.get(local_window.get("label"))
        if not account_window:
            continue

        local_duration = as_int(local_window.get("windowSeconds"))
        account_duration = as_int(account_window.get("windowSeconds"))
        if local_duration > 0 and account_duration > 0 and local_duration != account_duration:
            return 0

        local_reset = as_int(local_window.get("resetAtEpoch"))
        account_reset = as_int(account_window.get("resetAtEpoch"))
        if local_reset <= 0 or account_reset <= 0:
            continue
        if abs(local_reset - account_reset) > LOCAL_WINDOW_RESET_TOLERANCE_SECONDS:
            return 0
        matched += 1

    return matched


def apply_local_rate_limits(accounts, local_rate_limits):
    windows = local_rate_limit_windows(local_rate_limits)
    if not windows:
        return accounts

    local_plan_type = str(local_rate_limits["rateLimits"].get("plan_type", "")).lower()
    candidates = []
    for account in accounts:
        account_plan_type = str(account.get("planType", "")).lower()
        if local_plan_type and account_plan_type and local_plan_type != account_plan_type:
            continue

        match_count = matching_local_window_count(account, windows)
        if match_count <= 0:
            continue

        score = (match_count, 0 if account.get("carriedForward") else 1)
        candidates.append((score, account))

    if not candidates:
        log_event(
            "ignored local Codex session rate_limits because no account API windows "
            f"matched path={local_rate_limits['path'].name}"
        )
        return accounts

    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    best_score, best_account = candidates[0]
    if len(candidates) > 1 and candidates[1][0] == best_score:
        labels = ",".join(candidate[1].get("label", "") for candidate in candidates if candidate[0] == best_score)
        log_event(
            "ignored local Codex session rate_limits because the account match was ambiguous "
            f"accounts={labels} path={local_rate_limits['path'].name}"
        )
        return accounts

    best_account["windows"] = windows
    best_account["localRateLimits"] = True
    best_account["localRateLimitsPath"] = str(local_rate_limits["path"])
    best_account["localRateLimitsUpdatedAt"] = datetime.fromtimestamp(
        local_rate_limits["eventEpoch"], tz=timezone.utc
    ).isoformat()
    log_event(
        f"account={best_account.get('label', '')} matched local Codex session rate_limits "
        f"windows={len(windows)} path={local_rate_limits['path'].name}"
    )
    return accounts


def plan_sort_rank(account):
    plan_type = str(account.get("planType", "")).lower()
    if plan_type == "free":
        return 0
    if plan_type == "plus":
        return 2
    return 1


def sort_accounts(accounts):
    return sorted(accounts, key=plan_sort_rank)


def write_error(message):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "Codex",
        "ok": False,
        "error": message,
        "accounts": [],
        "bars": [],
    }
    common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
    log_event(f"error: {message}")


def fetch_account(label, path, is_selected):
    try:
        auth = read_auth(label, path)
        status, usage = codex_request(auth)

        if status in (401, 403):
            log_event(f"account={label} usage request returned HTTP {status}; refreshing token")
            refresh_token(auth)
            status, usage = codex_request(auth)

        if status != 200:
            print(json.dumps({label: usage}, indent=2), file=sys.stderr)
            return normalize_error(label, f"Codex usage API error: HTTP {status}", is_selected)

        usage = retry_degenerate_usage(auth, label, usage)
        account = normalize_usage(auth, usage, is_selected)
        log_event(
            f"account={label} completed plan={account['planType'] or 'unknown'} "
            f"windows={len(account['windows'])}"
        )
        return account
    except Exception as error:
        return normalize_error(label, str(error), is_selected)


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()
    configure_from_env()
    auth_files = discover_auth_files()
    previous_accounts = load_previous_accounts()
    local_rate_limits = read_latest_local_rate_limits()
    labels = ",".join(label for label, _, _ in auth_files)
    log_event(f"starting Codex usage fetch accounts={labels or 'none'}")

    try:
        accounts = [fetch_account(label, path, is_selected) for label, path, is_selected in auth_files]
        accounts = [carry_forward_previous_windows(account, previous_accounts) for account in accounts]
        accounts = apply_local_rate_limits(accounts, local_rate_limits)
        accounts = sort_accounts(accounts)
        ok_count = sum(1 for account in accounts if account.get("ok"))
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "Codex",
            "ok": ok_count > 0,
            "accounts": accounts,
            "bars": flatten_bars(accounts),
        }
        common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
        log_event(f"completed fetch accounts={len(accounts)} ok={ok_count} wrote={OUTPUT_PATH.name}")
        print(json.dumps(output, indent=2))
        return 0 if ok_count > 0 else 1
    except Exception as error:
        write_error(f"Codex usage fetch failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

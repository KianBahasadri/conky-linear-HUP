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
CODEX_AUTH_STORE_DIR = Path.home() / ".local" / "share" / "clusterfork-auth" / "codex"
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
FIVE_HOUR_WINDOW_SECONDS = common.FIVE_HOUR_WINDOW_SECONDS
WEEKLY_WINDOW_SECONDS = common.WEEKLY_WINDOW_SECONDS
LONG_WINDOW_THRESHOLD_SECONDS = 24 * 60 * 60
DEGENERATE_RETRIES = 4
LOCAL_RATE_LIMIT_MAX_AGE_SECONDS = 21600
LOCAL_WINDOW_RESET_TOLERANCE_SECONDS = 5
WINDOW_RESET_MATCH_TOLERANCE_SECONDS = 5


log_event = common.make_logger(LOG_PATH, "fetch_codex_usage")
atomic_write_json = common.atomic_write_json
as_float = common.as_float
as_int = common.as_int
parse_iso_epoch = common.parse_iso_epoch
flatten_bars = common.flatten_bars


def configure_from_env():
    global CODEX_HOME
    global CODEX_SQLITE_HOME
    global CODEX_AUTH_STORE_DIR
    global DEGENERATE_RETRIES
    global LOCAL_RATE_LIMIT_MAX_AGE_SECONDS

    CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    CODEX_SQLITE_HOME = Path(os.environ.get("CODEX_SQLITE_HOME", CODEX_HOME)).expanduser()
    codex_auth_store = os.environ.get("CODEX_AUTH_STORE_DIR", "").strip()
    if codex_auth_store:
        CODEX_AUTH_STORE_DIR = Path(codex_auth_store).expanduser()
    elif os.environ.get("CODEX_HOME"):
        # When CODEX_HOME is explicitly overridden, use it as the auth store dir
        # to maintain backward compatibility with the old single-directory layout.
        CODEX_AUTH_STORE_DIR = CODEX_HOME
    else:
        CODEX_AUTH_STORE_DIR = Path.home() / ".local" / "share" / "clusterfork-auth" / "codex"
    DEGENERATE_RETRIES = int(os.environ.get("CODEX_USAGE_DEGENERATE_RETRIES", "4"))
    LOCAL_RATE_LIMIT_MAX_AGE_SECONDS = int(os.environ.get("CODEX_LOCAL_RATE_LIMIT_MAX_AGE_SECONDS", "21600"))


def discover_auth_files():
    configured_path = os.environ.get("CODEX_AUTH_PATH", "").strip()
    if configured_path:
        path = Path(configured_path).expanduser()
        return [(auth_label(path), path, is_selected_auth(path))]

    # Prefer the shared clusterfork-auth store when it has profiles.
    store_dir = CODEX_AUTH_STORE_DIR if CODEX_AUTH_STORE_DIR.is_dir() else None
    search_dir = store_dir if store_dir else DEFAULT_AUTH_PATH.parent
    suffixed_paths = sorted(search_dir.glob("auth.json.*"))
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


def row_has_usage_limit_error(row):
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return False

    error = payload.get("error")
    return isinstance(error, dict) and error.get("codex_error_info") == "usage_limit_exceeded"


def read_local_rate_limit_samples():
    now = int(datetime.now(timezone.utc).timestamp())
    samples = []

    for path in latest_rollout_paths():
        if not path.is_file():
            continue

        latest = None
        try:
            with path.open("r", encoding="utf-8") as rollout:
                for line in rollout:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    event_epoch = parse_iso_epoch(row.get("timestamp"))
                    if not event_epoch:
                        continue

                    payload = row.get("payload") or {}
                    rate_limits = row.get("rate_limits")
                    if not isinstance(rate_limits, dict) and isinstance(payload, dict):
                        rate_limits = payload.get("rate_limits")
                    if isinstance(rate_limits, dict) and local_rate_limits_have_future_window(rate_limits, now):
                        latest = {
                            "eventEpoch": event_epoch,
                            "path": path,
                            "rateLimits": rate_limits,
                            "exhausted": False,
                        }
                    elif latest and event_epoch >= latest["eventEpoch"] and row_has_usage_limit_error(row):
                        # The endpoint can briefly report an old percentage before
                        # Codex rejects the next turn for the same window.
                        latest["eventEpoch"] = event_epoch
                        latest["exhausted"] = True
        except OSError as error:
            log_event(f"could not read Codex rollout for local rate limits path={path}: {error}")

        if latest and now - latest["eventEpoch"] <= LOCAL_RATE_LIMIT_MAX_AGE_SECONDS:
            samples.append(latest)

    return samples


def local_rate_limits_have_future_window(rate_limits, now):
    for key in ("primary", "secondary"):
        window = rate_limits.get(key)
        if isinstance(window, dict) and as_int(window.get("window_minutes")) > 0 and as_int(window.get("resets_at")) > now:
            return True
    return False


def clamped_used_percent(window):
    if not isinstance(window, dict):
        return None
    return max(0.0, min(100.0, as_float(window.get("used_percent"))))


def local_rate_limit_windows(local_rate_limits):
    if not local_rate_limits:
        return []

    rate_limits = local_rate_limits["rateLimits"]
    now = int(datetime.now(timezone.utc).timestamp())
    exhausted = local_rate_limits.get("exhausted", False)
    raw_windows = (("5h", rate_limits.get("primary")), ("weekly", rate_limits.get("secondary")))

    blocking_percent = None
    if exhausted:
        # A rollout never says which window tripped the usage_limit_exceeded
        # error, but the blocker is always the fullest one; the other window's
        # percentage is still accurate and must not be pinned to 100.
        percents = [percent for percent in (clamped_used_percent(window) for _, window in raw_windows) if percent is not None]
        blocking_percent = max(percents) if percents else None

    windows = []
    for label, window in raw_windows:
        forced = blocking_percent is not None and clamped_used_percent(window) == blocking_percent
        normalized = normalize_local_rate_limit_window(label, window, now, exhausted=forced)
        if normalized:
            windows.append(normalized)
    return windows


def normalize_local_rate_limit_window(label, window, now, exhausted=False):
    if not isinstance(window, dict):
        return None

    reset_at = as_int(window.get("resets_at"))
    window_seconds = as_int(window.get("window_minutes")) * 60
    used_percent = max(0.0, min(100.0, as_float(window.get("used_percent"))))
    if exhausted:
        used_percent = 100.0
    if reset_at <= now or window_seconds <= 0:
        return None

    normalized_label = "weekly" if window_seconds > LONG_WINDOW_THRESHOLD_SECONDS else "5h"

    return {
        "label": normalized_label,
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


def is_reserve_limit(item):
    name = str((item or {}).get("limit_name") or "").strip().lower()
    return "reserve" in name


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


def normalize_window(label, window, fetched_at, exhausted=False):
    if not isinstance(window, dict):
        return None

    limit_window_seconds = as_int(window.get("limit_window_seconds"))
    used_percent = max(0.0, min(100.0, as_float(window.get("used_percent"))))
    if exhausted:
        # Only the blocking window is pinned: its numeric percentage can lag
        # the account-level reached/allowed flags by a turn, while every other
        # window's percentage is already accurate.
        used_percent = 100.0
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
    if limit_window_seconds > 0:
        window_seconds = limit_window_seconds
    elif normalized_label == "weekly" or (
        normalized_label == "reserve" and reset_after_seconds > LONG_WINDOW_THRESHOLD_SECONDS
    ):
        window_seconds = WEEKLY_WINDOW_SECONDS
    else:
        window_seconds = FIVE_HOUR_WINDOW_SECONDS

    return {
        "label": normalized_label,
        "usedPercent": round(used_percent, 1),
        "remainingPercent": max(0, round(100 - used_percent, 1)),
        "resetsAt": resets_at_iso,
        "resetAtEpoch": int(reset_at) if reset_at else 0,
        "resetAfterSeconds": max(0, reset_after_seconds),
        "windowSeconds": window_seconds,
    }


def format_usage_windows(windows):
    """Format normalized windows for diagnostics without including credentials."""
    if not windows:
        return "none"

    formatted = []
    for window in windows:
        label = str(window.get("label") or "unknown")
        used_percent = as_float(window.get("usedPercent"))
        remaining_percent = as_float(window.get("remainingPercent"))
        reset_at = str(window.get("resetsAt") or "-")
        reset_after = as_int(window.get("resetAfterSeconds"))
        window_seconds = as_int(window.get("windowSeconds"))
        formatted.append(
            f"{label}(used={used_percent:.1f}%,remaining={remaining_percent:.1f}%,"
            f"reset={reset_at},reset_after={reset_after}s,window={window_seconds}s)"
        )
    return ";".join(formatted)


def local_rate_limit_path_name(account):
    path = account.get("localRateLimitsPath")
    return Path(path).name if path else "-"


def account_value_source(account):
    if account.get("localRateLimits"):
        return "local"
    if account.get("ok"):
        return "api"
    return "error"


def log_final_account(account):
    """Log the exact normalized values that will be written for one account."""
    fields = [
        f"account={account.get('label', '')}",
        "stage=final",
        f"ok={1 if account.get('ok') else 0}",
        f"endpoint_fresh={1 if account.get('endpointFresh') else 0}",
        f"selected={1 if account.get('isSelected') else 0}",
        f"plan={account.get('planType') or 'unknown'}",
        f"source={account_value_source(account)}",
        f"windows={len(account.get('windows') or [])}",
        f"values={format_usage_windows(account.get('windows') or [])}",
    ]
    if account.get("localRateLimits"):
        fields.append(f"local_path={local_rate_limit_path_name(account)}")
        fields.append(f"local_updated={account.get('localRateLimitsUpdatedAt') or '-'}")
    if account.get("error"):
        fields.append(f"error={account['error']}")
    log_event(" ".join(fields))


def account_blocking_reset_at(usage):
    """Reset time of the window actually blocking the account, per the upsell banner."""
    upsell = usage.get("rate_limit_upsell") if isinstance(usage, dict) else None
    if isinstance(upsell, dict):
        reset_at = as_int(upsell.get("reset_at"))
        if reset_at > 0:
            return reset_at
    return None


def window_blocks_account(window, fetched_at, blocking_reset):
    if blocking_reset is None or not isinstance(window, dict):
        return False

    reset_at = as_float(window.get("reset_at"))
    if reset_at <= 0:
        reset_after_seconds = as_int(window.get("reset_after_seconds"))
        if reset_after_seconds <= 0:
            return False
        reset_at = fetched_at.timestamp() + reset_after_seconds
    return abs(reset_at - blocking_reset) <= WINDOW_RESET_MATCH_TOLERANCE_SECONDS


def normalize_usage(auth, usage, is_selected):
    rate_limit = usage.get("rate_limit") or {}
    plan_type = usage.get("plan_type", "")
    fetched_at = datetime.now(timezone.utc)
    windows = []
    labels_seen = set()
    exhausted = rate_limit.get("limit_reached") is True or rate_limit.get("allowed") is False
    blocking_reset = account_blocking_reset_at(usage) if exhausted else None

    fallback_blocking_percent = None
    if exhausted and blocking_reset is None:
        # Responses without the banner never name the blocker either; the
        # fullest window is the one that tripped the account-level flags.
        percents = [
            percent
            for percent in (clamped_used_percent(rate_limit.get(key)) for key in ("primary_window", "secondary_window"))
            if percent is not None
        ]
        fallback_blocking_percent = max(percents) if percents else None

    if is_paid_plan(plan_type) and meaningful_window_count(usage) == 0:
        return {
            "ok": True,
            "endpointFresh": True,
            "label": auth["label"],
            "email": auth["email"],
            "accountId": auth["account_id"],
            "planType": plan_type,
            "isSelected": is_selected,
            "windows": [],
            "error": "Codex usage API returned a degenerate paid-account quota response.",
        }

    for label, key in (("5h", "primary_window"), ("weekly", "secondary_window")):
        window = rate_limit.get(key)
        forced = window_blocks_account(window, fetched_at, blocking_reset) or (
            blocking_reset is None
            and fallback_blocking_percent is not None
            and clamped_used_percent(window) == fallback_blocking_percent
        )
        normalized = normalize_window(label, window, fetched_at, exhausted=forced)
        if not normalized:
            continue
        if normalized["label"] in labels_seen:
            log_event(f"account={auth['label']} skipped duplicate {normalized['label']} window from {key}")
            continue
        labels_seen.add(normalized["label"])
        windows.append(normalized)

    for reserve_window in reserve_usage_windows(usage, fetched_at):
        if reserve_window["label"] in labels_seen:
            continue
        labels_seen.add(reserve_window["label"])
        windows.append(reserve_window)

    return {
        "ok": True,
        "endpointFresh": True,
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
        "endpointFresh": False,
        "label": label,
        "error": message,
        "isSelected": is_selected,
        "windows": [],
    }


def reserve_usage_windows(usage, fetched_at):
    additional = usage.get("additional_rate_limits") if isinstance(usage, dict) else None
    if not isinstance(additional, list):
        return []

    windows = []
    for item in additional:
        if not isinstance(item, dict) or not is_reserve_limit(item):
            continue
        rate_limit = item.get("rate_limit")
        if not isinstance(rate_limit, dict):
            continue
        candidates = []
        for key in ("primary_window", "secondary_window"):
            # Reserve is a fallback pool. Account-level reached/allowed flags
            # pin the main 5h/weekly blocker, not this window.
            normalized = normalize_window("reserve", rate_limit.get(key), fetched_at)
            if normalized:
                candidates.append(normalized)
        if not candidates:
            continue
        weekly = [window for window in candidates if window["windowSeconds"] > LONG_WINDOW_THRESHOLD_SECONDS]
        windows.append(weekly[0] if weekly else candidates[0])
        break
    return windows


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
    if isinstance(local_rate_limits, list):
        samples = local_rate_limits
    elif isinstance(local_rate_limits, dict):
        samples = [local_rate_limits]
    else:
        samples = []

    if not samples:
        return accounts

    applied_epochs = {}
    for local_sample in sorted(samples, key=lambda sample: sample.get("eventEpoch", 0)):
        windows = local_rate_limit_windows(local_sample)
        if not windows:
            continue
        local_values = format_usage_windows(windows)

        local_plan_type = str(local_sample["rateLimits"].get("plan_type", "")).lower()
        candidates = []
        endpoint_accounts = []
        for account in accounts:
            if account.get("endpointFresh"):
                endpoint_accounts.append(account.get("label", ""))
                continue

            account_plan_type = str(account.get("planType", "")).lower()
            if local_plan_type and account_plan_type and local_plan_type != account_plan_type:
                continue

            match_count = matching_local_window_count(account, windows)
            if match_count <= 0:
                continue

            score = (match_count,)
            candidates.append((score, account))

        if not candidates:
            if endpoint_accounts:
                log_event(
                    "discarded local Codex session rate_limits because endpoint data is authoritative "
                    f"accounts={','.join(endpoint_accounts)} path={local_sample['path'].name} "
                    f"values={local_values}"
                )
            else:
                log_event(
                    "ignored local Codex session rate_limits because no account API windows "
                    f"matched path={local_sample['path'].name} values={local_values}"
                )
            continue

        candidates.sort(key=lambda candidate: candidate[0], reverse=True)
        best_score, best_account = candidates[0]
        if len(candidates) > 1 and candidates[1][0] == best_score:
            labels = ",".join(candidate[1].get("label", "") for candidate in candidates if candidate[0] == best_score)
            log_event(
                "ignored local Codex session rate_limits because the account match was ambiguous "
                f"accounts={labels} path={local_sample['path'].name} values={local_values}"
            )
            continue

        account_label = best_account.get("label", "")
        if local_sample.get("eventEpoch", 0) < applied_epochs.get(account_label, -1):
            log_event(
                f"account={account_label} ignored older local Codex session rate_limits "
                f"event={local_sample.get('eventEpoch', 0)} "
                f"newer_event={applied_epochs[account_label]} "
                f"path={local_sample['path'].name} values={local_values}"
            )
            continue

        previous_values = format_usage_windows(best_account.get("windows") or [])
        previous_reserve = [
            window
            for window in best_account.get("windows") or []
            if window.get("label") == "reserve"
        ]
        best_account["windows"] = windows
        if previous_reserve and not any(window.get("label") == "reserve" for window in windows):
            best_account["windows"] = list(windows) + previous_reserve
        best_account["localRateLimits"] = True
        best_account["localRateLimitsPath"] = str(local_sample["path"])
        best_account["localRateLimitsUpdatedAt"] = datetime.fromtimestamp(
            local_sample["eventEpoch"], tz=timezone.utc
        ).isoformat()
        applied_epochs[account_label] = local_sample.get("eventEpoch", 0)
        local_event = best_account["localRateLimitsUpdatedAt"]
        log_event(
            f"account={account_label} matched local Codex session rate_limits "
            f"windows={len(windows)} event={local_event} path={local_sample['path'].name} "
            f"previous_values={previous_values} local_values={local_values} "
            f"final_values={format_usage_windows(best_account['windows'])}"
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
            f"windows={len(account['windows'])} source=api "
            f"values={format_usage_windows(account['windows'])}"
        )
        return account
    except Exception as error:
        return normalize_error(label, str(error), is_selected)


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()
    configure_from_env()
    auth_files = discover_auth_files()
    local_rate_limits = read_local_rate_limit_samples()
    labels = ",".join(label for label, _, _ in auth_files)
    log_event(f"starting Codex usage fetch accounts={labels or 'none'}")

    try:
        accounts = [fetch_account(label, path, is_selected) for label, path, is_selected in auth_files]
        accounts = apply_local_rate_limits(accounts, local_rate_limits)
        accounts = sort_accounts(accounts)
        for account in accounts:
            log_final_account(account)
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

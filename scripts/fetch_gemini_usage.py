#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "gemini-usage.json"
RENDER_PATH = CACHE_DIR / "gemini-usage-render.tsv"
LOG_PATH = CACHE_DIR / "conky-rate-limit-panel.log"
DEFAULT_STATE_DIR = Path.home() / ".gemini" / "antigravity-cli" / "rotate-auth"
DEFAULT_ENDPOINT = "https://daily-cloudcode-pa.googleapis.com"
DEFAULT_AUTH_REFRESH_TIMEOUT_SECONDS = 30
API_VERSION = "v1internal"
DAY_SECONDS = 24 * 60 * 60
WEEK_SECONDS = 7 * DAY_SECONDS
PROFILE_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


log_event = common.make_logger(LOG_PATH, "fetch_gemini_usage")
as_float = common.as_float
flatten_bars = common.flatten_bars


class GeminiAuthError(RuntimeError):
    pass


def state_dir():
    configured = os.environ.get("GEMINI_ANTIGRAVITY_STATE_DIR", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_STATE_DIR


def endpoint():
    return os.environ.get("GEMINI_CODE_ASSIST_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/")


def auth_refresh_timeout_seconds():
    configured = os.environ.get("GEMINI_AUTH_REFRESH_TIMEOUT_SECONDS", "")
    return max(1, common.as_int(configured, DEFAULT_AUTH_REFRESH_TIMEOUT_SECONDS))


def read_profiles(path):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    return sorted({line.strip() for line in lines if PROFILE_PATTERN.fullmatch(line.strip())})


def read_current(path):
    try:
        value = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    return value if PROFILE_PATTERN.fullmatch(value) else ""


def discover_profiles():
    directory = state_dir()
    profiles = read_profiles(directory / "profiles")
    current = read_current(directory / "current")
    if profiles:
        return [(profile, profile == current) for profile in profiles]
    return [(os.environ.get("GEMINI_USAGE_LABEL", "").strip() or "default", True)]


def lookup_keyring_secret(service, username):
    if not shutil.which("secret-tool"):
        raise RuntimeError("secret-tool is required for Gemini Antigravity credentials")
    result = subprocess.run(
        ["secret-tool", "lookup", "service", service, "username", username],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0 or not result.stdout:
        detail = result.stderr.strip()
        suffix = f": {detail}" if detail else ""
        raise RuntimeError(f"missing keyring item service={service} username={username}{suffix}")
    return result.stdout


def read_auth(label, is_selected):
    service = "gemini" if is_selected else "rotate-antigravity"
    username = "antigravity" if is_selected else label
    try:
        raw = json.loads(lookup_keyring_secret(service, username))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"invalid Antigravity keyring JSON for {label}: {error}") from error

    token = raw.get("token")
    if not isinstance(token, dict) or not token.get("access_token"):
        raise RuntimeError(f"Antigravity keyring item for {label} has no token.access_token")
    return {
        "label": label,
        "access_token": token["access_token"],
        "expiry": token.get("expiry", ""),
        "auth_method": raw.get("auth_method", ""),
    }


def refresh_selected_auth(label):
    current = read_current(state_dir() / "current")
    if current and current != label:
        raise RuntimeError(f"selected Gemini profile changed from {label} to {current}")

    configured = os.environ.get("GEMINI_ANTIGRAVITY_CLI", "").strip()
    executable = str(Path(configured).expanduser()) if configured else shutil.which("agy")
    if not executable:
        raise RuntimeError("agy is required to refresh the selected Gemini credentials")

    timeout = auth_refresh_timeout_seconds()
    log_event(f"account={label} refreshing Gemini credentials through agy")
    try:
        result = subprocess.run(
            [executable, "models"],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"agy credential refresh timed out after {timeout}s") from error
    except OSError as error:
        raise RuntimeError(f"agy credential refresh failed: {error}") from error

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        suffix = f": {detail[-500:]}" if detail else ""
        raise RuntimeError(f"agy credential refresh failed with exit code {result.returncode}{suffix}")
    log_event(f"account={label} refreshed Gemini credentials through agy")


def request_json(access_token, method, body):
    request = urllib.request.Request(
        f"{endpoint()}/{API_VERSION}:{method}",
        data=json.dumps(body).encode("utf-8"),
        method="POST",
    )
    request.add_header("Authorization", f"Bearer {access_token}")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", "antigravity-cli")

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body_text = error.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError:
            payload = {"error": body_text[:500]}
        return error.code, payload
    except urllib.error.URLError as error:
        raise RuntimeError(f"Gemini {method} request failed: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Gemini {method} response was not JSON: {error}") from error


def load_code_assist(auth):
    status, payload = request_json(
        auth["access_token"],
        "loadCodeAssist",
        {
            "metadata": {
                "ideType": "IDE_UNSPECIFIED",
                "platform": "LINUX_AMD64",
                "pluginType": "GEMINI",
            }
        },
    )
    if status in (401, 403):
        raise GeminiAuthError(f"Gemini loadCodeAssist API error: HTTP {status}")
    if status != 200:
        raise RuntimeError(f"Gemini loadCodeAssist API error: HTTP {status}")
    project = payload.get("cloudaicompanionProject", "")
    if not project:
        raise RuntimeError("Gemini loadCodeAssist returned no cloudaicompanionProject")
    return project, payload


def fetch_quota(auth, project):
    status, payload = request_json(auth["access_token"], "retrieveUserQuota", {"project": project})
    if status in (401, 403):
        raise GeminiAuthError(f"Gemini retrieveUserQuota API error: HTTP {status}")
    if status != 200:
        raise RuntimeError(f"Gemini retrieveUserQuota API error: HTTP {status}")
    return payload


def classify_model(model_id):
    model_id = str(model_id or "").lower()
    if "pro" in model_id or "flash" in model_id:
        return "gemini"
    return "other"


def quota_window_seconds(reset_after_seconds):
    if reset_after_seconds > 2 * DAY_SECONDS:
        return WEEK_SECONDS
    return DAY_SECONDS


def normalize_windows(payload, fetched_at=None):
    fetched_at = fetched_at or datetime.now(timezone.utc)
    now = int(fetched_at.timestamp())
    groups = {}

    for bucket in payload.get("buckets", []) if isinstance(payload, dict) else []:
        if not isinstance(bucket, dict):
            continue
        token_type = str(bucket.get("tokenType", "")).upper()
        if token_type and token_type not in {"REQUESTS", "WTUS"}:
            continue
        model_id = str(bucket.get("modelId", "")).strip()
        if not model_id:
            continue
        reset_at = common.parse_iso_epoch(bucket.get("resetTime"))
        remaining_fraction = max(0.0, min(1.0, as_float(bucket.get("remainingFraction"))))
        if reset_at <= now:
            continue

        label = classify_model(model_id)
        group = groups.setdefault(
            label,
            {
                "remaining": [],
                "resets": [],
                "models": [],
            },
        )
        group["remaining"].append(remaining_fraction)
        group["resets"].append(reset_at)
        group["models"].append(model_id)

    order = {"gemini": 0, "other": 1}
    windows = []
    for label, group in sorted(groups.items(), key=lambda item: (order.get(item[0], 2), item[0]))[:2]:
        remaining_fraction = sum(group["remaining"]) / len(group["remaining"])
        reset_at = min(group["resets"])
        reset_after_seconds = max(0, reset_at - now)
        used_percent = round((1 - remaining_fraction) * 100, 1)
        windows.append(
            {
                "label": label,
                "usedPercent": used_percent,
                "remainingPercent": max(0, round(100 - used_percent, 1)),
                "resetsAt": datetime.fromtimestamp(reset_at, tz=timezone.utc).isoformat(),
                "resetAtEpoch": reset_at,
                "resetAfterSeconds": reset_after_seconds,
                "windowSeconds": quota_window_seconds(reset_after_seconds),
                "models": sorted(set(group["models"])),
            }
        )
    return windows


def plan_type(load_payload):
    tier = load_payload.get("currentTier") if isinstance(load_payload, dict) else {}
    tier = tier if isinstance(tier, dict) else {}
    tier_id = str(tier.get("id", "")).lower()
    tier_name = str(tier.get("name", ""))
    if "free" in tier_id or "free" in tier_name.lower():
        return "free"
    if load_payload.get("paidTier") or "pro" in tier_id or "pro" in tier_name.lower():
        return "pro"
    return tier_name or tier_id


def safe_cache_label(label):
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("._")
    return safe or "default"


def account_cache_path(label):
    return CACHE_DIR / f"gemini-usage-cache-{safe_cache_label(label)}.json"


def read_account_cache(label):
    try:
        return json.loads(account_cache_path(label).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_account_cache(account):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.atomic_write_json(account_cache_path(account["label"]), account)


def normalize_error(label, message, is_selected=False):
    return {
        "ok": False,
        "label": label,
        "error": message,
        "isSelected": is_selected,
        "windows": [],
    }


def fetch_fresh_account(label, is_selected):
    auth = read_auth(label, is_selected)
    project, load_payload = load_code_assist(auth)
    quota_payload = fetch_quota(auth, project)
    windows = normalize_windows(quota_payload)
    if not windows:
        raise RuntimeError("Gemini quota API returned no active request buckets")
    account = {
        "ok": True,
        "label": label,
        "planType": plan_type(load_payload),
        "isSelected": is_selected,
        "windows": windows,
    }
    write_account_cache(account)
    log_event(
        f"account={label} completed plan={account['planType'] or 'unknown'} "
        f"windows={len(windows)} selected={is_selected}"
    )
    return account


def fetch_account(label, is_selected):
    try:
        try:
            return fetch_fresh_account(label, is_selected)
        except GeminiAuthError:
            if not is_selected:
                raise
            refresh_selected_auth(label)
            return fetch_fresh_account(label, is_selected)
    except Exception as error:
        cached = read_account_cache(label)
        if isinstance(cached, dict) and cached.get("windows"):
            cached["isSelected"] = is_selected
            cached["staleCache"] = True
            cached["error"] = f"using stale cache after {error}"
            log_event(f"account={label} using stale Gemini cache after error: {error}")
            return cached
        return normalize_error(label, str(error), is_selected)


def write_error(message):
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "provider": "Gemini",
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
    profiles = discover_profiles()
    labels = ",".join(label for label, _ in profiles)
    log_event(f"starting Gemini usage fetch accounts={labels or 'none'}")

    try:
        accounts = [fetch_account(label, is_selected) for label, is_selected in profiles]
        ok_count = sum(1 for account in accounts if account.get("ok"))
        errors = [account.get("error", "") for account in accounts if not account.get("ok")]
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "Gemini",
            "ok": ok_count > 0,
            "error": "; ".join(error for error in errors if error),
            "accounts": accounts,
            "bars": flatten_bars(accounts),
        }
        common.write_usage_outputs(OUTPUT_PATH, RENDER_PATH, output)
        log_event(f"completed fetch accounts={len(accounts)} ok={ok_count} wrote={OUTPUT_PATH.name}")
        print(json.dumps(output, indent=2))
        return 0 if ok_count > 0 else 1
    except Exception as error:
        write_error(f"Gemini usage fetch failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

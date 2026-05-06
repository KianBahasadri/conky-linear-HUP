#!/usr/bin/env python3
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
OUTPUT_PATH = CACHE_DIR / "codex-usage.json"
LOG_PATH = CACHE_DIR / "conky-linear.log"
DEFAULT_AUTH_PATH = Path.home() / ".codex" / "auth.json"
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


def log_event(message):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(f"[{timestamp}] fetch_codex_usage: {message}\n")


def atomic_write_text(path, content):
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    os.replace(tmp_path, path)


def atomic_write_json(path, data):
    atomic_write_text(path, json.dumps(data, indent=2))


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
            "User-Agent": "conky-codex-usage",
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
    auth["path"].write_text(json.dumps(auth["raw"], indent=2), encoding="utf-8")
    os.chmod(auth["path"], 0o600)


def normalize_window(label, window):
    if not isinstance(window, dict):
        return None

    used_percent = float(window.get("used_percent") or 0)
    reset_at = window.get("reset_at") or 0
    reset_after_seconds = window.get("reset_after_seconds") or 0
    resets_at_iso = None

    if reset_at:
        resets_at_iso = datetime.fromtimestamp(float(reset_at), tz=timezone.utc).isoformat()

    return {
        "label": label,
        "usedPercent": round(used_percent, 1),
        "remainingPercent": max(0, round(100 - used_percent, 1)),
        "resetsAt": resets_at_iso,
        "resetAfterSeconds": int(reset_after_seconds or 0),
    }


def normalize_usage(auth, usage, is_selected):
    rate_limit = usage.get("rate_limit") or {}
    windows = []

    for label, key in (("5h", "primary_window"), ("weekly", "secondary_window")):
        normalized = normalize_window(label, rate_limit.get(key))
        if normalized and (normalized["usedPercent"] > 0 or normalized["resetsAt"]):
            windows.append(normalized)

    return {
        "ok": True,
        "label": auth["label"],
        "email": auth["email"],
        "accountId": auth["account_id"],
        "planType": usage.get("plan_type", ""),
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


def flatten_bars(accounts):
    bars = []
    for account in accounts:
        for window in account.get("windows", []):
            bars.append(
                {
                    "account": account.get("label", ""),
                    "planType": account.get("planType", ""),
                    "isSelected": account.get("isSelected", False),
                    "window": window.get("label", ""),
                    "usedPercent": window.get("usedPercent", 0),
                    "remainingPercent": window.get("remainingPercent", 0),
                    "resetsAt": window.get("resetsAt"),
                    "resetAfterSeconds": window.get("resetAfterSeconds", 0),
                    "ok": account.get("ok", False),
                }
            )
    return bars


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
    atomic_write_json(OUTPUT_PATH, output)
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
    auth_files = discover_auth_files()
    labels = ",".join(label for label, _, _ in auth_files)
    log_event(f"starting Codex usage fetch accounts={labels or 'none'}")

    try:
        accounts = [fetch_account(label, path, is_selected) for label, path, is_selected in auth_files]
        ok_count = sum(1 for account in accounts if account.get("ok"))
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "Codex",
            "ok": ok_count > 0,
            "accounts": accounts,
            "bars": flatten_bars(accounts),
        }
        atomic_write_json(OUTPUT_PATH, output)
        log_event(f"completed fetch accounts={len(accounts)} ok={ok_count} wrote={OUTPUT_PATH.name}")
        print(json.dumps(output, indent=2))
        return 0 if ok_count > 0 else 1
    except Exception as error:
        write_error(f"Codex usage fetch failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

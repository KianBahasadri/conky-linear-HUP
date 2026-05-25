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
RENDER_PATH = CACHE_DIR / "codex-usage-render.tsv"
LOG_PATH = CACHE_DIR / "conky-codex.log"
DEFAULT_AUTH_PATH = Path.home() / ".codex" / "auth.json"
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
TOKEN_URL = "https://auth.openai.com/oauth/token"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
FIVE_HOUR_WINDOW_SECONDS = 5 * 60 * 60
WEEKLY_WINDOW_SECONDS = 7 * 24 * 60 * 60
LONG_WINDOW_THRESHOLD_SECONDS = 24 * 60 * 60


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


def escape_tsv(value):
    return str(value).replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def render_tsv(output):
    lines = [
        "\t".join(
            [
                "meta",
                "ok",
                "1" if output.get("ok") else "0",
                "updatedAt",
                escape_tsv(output.get("updatedAt", "")),
                "error",
                escape_tsv(output.get("error", "")),
            ]
        )
    ]

    for account in output.get("accounts", []):
        lines.append(
            "\t".join(
                [
                    "account",
                    escape_tsv(account.get("label", "")),
                    escape_tsv(account.get("planType", "")),
                    "1" if account.get("isSelected") else "0",
                    "1" if account.get("ok") else "0",
                    escape_tsv(account.get("error", "")),
                ]
            )
        )

    for bar in output.get("bars", []):
        lines.append(
            "\t".join(
                [
                    "bar",
                    escape_tsv(bar.get("account", "")),
                    escape_tsv(bar.get("planType", "")),
                    "1" if bar.get("isSelected") else "0",
                    escape_tsv(bar.get("window", "")),
                    str(bar.get("usedPercent", 0)),
                    str(bar.get("remainingPercent", 0)),
                    escape_tsv(bar.get("resetsAt") or ""),
                    str(bar.get("resetAtEpoch", 0)),
                    str(bar.get("resetAfterSeconds", 0)),
                    str(bar.get("windowSeconds", 0)),
                ]
            )
        )

    return "\n".join(lines) + "\n"


def write_outputs(output):
    atomic_write_json(OUTPUT_PATH, output)
    atomic_write_text(RENDER_PATH, render_tsv(output))


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
    atomic_write_json(auth["path"], auth["raw"])
    os.chmod(auth["path"], 0o600)


def as_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_window(label, window, fetched_at):
    if not isinstance(window, dict):
        return None

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

    normalized_label = label
    if label == "5h" and reset_after_seconds > LONG_WINDOW_THRESHOLD_SECONDS:
        normalized_label = "weekly"
    window_seconds = WEEKLY_WINDOW_SECONDS if normalized_label == "weekly" else FIVE_HOUR_WINDOW_SECONDS

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

    for label, key in (("5h", "primary_window"), ("weekly", "secondary_window")):
        normalized = normalize_window(label, rate_limit.get(key), fetched_at)
        if not normalized or not (normalized["usedPercent"] > 0 or normalized["resetsAt"]):
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


def plan_sort_rank(account):
    plan_type = str(account.get("planType", "")).lower()
    if plan_type == "free":
        return 0
    if plan_type == "plus":
        return 2
    return 1


def sort_accounts(accounts):
    return sorted(accounts, key=plan_sort_rank)


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
                    "resetAtEpoch": window.get("resetAtEpoch", 0),
                    "resetAfterSeconds": window.get("resetAfterSeconds", 0),
                    "windowSeconds": window.get("windowSeconds", 0),
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
    write_outputs(output)
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
        accounts = sort_accounts(accounts)
        ok_count = sum(1 for account in accounts if account.get("ok"))
        output = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "provider": "Codex",
            "ok": ok_count > 0,
            "accounts": accounts,
            "bars": flatten_bars(accounts),
        }
        write_outputs(output)
        log_event(f"completed fetch accounts={len(accounts)} ok={ok_count} wrote={OUTPUT_PATH.name}")
        print(json.dumps(output, indent=2))
        return 0 if ok_count > 0 else 1
    except Exception as error:
        write_error(f"Codex usage fetch failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

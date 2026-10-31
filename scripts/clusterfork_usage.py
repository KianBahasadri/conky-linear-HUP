"""Read Clusterfork's v1 consumer contract without handling managed credentials."""

import copy
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


MAX_AGE_SECONDS = 300
ACCOUNT_ID = re.compile(r"[0-9a-f]{64}")
PROFILE = re.compile(r"[A-Za-z0-9._-]+")


def read_snapshot(provider, store):
    """The installed CLI joins offline ownership with authenticated controller GET.

    Never retry using auth files, refresh tokens, or credential-transfer commands.
    Do not surface subprocess output on failure: only the contract is public.
    """
    install = Path.home() / ".config" / "clusterfork"
    script = Path(os.environ.get(
        "CLUSTERFORK_ACCOUNTS_SCRIPT", install / "automation" / "accounts.py"
    )).expanduser()
    venv_python = script.parent / "venv" / "bin" / "python"
    python = os.environ.get("CLUSTERFORK_PYTHON") or (
        str(venv_python) if venv_python.is_file() else sys.executable
    )
    try:
        result = subprocess.run(
            [python, str(script), "snapshot", "--provider", provider, "--store", str(store)],
            capture_output=True, text=True, timeout=45, check=False,
        )
        if result.returncode:
            raise RuntimeError("Clusterfork account snapshot unavailable")
        snapshot = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise RuntimeError("Clusterfork account snapshot unavailable") from error
    return snapshot


def read_cached_accounts(path, provider):
    try:
        output = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(output, dict) or not isinstance(output.get("accounts"), list):
            return {}
        return {
            row["accountId"]: row for row in output["accounts"]
            if isinstance(row, dict) and row.get("provider") == provider
            and ACCOUNT_ID.fullmatch(str(row.get("accountId", "")))
        }
    except (OSError, ValueError, TypeError, KeyError):
        return {}


def group_accounts(snapshot, provider):
    if (not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1
            or snapshot.get("provider") != provider
            or snapshot.get("local_scope") != "host"
            or not isinstance(snapshot.get("accounts"), list)):
        raise ValueError("Unsupported Clusterfork account snapshot")
    groups = {}
    for row in snapshot["accounts"]:
        if (not isinstance(row, dict) or row.get("provider") != provider
                or not ACCOUNT_ID.fullmatch(str(row.get("account_id", "")))):
            raise ValueError("Invalid Clusterfork account identity")
        groups.setdefault(row["account_id"], []).append(row)
    return groups


def names(rows, key):
    return sorted({name for row in rows if isinstance(row.get(key), list) for name in row[key]
                   if isinstance(name, str) and name}, key=lambda name: (name.lower(), name))


def normalize_cloud_usage(usage, provider, now):
    """Keep capture/attempt times and source names; unknown is never 0% used."""
    usage = usage if isinstance(usage, dict) else {}
    observed = common.as_float(usage.get("observed_at")) or None
    max_age = min(MAX_AGE_SECONDS, max(1, common.as_int(usage.get("max_age_seconds"), MAX_AGE_SECONDS)))
    windows = {}
    source_windows = usage.get("windows")
    invalid = not isinstance(source_windows, list)
    for window in source_windows if isinstance(source_windows, list) else []:
        if not isinstance(window, dict):
            invalid = True
            continue
        name = window.get("name")
        used = common.as_float(window.get("used_percent"), None)
        if not isinstance(name, str) or not name.startswith((provider + "/", "gpt-" if provider == "codex" else "cursor/")):
            invalid = True
            continue
        if used is None or not 0 <= used <= 100:
            invalid = True
            continue
        duration = max(0, common.as_int(window.get("duration_minutes")) * 60)
        reset = max(0, common.as_int(window.get("resets_at")))
        if provider == "cursor":
            label = name.removeprefix("cursor/")
        elif "reserve" in name.lower():
            label = "reserve"
        elif duration >= 20 * 86400:
            label = "monthly"
        elif duration > 86400 or name.endswith("/secondary"):
            label = "weekly"
        else:
            label = "5h"
        try:
            resets_at = datetime.fromtimestamp(reset, timezone.utc).isoformat() if reset else None
        except (ValueError, OverflowError, OSError):
            invalid = True
            continue
        windows[name] = {
            "label": label, "sourceName": name,
            "usedPercent": used, "remainingPercent": 100 - used,
            "resetAtEpoch": reset, "resetsAt": resets_at,
            "resetAfterSeconds": max(0, reset - int(observed or now)),
            "windowSeconds": duration,
        }
    freshness = "unknown"
    if windows and observed and usage.get("freshness") != "unknown":
        freshness = "fresh" if (
            not invalid and usage.get("freshness") == "fresh" and 0 <= now - observed <= max_age
            and all(not w["resetAtEpoch"] or w["resetAtEpoch"] > now for w in windows.values())
        ) else "stale"
    if freshness == "unknown":
        windows = {}
    return {
        "observedAt": observed, "attemptedAt": usage.get("attempted_at"),
        "ageSeconds": now - observed if observed else None,
        "maxAgeSeconds": max_age, "freshness": freshness,
        "sourceFreshness": usage.get("freshness", "unknown"),
        "sourceAgeSeconds": usage.get("age_seconds"),
        "normalizationError": "invalid usage windows" if invalid and source_windows else None,
        "sourceError": usage.get("error"), "windows": list(windows.values()),
    }


def retain_cached_usage(account, cached, now):
    if not cached or not cached.get("observedAt") or not cached.get("windows"):
        return
    for key in ("windows", "observedAt", "maxAgeSeconds"):
        if key in cached:
            account[key] = copy.deepcopy(cached[key])
    account.update(ageSeconds=now - account["observedAt"], freshness="stale", staleCache=True)


def fetch_accounts(provider, store, cache_path, fetch_local, *, now=None):
    previous = read_cached_accounts(cache_path, provider)
    try:
        snapshot = read_snapshot(provider, store)
        groups = group_accounts(snapshot, provider)
        source_error = snapshot.get("cloud_error")
    except (RuntimeError, ValueError, TypeError):
        snapshot, groups, source_error = {}, {}, "Clusterfork account snapshot unavailable"
    # The CLI generates host availability during the subprocess call.
    now = time.time() if now is None else now

    # During source failure keep controller-only accounts, too. Availability is
    # never copied from cache, even when its quota measurement is retained.
    if source_error:
        for identity, cached in previous.items():
            groups.setdefault(identity, [{
                "account_id": identity, "aliases": cached.get("aliases", []),
                "cloud_available": cached.get("usageSource") == "cloud",
            }])
    generated = common.as_float(snapshot.get("generated_at"))
    availability_fresh = 0 < generated <= now and now - generated <= MAX_AGE_SECONDS
    accounts = []
    for identity, rows in groups.items():
        cached = previous.get(identity)
        aliases = names(rows, "aliases")
        local_rows = [row for row in rows if row.get("local_available") is True] if availability_fresh else []
        profiles = [name for name in names(local_rows, "local_profiles") if PROFILE.fullmatch(name) and name != "lock"]
        selected = next((row.get("selected_local_profile") for row in local_rows
                         if row.get("selected_local_profile") in profiles), None)
        # Keep a label stable across selection changes without using it as identity.
        old_label = cached.get("label") if cached else None
        label = old_label if old_label in aliases else (aliases[0] if aliases else identity[:12])
        cloud = any(row.get("cloud_available") is True for row in rows)
        account = {
            "provider": provider, "accountId": identity, "aliases": aliases,
            "label": label, "planType": "", "localAvailable": bool(profiles),
            "localProfiles": profiles, "selectedLocalProfile": selected,
            "isSelected": selected is not None, "availabilityGeneratedAt": generated,
            "usageSource": "cloud" if cloud else "local", "windows": [],
            "cloudAvailable": cloud,
            "cloudState": next((row.get("cloud_state") for row in rows if row.get("cloud_state")), None),
            "ok": False, "staleCache": False,
        }
        if cloud:
            candidates = [row.get("usage") for row in rows if isinstance(row.get("usage"), dict)]
            usage = max(candidates, key=lambda u: common.as_float(u.get("observed_at")), default={})
            account.update(normalize_cloud_usage(usage, provider, now))
            account["error"] = account["sourceError"] or source_error or account["normalizationError"] or (
                "" if account["freshness"] == "fresh" else account["freshness"] + " usage"
            )
            account["ok"] = account["freshness"] == "fresh" and not source_error
            account["staleCache"] = not account["ok"]
            if not account["windows"]:
                retain_cached_usage(account, cached, now)
        elif not source_error and profiles and all(row.get("cloud_available") is False for row in rows):
            # Only explicitly unenrolled, eligible local profiles may use the
            # legacy provider path. A separate login on a managed account still
            # consumes the cloud snapshot, so its quota is counted just once.
            result = fetch_local(label, Path(store) / ("auth.json." + (selected or profiles[0])), selected is not None)
            for key in ("ok", "windows", "planType", "error"):
                if key in result:
                    account[key] = result[key]
            account.update(observedAt=now if account["ok"] else None, maxAgeSeconds=MAX_AGE_SECONDS,
                           freshness="fresh" if account["ok"] else "unknown")
            if not account["ok"]:
                retain_cached_usage(account, cached, now)
        else:
            account.update(error=source_error or "Unknown local availability", freshness="unknown")
            retain_cached_usage(account, cached, now)
        accounts.append(account)
    return sorted(accounts, key=lambda a: (a["label"].lower(), a["accountId"])), source_error

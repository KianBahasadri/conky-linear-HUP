"""Discover and poll local profiles for the Codex and Cursor rate-limit panel."""

import base64
import hashlib
import json
import time


MAX_AGE_SECONDS = 300


def resolved_file(path):
    try:
        target = path.resolve(strict=True)
        return target if target.is_file() else None
    except (OSError, RuntimeError):
        return None


def discover_auth_profiles(store, default_path, configured_path):
    directory = store if store.is_dir() else default_path.parent
    active = resolved_file(directory / "current") or resolved_file(default_path)
    paths = [configured_path] if configured_path else sorted(
        path for path in directory.glob("auth.json.*")
        if not path.name.endswith(".lock") and path.is_file()
    )
    return [(path, active is not None and resolved_file(path) == active)
            for path in paths or [default_path]]


def jwt_claims(token):
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return claims if isinstance(claims, dict) else {}
    except (ValueError, IndexError):
        return {}


def read_cached_accounts(path):
    try:
        output = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rows = output.get("accounts") if isinstance(output, dict) else None
    if not isinstance(rows, list):
        return {}
    return {
        row["accountId"]: row for row in rows
        if isinstance(row, dict) and isinstance(row.get("accountId"), str)
    }


def retain_cached_usage(account, cached):
    windows = cached.get("windows")
    observed_at = cached.get("observedAt")
    if (not isinstance(observed_at, (int, float)) or observed_at <= 0
            or not isinstance(windows, list) or not windows
            or not all(isinstance(window, dict) for window in windows)):
        return
    for key in ("windows", "observedAt", "planType", "usageSource", "rateLimitResetsAvailable"):
        if key in cached:
            account[key] = cached[key]
    account.update(freshness="stale", staleCache=True)


def fetch_accounts(provider, profiles, cache_path, read_auth, fetch_account):
    previous = read_cached_accounts(cache_path)
    discovered_at = int(time.time())
    groups = {}
    for label, path, selected in profiles:
        auth = None
        error = ""
        try:
            # Pin the credential file before reading it so a refresh writes to
            # the same profile even if the selector switches during the poll.
            auth = read_auth(label, path.resolve())
        except (OSError, RuntimeError, ValueError) as exc:
            error = str(exc)
        subject = auth.get("account_id") if auth else None
        # Keep the same identity as the old cache and usage history.
        account_id = (hashlib.sha256(subject.encode()).hexdigest()
                      if isinstance(subject, str) and subject else f"profile:{label}")
        groups.setdefault(account_id, []).append((label, selected, auth, error))

    accounts = []
    for account_id, group in groups.items():
        aliases = sorted((profile[0] for profile in group), key=str.lower)
        cached = previous.get(account_id, {})
        old_label = cached.get("label")
        label = old_label if old_label in aliases else aliases[0]
        profile, selected, auth, error = next((item for item in group if item[1]), group[0])
        result = {"ok": False, "error": error}
        if auth is not None:
            auth["label"] = label
            result = fetch_account(auth, selected)
        observed_at = int(time.time()) if result["ok"] else None
        account = {
            "provider": provider, "accountId": account_id, "aliases": aliases,
            "label": label, "isSelected": selected and auth is not None,
            "localAvailable": auth is not None, "cloudAvailable": False,
            "localProfiles": aliases if auth is not None else [],
            "selectedLocalProfile": profile if selected and auth is not None else None,
            "availabilityGeneratedAt": discovered_at,
            "ok": result["ok"], "error": result.get("error", ""),
            "windows": result.get("windows", []), "planType": result.get("planType", ""),
            "usageSource": "local", "observedAt": observed_at,
            "maxAgeSeconds": MAX_AGE_SECONDS, "freshness": "fresh" if result["ok"] else "unknown",
            "staleCache": False,
        }
        if "rateLimitResetsAvailable" in result:
            account["rateLimitResetsAvailable"] = result["rateLimitResetsAvailable"]
        if not account["ok"] and not account_id.startswith("profile:"):
            retain_cached_usage(account, cached)
        accounts.append(account)

    return sorted(accounts, key=lambda account: account["label"].lower())

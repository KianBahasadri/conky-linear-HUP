"""Failure-isolated, cached weight and hourly weather context for workouts."""
import bisect
import calendar
import json
import math
import sqlite3
import statistics
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import fetch_common as common
import fetch_weight
from exercise_progression import DAY, epoch, finite

VERSION = 1
VARIABLES = ("temperature_2m", "relative_humidity_2m", "dew_point_2m", "wind_speed_10m", "shortwave_radiation")
UNITS = ("°C", "%", "°C", "km/h", "W/m²")
FIELDS = ("temperatureC", "humidityPercent", "dewPointC", "windKmh", "solarWm2")
MODEL = "ecmwf_ifs"
ENDPOINT = "https://archive-api.open-meteo.com/v1/archive"


def read_cache(path):
    try:
        value = json.loads(Path(path).read_text())
        if value.get("version") != VERSION or not isinstance(value.get("tiles"), dict):
            return {"version": VERSION, "tiles": {}}
        for key, tile in list(value["tiles"].items()):
            if not isinstance(tile, dict):
                value["tiles"].pop(key)
                continue
            if "hourly" in tile:
                try:
                    _validate_hourly({"hourly": tile["hourly"], "hourly_units": dict(zip(("time",) + VARIABLES, ("unixtime",) + UNITS))})
                except (ValueError, TypeError, KeyError):
                    value["tiles"].pop(key)
        return value
    except (OSError, ValueError, TypeError, AttributeError):
        return {"version": VERSION, "tiles": {}}


def weight_context(readings, start, stale=False):
    prior = [r for r in readings if epoch(r.get("timestamp")) is not None and epoch(r["timestamp"]) <= start]
    if not prior:
        return {"available": False, "reason": "No preceding weigh-in"}
    prior.sort(key=lambda r: epoch(r["timestamp"]))
    factors = {"KG": 1.0, "LB": 0.45359237, "ST": 6.35029318}
    last = prior[-1]
    factor = factors.get(last.get("unit"))
    if factor is None or finite(last.get("value")) is None or last["value"] <= 0:
        return {"available": False, "reason": "Invalid weight units or value"}
    age = (start - epoch(last["timestamp"])) / DAY
    recent = [r["value"] * factor for r in prior if start - epoch(r["timestamp"]) <= 7 * DAY
              and r.get("unit") == last["unit"] and finite(r.get("value")) is not None and r["value"] > 0]
    return {"available": age <= 7 and not stale, "value": round(last["value"], 2), "unit": last["unit"].lower(),
            "valueKg": round(last["value"] * factor, 3), "medianKg": round(statistics.median(recent), 3) if recent else None,
            "ageDays": round(age, 3), "measuredAt": last["timestamp"].isoformat(), "sampleCount": len(recent),
            "stale": stale, "reason": "Weight upload unreadable" if stale else "Weigh-in older than 7 days" if age > 7 else None}


def _tile_key(workout):
    location = workout.get("location") or {}
    latitude, longitude = finite(location.get("latitude")), finite(location.get("longitude"))
    start = epoch(workout.get("startTime"))
    if latitude is None or longitude is None or start is None or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    date = datetime.fromtimestamp(start, timezone.utc)
    return f"{latitude:.2f},{longitude:.2f},{date.year:04d}-{date.month:02d}"


def _validate_hourly(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("hourly"), dict):
        raise ValueError("Weather response missing hourly data")
    hourly, units = payload["hourly"], payload.get("hourly_units", {})
    times = hourly.get("time")
    if not isinstance(times, list) or len(times) < 2 or any(finite(t) is None for t in times):
        raise ValueError("Invalid weather timestamps")
    if any(b - a != 3600 for a, b in zip(times, times[1:])):
        raise ValueError("Weather timestamps must be continuous UTC hours")
    if any(t % 3600 != 0 for t in times):
        raise ValueError("Weather timestamps must align to UTC hours")
    if units.get("time") != "unixtime":
        raise ValueError("Weather timestamps must use UTC epoch seconds")
    for key, unit in zip(VARIABLES, UNITS):
        if units.get(key) != unit or not isinstance(hourly.get(key), list) or len(hourly[key]) != len(times):
            raise ValueError("Missing weather values or wrong units: " + key)
        if any(value is not None and (type(value) not in (int, float) or finite(value) is None) for value in hourly[key]):
            raise ValueError("Invalid numeric weather value: " + key)
    return {key: hourly[key] for key in ("time",) + VARIABLES}


def _request(params):
    request = urllib.request.Request(ENDPOINT + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "conky-workout-context/1"})
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("Weather response exceeds size limit")
    return json.loads(raw)


def _parameters(key, now):
    latitude, longitude, month = key.split(",")
    year, number = map(int, month.split("-"))
    last = datetime(year, number, calendar.monthrange(year, number)[1], tzinfo=timezone.utc).date()
    today = datetime.fromtimestamp(now, timezone.utc).date()
    # Include the following midnight for interpolation and cross-month workouts.
    from datetime import timedelta
    return {"latitude": latitude, "longitude": longitude, "start_date": month + "-01",
            "end_date": min(last + timedelta(days=1), today).isoformat(), "timezone": "UTC",
            "timeformat": "unixtime", "models": MODEL, "hourly": ",".join(VARIABLES)}


def _interpolate(hourly, key, stamp):
    times = hourly["time"]
    if not times[0] <= stamp <= times[-1]:
        return None
    index = min(bisect.bisect_right(times, stamp) - 1, len(times) - 2)
    a, b = finite(hourly[key][index]), finite(hourly[key][index + 1])
    if a is None or b is None:
        return None
    return a + (b - a) * (stamp - times[index]) / (times[index + 1] - times[index])


def weather_context(workout, tile):
    if not tile or not isinstance(tile.get("hourly"), dict):
        return {"available": False, "reason": "Weather pending"}
    start, end = epoch(workout.get("startTime")), epoch(workout.get("endTime"))
    hourly = tile["hourly"]
    try:
        if start is None or end is None or end <= start:
            raise ValueError("Invalid workout interval")
        knots = [start] + [t for t in hourly["time"] if start < t < end] + [end]
        values = {}
        for key, field in zip(VARIABLES, FIELDS):
            readings = [_interpolate(hourly, key, t) for t in knots]
            if any(value is None for value in readings):
                raise ValueError("Weather has missing hours")
            integral = sum((b - a) * (x + y) / 2 for a, b, x, y in zip(knots, knots[1:], readings, readings[1:]))
            values[field] = round(integral / (end - start), 2)
        if not (-90 <= values["temperatureC"] <= 65 and 0 <= values["humidityPercent"] <= 100
                and -100 <= values["dewPointC"] <= 65 and 0 <= values["windKmh"] <= 250 and 0 <= values["solarWm2"] <= 1600):
            raise ValueError("Weather values outside supported range")
        return {"available": True, **values, "estimated": True, "model": MODEL,
                "retrievedAt": tile.get("retrievedAt"), "stale": False}
    except (ValueError, TypeError, KeyError, IndexError, ZeroDivisionError):
        return {"available": False, "reason": "Incomplete weather context"}


def enrich(workouts, workouts_dir, cache_path, now, *, weight_dir=None, user_id=None, weather_enabled=True, max_requests=3, request=None):
    """Context failures never discard a workout; retries and requests are bounded."""
    cache = read_cache(cache_path)
    stamp = epoch(now)
    issues = []
    readings, stale = [], False
    weight_dir = Path(weight_dir) if weight_dir else Path(workouts_dir) / "weight"
    try:
        backups = sorted(weight_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime_ns, reverse=True)
        if not backups:
            raise ValueError("No weight backup")
        readings = fetch_weight.read_backup(backups[0], user_id)
        cache["weights"] = [{**r, "timestamp": r["timestamp"].isoformat()} for r in readings]
        cache["weightUser"] = user_id
    except (OSError, ValueError, zipfile.BadZipFile, sqlite3.Error, RuntimeError) as error:
        # Backup parsing can fail with ZIP or SQLite errors during an upload.
        issues.append("Weight: " + type(error).__name__)
        if cache.get("weightUser") == user_id:
            for row in cache.get("weights", []):
                try:
                    readings.append({**row, "timestamp": datetime.fromisoformat(row["timestamp"])})
                except (ValueError, KeyError, TypeError):
                    continue
        stale = True
    keyed = {}
    for workout in workouts:
        start = epoch(workout.get("startTime"))
        end = epoch(workout.get("endTime"))
        key = _tile_key(workout)
        if key and start is not None and end is not None and end <= stamp:
            keyed.setdefault(key, []).append(workout)
    pending = []
    for key, group in keyed.items():
        tile = cache["tiles"].get(key)
        if all(weather_context(w, tile).get("available") for w in group):
            continue
        if (tile or {}).get("retryAfter", 0) <= stamp:
            pending.append((max(epoch(w["startTime"]) for w in group), key))
    requested = 0
    allowed = weather_enabled and cache.get("weatherRetryAfter", 0) <= stamp
    for _, key in sorted(pending, reverse=True)[:max_requests if allowed else 0]:
        old = cache["tiles"].get(key, {})
        try:
            params = _parameters(key, stamp)
            hourly = _validate_hourly((request or _request)(params))
            cache["tiles"][key] = {"hourly": hourly, "retrievedAt": now.isoformat(), "model": MODEL, "retryAfter": stamp + 6 * 3600}
        except (OSError, ValueError, TypeError, TimeoutError) as error:
            code = getattr(error, "code", None)
            cache["tiles"][key] = {**old, "retryAfter": stamp + 3600, "error": str(error)[:200], "httpStatus": code}
            issues.append("Weather: " + type(error).__name__)
            if code in (429, 503):
                retry_header = error.headers.get("Retry-After") if getattr(error, "headers", None) else None
                retry = finite(retry_header)
                if retry is None and retry_header:
                    try:
                        retry = parsedate_to_datetime(retry_header).timestamp() - stamp
                    except (ValueError, TypeError, OverflowError):
                        pass
                retry = retry if retry is not None else 3600
                cache["weatherRetryAfter"] = stamp + max(3600, retry)
                requested += 1
                break
        requested += 1
    enriched = []
    pending_workouts = 0
    for workout in workouts:
        start = epoch(workout.get("startTime"))
        weather = weather_context(workout, cache["tiles"].get(_tile_key(workout))) if weather_enabled else {"available": False, "reason": "Weather disabled"}
        if not weather["available"] and _tile_key(workout) and epoch(workout.get("endTime")) is not None and epoch(workout["endTime"]) <= stamp:
            pending_workouts += 1
        context = {"weight": weight_context(readings, start, stale) if start is not None else {"available": False, "reason": "Workout time missing"}, "weather": weather}
        enriched.append({**workout, "context": context})
    common.atomic_write_json(cache_path, cache)
    return enriched, {"weatherPending": pending_workouts,
                      "weatherCovered": sum(w["context"]["weather"]["available"] for w in enriched),
                      "weightCovered": sum(w["context"]["weight"]["available"] for w in enriched),
                      "requests": requested, "issues": issues}

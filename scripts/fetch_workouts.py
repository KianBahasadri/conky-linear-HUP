#!/usr/bin/env python3
"""Summarize phone-uploaded TCX workouts into the panel cache.

Reads the workouts directory fed by the rclone WebDAV service (see
docs/workout-data-source.md) and writes cache/workouts-status.json for the
weather and running overlay's training section.
"""
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
STATUS_PATH = CACHE_DIR / "workouts-status.json"
LOG_PATH = CACHE_DIR / "conky-workouts.log"
DEFAULT_WORKOUTS_DIR = CACHE_DIR / "workouts"

RECENT_LIMIT = 14
WEEK_WINDOW = timedelta(days=7)

SPORT_SHORT_NAMES = {
    "running": "Run",
    "cycling": "Ride",
    "swimming": "Swim",
    "walking": "Walk",
    "hiking": "Hike",
    "elliptical": "Elliptical",
}

log_event = common.make_logger(LOG_PATH, "fetch_workouts")
atomic_write_json = common.atomic_write_json


def local_tag(element):
    return element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""


def units():
    units_name = os.environ.get("WORKOUTS_UNITS", "metric").strip().lower()
    if units_name not in {"metric", "imperial"}:
        raise ValueError("WORKOUTS_UNITS must be metric or imperial")
    return {
        "name": units_name,
        "distanceDivisor": 1000.0 if units_name == "metric" else 1609.344,
        "distanceSymbol": "km" if units_name == "metric" else "mi",
        "paceSymbol": "/km" if units_name == "metric" else "/mi",
    }


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_workout(path):
    """Parse one TCX file into a summary dict, raising on unusable content."""
    duration = 0.0
    distance = 0.0
    calories = 0
    heart_rates = []
    cadences = []
    start_time = None
    end_time = None
    sport = ""
    activity_count = 0

    context = ET.iterparse(str(path), events=("start", "end"))
    for event, element in context:
        tag = local_tag(element)
        if event == "start":
            if tag == "Activity":
                activity_count += 1
                sport = sport or str(element.get("Sport") or "")
            elif tag == "Trackpoint":
                for child in element:
                    child_tag = local_tag(child)
                    if child_tag == "Time":
                        stamp = parse_time(child.text)
                        if stamp:
                            start_time = start_time or stamp
                            end_time = stamp if not end_time or stamp > end_time else end_time
                    elif child_tag == "HeartRateBpm":
                        for sub_child in child:
                            if local_tag(sub_child) == "Value":
                                rate = common.as_int(sub_child.text, 0)
                                if rate > 0:
                                    heart_rates.append(rate)
                    elif child_tag == "Extensions":
                        for ext in child.iter():
                            if local_tag(ext) == "RunCadence":
                                cadence = common.as_int(ext.text, 0)
                                if cadence > 0:
                                    cadences.append(cadence)
                element.clear()
        elif tag == "Lap":
            for child in element:
                child_tag = local_tag(child)
                if child_tag == "TotalTimeSeconds":
                    duration += common.as_float(child.text)
                elif child_tag == "DistanceMeters":
                    distance += common.as_float(child.text)
                elif child_tag == "Calories":
                    calories += common.as_int(child.text, 0)
            element.clear()

    if not activity_count:
        raise ValueError("no Activity element")

    if duration <= 0 and start_time and end_time:
        duration = max(0.0, (end_time - start_time).total_seconds())
    if distance <= 0:
        distance = 0.0

    return {
        "file": path.name,
        "sport": sport or "Workout",
        "startTime": start_time,
        "endTime": end_time,
        "durationSeconds": duration,
        "distanceMeters": distance,
        "calories": calories,
        "avgHeartRate": round(sum(heart_rates) / len(heart_rates)) if heart_rates else None,
        "maxHeartRate": max(heart_rates) if heart_rates else None,
        "avgCadence": round(sum(cadences) / len(cadences)) if cadences else None,
    }


def load_workouts(workouts_dir):
    workouts = []
    failures = 0
    for path in sorted(Path(workouts_dir).glob("*.tcx")):
        try:
            workouts.append(parse_workout(path))
        except (ET.ParseError, ValueError, OSError) as error:
            failures += 1
            log_event(f"skipping {path.name}: {error}")
    workouts.sort(key=lambda workout: workout["startTime"] or datetime.min.replace(tzinfo=timezone.utc))
    return workouts, failures


def short_sport(sport):
    return SPORT_SHORT_NAMES.get(sport.strip().lower(), sport)


def format_duration(seconds):
    seconds = int(round(max(0.0, seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_distance(meters, units):
    return f"{meters / units['distanceDivisor']:.1f} {units['distanceSymbol']}"


def format_pace(duration_seconds, distance_meters, units):
    distance_units = distance_meters / units["distanceDivisor"]
    if distance_units < 0.05 or duration_seconds <= 0:
        return "--"
    pace = duration_seconds / distance_units
    minutes = int(pace // 60)
    seconds = int(round(pace % 60))
    if seconds == 60:
        minutes += 1
        seconds = 0
    return f"{minutes}:{seconds:02d} {units['paceSymbol']}"


def format_date_text(stamp, now):
    local_stamp = stamp.astimezone()
    if local_stamp.date() == now.date():
        return "Today"
    if local_stamp.date() == (now - timedelta(days=1)).date():
        return "Yesterday"
    return local_stamp.strftime("%b %-d")


def pace_seconds(duration_seconds, distance_meters, units):
    distance_units = distance_meters / units["distanceDivisor"]
    if distance_units < 0.05:
        return 0.0
    return duration_seconds / distance_units


def build_status(workouts, units, now=None):
    if now is None:
        now = datetime.now().astimezone()
    status = {
        "ok": True,
        "stale": False,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "workoutCount": len(workouts),
        "unitName": units["name"],
    }

    if not workouts:
        status["ok"] = False
        status["error"] = "No workouts uploaded yet"
        return status

    last = workouts[-1]
    last_duration = last["durationSeconds"]
    last_distance = last["distanceMeters"]
    status.update(
        {
            "lastSport": short_sport(last["sport"]),
            "lastDateText": format_date_text(last["startTime"] or now, now),
            "lastDistanceText": format_distance(last_distance, units),
            "lastDistanceMeters": round(last_distance, 1),
            "lastDurationText": format_duration(last_duration),
            "lastDurationSeconds": round(last_duration),
            "lastPaceText": format_pace(last_duration, last_distance, units),
            "lastHeartRateText": (
                f"{last['avgHeartRate']} avg · {last['maxHeartRate']} max"
                if last["avgHeartRate"]
                else ""
            ),
            "lastCadenceText": (
                f"{last['avgCadence']} spm avg" if last["avgCadence"] else ""
            ),
        }
    )

    week_start = now - WEEK_WINDOW
    week_workouts = [
        workout
        for workout in workouts
        if workout["startTime"] and workout["startTime"].astimezone() >= week_start
    ]
    week_distance = sum(workout["distanceMeters"] for workout in week_workouts)
    week_duration = sum(workout["durationSeconds"] for workout in week_workouts)
    status.update(
        {
            "weekRuns": len(week_workouts),
            "weekDistanceText": format_distance(week_distance, units),
            "weekDistanceMeters": round(week_distance, 1),
            "weekDurationText": format_duration(week_duration),
            "weekPaceText": format_pace(week_duration, week_distance, units),
        }
    )

    recent = workouts[-RECENT_LIMIT:]
    status["recent"] = [
        {
            "dateText": format_date_text(workout["startTime"] or now, now),
            "sport": short_sport(workout["sport"]),
            "distanceText": format_distance(workout["distanceMeters"], units),
            "distanceUnits": round(
                workout["distanceMeters"] / units["distanceDivisor"], 2
            ),
            "isLast": workout is last,
        }
        for workout in recent
    ]
    return status


def write_error(message):
    atomic_write_json(
        STATUS_PATH,
        {
            "ok": False,
            "stale": False,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "error": message,
        },
    )
    log_event(f"error: {message}")


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()
    try:
        units_config = units()
    except ValueError as error:
        write_error(str(error))
        return 1

    workouts_dir = Path(os.environ.get("WORKOUTS_DIR", "") or DEFAULT_WORKOUTS_DIR)
    if not workouts_dir.is_dir():
        write_error(f"Workouts directory missing: {workouts_dir}")
        return 1

    workouts, failures = load_workouts(workouts_dir)
    if not workouts:
        write_error("No workouts uploaded yet")
        return 1

    status = build_status(workouts, units_config)
    if failures:
        status["skippedFiles"] = failures
    atomic_write_json(STATUS_PATH, status)
    log_event(
        f"summarized workouts={len(workouts)} skipped={failures} "
        f"last={status['lastSport']} {status['lastDistanceText']} {status['lastDateText']} "
        f"week={status['weekDistanceText']}/{status['weekRuns']} runs"
    )
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Summarize phone-uploaded TCX workouts into the panel cache.

Reads the workouts directory fed by the rclone WebDAV service (see
docs/workout-data-source.md) and writes cache/workouts-status.json for the
weather and running overlay's training section. GPS and gait measurements,
matched performance comparisons, and workload/context calculations live in
run_analysis.py, exercise_progression.py, and workout_context.py.
"""
import fcntl
import json
import math
import os
import statistics
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fetch_common as common
import run_analysis
import exercise_progression as progression
import workout_context


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
STATUS_PATH = CACHE_DIR / "workouts-status.json"
ANALYSIS_PATH = CACHE_DIR / "workouts-analysis.json"
LOG_PATH = CACHE_DIR / "conky-workouts.log"
DEFAULT_WORKOUTS_DIR = CACHE_DIR / "workouts"

# Bump when parsing or run_analysis changes what a cached file summary means.
ANALYSIS_VERSION = 9
RECENT_LIMIT = 14
WEEK_WINDOW = timedelta(days=7)
TREND_WINDOW_DAYS = 28
NON_RUN_SPORTS = progression.NON_RUN_SPORTS
OTHER_SPORT_RUN_SECONDS = 300
TRACK_COVERAGE = 0.9

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
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp if stamp.tzinfo is not None else None
    except ValueError:
        return None


def parse_workout(path):
    """Parse one TCX file into a summary dict and its track, raising on unusable content.

    An upload cut off mid-file keeps the lap totals and trackpoints read before
    the break and is marked `truncated`.
    """
    duration = 0.0
    distance = 0.0
    calories = 0
    heart_rates = []
    hr_samples = []
    cadences = []
    track = []
    positions = []
    start_time = None
    end_time = None
    sport = ""
    activity_count = 0
    lap = None
    parents = []
    truncated = False
    notes = ""

    def add_lap(fields):
        nonlocal duration, distance, calories
        seconds = progression.finite(fields["TotalTimeSeconds"]) if fields.get("TotalTimeSeconds") is not None else 0.0
        meters = progression.finite(fields["DistanceMeters"]) if fields.get("DistanceMeters") is not None else 0.0
        if seconds is None or meters is None or seconds < 0 or meters < 0:
            raise ValueError("Invalid workout totals")
        duration += seconds
        distance += meters
        calories += common.as_int(fields.get("Calories"), 0)

    try:
        for event, element in ET.iterparse(str(path), events=("start", "end")):
            tag = local_tag(element)
            if event == "start":
                if tag == "Activity":
                    activity_count += 1
                    sport = sport or str(element.get("Sport") or "")
                elif tag == "Lap":
                    lap = {}
                parents.append(tag)
                continue
            parents.pop()
            if tag == "Notes":
                notes = element.text or ""
            if lap is not None and parents and parents[-1] == "Lap":
                if tag in ("TotalTimeSeconds", "DistanceMeters", "Calories"):
                    lap[tag] = element.text
            if tag == "Trackpoint":
                stamp = meters = steps = latitude = longitude = rate = None
                for child in element:
                    child_tag = local_tag(child)
                    if child_tag == "Time":
                        stamp = parse_time(child.text)
                    elif child_tag == "DistanceMeters":
                        meters = progression.finite(child.text)
                    elif child_tag == "Position":
                        for coordinate in child:
                            if local_tag(coordinate) == "LatitudeDegrees":
                                latitude = common.as_float(coordinate.text, None)
                            elif local_tag(coordinate) == "LongitudeDegrees":
                                longitude = common.as_float(coordinate.text, None)
                    elif child_tag == "HeartRateBpm":
                        for sub_child in child:
                            if local_tag(sub_child) == "Value":
                                rate = common.as_int(sub_child.text, 0)
                                if 30 <= rate <= 240:
                                    heart_rates.append(rate)
                    elif child_tag == "Extensions":
                        for ext in child.iter():
                            if local_tag(ext) == "RunCadence":
                                steps = common.as_int(ext.text, 0)
                                if steps > 0:
                                    cadences.append(steps)
                if stamp:
                    start_time = start_time or stamp
                    end_time = stamp if not end_time or stamp > end_time else end_time
                    track.append((stamp.timestamp(), meters, steps))
                    if rate is not None:
                        hr_samples.append((stamp.timestamp(), rate))
                    if latitude is not None and longitude is not None:
                        positions.append((stamp.timestamp(), latitude, longitude))
                element.clear()
            elif tag == "Lap":
                add_lap(lap)
                lap = None
                element.clear()
    except ET.ParseError:
        if not activity_count or (lap is None and not track and duration <= 0):
            raise
        truncated = True
        if lap is not None:
            add_lap(lap)

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
        "truncated": truncated,
        "notes": notes.strip(),
        "track": track,
        "positions": positions,
        "hrSamples": hr_samples,
    }


def hr_settings():
    resting = progression.finite(os.environ.get("WORKOUTS_RESTING_HR", "50"))
    maximum = progression.finite(os.environ.get("WORKOUTS_MAX_HR", "195"))
    if resting is None or maximum is None or not 20 <= resting < maximum <= 240:
        raise ValueError("WORKOUTS_RESTING_HR and WORKOUTS_MAX_HR must satisfy 20 <= resting < maximum <= 240")
    return {"restingHR": resting, "maximumHR": maximum}


def analyze_file(path):
    workout = parse_workout(path)
    track = workout.pop("track")
    positions = workout.pop("positions")
    hr_samples = workout.pop("hrSamples")
    notes = progression.parse_notes(workout.get("notes"))
    workout["trainingNotes"] = notes
    if workout["sport"].strip().lower() not in NON_RUN_SPORTS:
        workout.update(run_analysis.analyze_track(track))
    valid_positions = [(stamp, latitude, longitude) for stamp, latitude, longitude in positions
                       if all(math.isfinite(v) for v in (stamp, latitude, longitude))
                       and -90 <= latitude <= 90 and -180 <= longitude <= 180]
    if valid_positions:
        workout["location"] = {"latitude": statistics.median(p[1] for p in valid_positions),
                               "longitude": statistics.median(p[2] for p in valid_positions)}
    geometry = None
    if not workout["truncated"] and workout.get("trackMeters", 0.0) >= TRACK_COVERAGE * workout["distanceMeters"]:
        geometry = run_analysis.circuit_geometry(positions)
    workout.update(progression.repetition_summary(notes, geometry["laps"] if geometry else None))
    if geometry and not workout["lapCountConflict"]:
        workout["circuit"] = geometry
    settings = hr_settings()
    workout["hrLoad"] = progression.heart_rate_load(hr_samples, workout["durationSeconds"], settings["restingHR"], settings["maximumHR"])
    continuous = workout.get("continuousRun")
    if continuous:
        points = [p for p in valid_positions if continuous["startEpoch"] <= p[0] <= continuous["endEpoch"]]
        if points:
            latitudes, longitudes = [p[1] for p in points], [p[2] for p in points]
            latitude = statistics.median(latitudes)
            continuous.update(latitude=latitude, longitude=statistics.median(longitudes), lapMeters=continuous["meters"],
                              widthMeters=(max(longitudes) - min(longitudes)) * 111320 * math.cos(math.radians(latitude)),
                              heightMeters=(max(latitudes) - min(latitudes)) * 111320)
        selected = sorted({stamp: rate for stamp, rate in hr_samples
                           if continuous["endEpoch"] - 300 <= stamp <= continuous["endEpoch"] and 30 <= rate <= 240}.items())
        intervals = [(b[0] - a[0], (a[1] + b[1]) / 2) for a, b in zip(selected, selected[1:]) if 0 < b[0] - a[0] <= 10]
        covered = sum(dt for dt, _ in intervals)
        continuous["hrCoverage"] = min(1, covered / 300)
        continuous["steadyHR"] = round(sum(dt * rate for dt, rate in intervals) / covered, 2) if covered >= 270 else None
    return workout


def encode_workout(workout):
    return {
        key: value.isoformat() if isinstance(value, datetime) else value
        for key, value in workout.items()
    }


def decode_workout(entry):
    workout = dict(entry)
    for key in ("startTime", "endTime"):
        workout[key] = parse_time(workout.get(key))
    return workout


def read_analysis(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("version") != ANALYSIS_VERSION or data.get("hrSettings") != hr_settings():
        return {}
    files = data.get("files")
    return files if isinstance(files, dict) else {}


def load_workouts(workouts_dir, analysis_path=None):
    """Analyze every TCX file, reusing `analysis_path` entries whose size and mtime match."""
    previous = read_analysis(analysis_path) if analysis_path else {}
    entries = {}
    workouts = []
    failures = 0
    for path in sorted(Path(workouts_dir).glob("*.tcx")):
        try:
            stat = path.stat()
        except OSError as error:
            failures += 1
            log_event(f"skipping {path.name}: {error}")
            continue
        key = [stat.st_size, stat.st_mtime_ns]
        entry = previous.get(path.name)
        if not isinstance(entry, dict) or entry.get("key") != key:
            try:
                entry = {"key": key, "workout": encode_workout(analyze_file(path))}
                if entry["workout"]["truncated"]:
                    log_event(f"salvaged truncated {path.name}")
            except (ET.ParseError, ValueError, OSError) as error:
                log_event(f"skipping {path.name}: {error}")
                entry = {"key": key, "error": str(error), **({"workout": entry["workout"], "stale": True} if isinstance(entry, dict) and isinstance(entry.get("workout"), dict) else {})}
        entries[path.name] = entry
        if isinstance(entry.get("workout"), dict):
            workout = decode_workout(entry["workout"])
            workout["sourceMtimeNs"] = stat.st_mtime_ns
            if entry.get("stale"):
                workout["analysisStale"] = True
                failures += 1
            workouts.append(workout)
        else:
            failures += 1
    if analysis_path and entries != previous:
        atomic_write_json(analysis_path, {"version": ANALYSIS_VERSION, "hrSettings": hr_settings(), "files": entries})
    workouts.sort(key=lambda workout: workout["startTime"] or datetime.min.replace(tzinfo=timezone.utc))
    return workouts, failures


def is_run(workout):
    """Running workouts, plus untyped ones (such as Other) with sustained running in them."""
    sport = workout["sport"].strip().lower()
    if sport == "running":
        return True
    if sport in NON_RUN_SPORTS:
        return False
    return (workout.get("runSeconds") or 0) >= OTHER_SPORT_RUN_SECONDS


def short_sport(sport):
    return SPORT_SHORT_NAMES.get(sport.strip().lower(), sport)


def format_duration(seconds):
    seconds = int(round(max(0.0, seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_signed_duration(seconds):
    seconds = int(round(seconds))
    sign = "−" if seconds < 0 else "+" if seconds > 0 else ""
    minutes, secs = divmod(abs(seconds), 60)
    return f"{sign}{minutes}:{secs:02d}"


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


def known_run_meters(workout):
    """Running meters, or None when the track misses part of the workout (a truncated upload)."""
    run_meters = workout.get("runMeters")
    if run_meters is None or workout.get("trackMeters", 0.0) < TRACK_COVERAGE * workout["distanceMeters"]:
        return None
    return run_meters


def build_status(workouts, units, now=None):
    if now is None:
        now = datetime.now().astimezone()
    observed_count = len(workouts)
    workouts = progression.usable_workouts(workouts, now.timestamp())
    runs = [workout for workout in workouts if is_run(workout)]
    status = {
        "ok": True,
        "stale": False,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "workoutCount": len(workouts),
        "runCount": len(runs),
        "unitName": units["name"],
        "schemaVersion": 3,
        "excludedWorkouts": observed_count - len(workouts),
    }

    if not runs:
        status["ok"] = False
        status["error"] = "No runs uploaded yet" if workouts else "No workouts uploaded yet"
        return status

    last = runs[-1]
    status["stale"] = bool(last.get("analysisStale"))
    if status["stale"]:
        status["error"] = "Workout upload incomplete; showing previous summary"
    last_duration = last["durationSeconds"]
    last_distance = last["distanceMeters"]
    last_stamp = (last["startTime"] or now).astimezone()
    last_age_days = max(0, (now.date() - last_stamp.date()).days)
    run_meters = last.get("runMeters")
    split_known = known_run_meters(last) is not None
    status.update(
        {
            "lastSport": short_sport(last["sport"]),
            "lastDateText": format_date_text(last["startTime"] or now, now),
            "lastAgeDays": last_age_days,
            "lastAgeText": f"{last_age_days}d ago" if last_age_days > 1 else "",
            "lastDistanceText": format_distance(last_distance, units),
            "lastDistanceMeters": round(last_distance, 1),
            "lastDurationText": format_duration(last_duration),
            "lastDurationSeconds": round(last_duration),
            "lastPaceText": format_pace(last_duration, last_distance, units),
            "lastRunDistanceText": format_distance(run_meters, units) if split_known else "",
            "lastWalkDistanceText": format_distance(last["walkMeters"], units) if split_known else "",
            "lastRunPaceText": (
                format_pace(last["runSeconds"], run_meters, units) if run_meters else ""
            ),
            "lastHeartRateText": (
                f"{last['avgHeartRate']} avg · {last['maxHeartRate']} max"
                if last["avgHeartRate"]
                else ""
            ),
            "lastHeartRateShortText": (
                f"{last['avgHeartRate']} bpm" if last["avgHeartRate"] else ""
            ),
            "lastCadenceText": (
                f"{last['avgCadence']} spm avg" if last["avgCadence"] else ""
            ),
            "lastCadenceShortText": (
                f"{last['avgCadence']} spm" if last["avgCadence"] else ""
            ),
        }
    )

    week_start = now - WEEK_WINDOW
    week_runs = [
        run for run in runs if run["startTime"] and run["startTime"].astimezone() >= week_start
    ]
    week_distance = sum(run["distanceMeters"] for run in week_runs)
    week_duration = sum(run["durationSeconds"] for run in week_runs)
    status.update(
        {
            "weekRuns": len(week_runs),
            "weekDistanceText": format_distance(week_distance, units),
            "weekDistanceMeters": round(week_distance, 1),
            "weekDurationText": format_duration(week_duration),
            "weekPaceText": format_pace(week_duration, week_distance, units),
        }
    )

    month_start = now - timedelta(days=TREND_WINDOW_DAYS)
    month_runs = [
        run for run in runs if run["startTime"] and run["startTime"].astimezone() >= month_start
    ]
    month_distance = sum(run["distanceMeters"] for run in month_runs)
    month_distance_text = format_distance(month_distance, units)
    status.update(
        {
            "monthRuns": len(month_runs),
            "monthDistanceText": month_distance_text,
            "monthSummaryText": (
                f"{month_distance_text} · {len(month_runs)} "
                f"{'run' if len(month_runs) == 1 else 'runs'} / {TREND_WINDOW_DAYS}d"
            ),
        }
    )

    reps = last.get("reps") or {}
    strength_parts = []
    if reps.get("pushups") is not None:
        strength_parts.append(f"{reps['pushups']} push")
    if reps.get("pullups") is not None:
        strength_parts.append(f"{reps['pullups']} pull")
    if reps.get("situps") is not None:
        strength_parts.append(f"{reps['situps']} sit")
    last_strength_text = " · ".join(strength_parts)
    notes = last.get("trainingNotes", progression.parse_notes(last.get("notes")))
    for exercise in notes["unquantified"]:
        last_strength_text += (" · " if last_strength_text else "") + "? " + {"pushups": "push", "pullups": "pull", "situps": "sit"}[exercise]
    if last_strength_text and last.get("repsPerLap"):
        last_strength_text += " /lap"
    status["lastStrengthText"] = last_strength_text
    status["lastLapCount"] = last.get("laps")
    status["lastLapCountSource"] = last.get("lapCountSource", "unknown")
    summary = progression.summarize(workouts, now.timestamp(), subject=last)
    status.update(summary)
    # Performance is anchored to the displayed run, even when a different
    # sport was uploaded more recently. Workload still includes all sports.
    assessment = status["performance"]["circuit" if notes["isCircuit"] else "running"]
    status["progressVerdict"] = assessment["text"]
    status["progressKind"] = assessment["kind"] if last_age_days < 10 else "caution"
    status["trendText"] = assessment["text"]
    status["lastContext"] = last.get("context", {})
    status.update(training_display(last, status, units))

    divisor = units["distanceDivisor"]
    status["recent"] = [
        {
            **pace,
            "dateText": format_date_text(run["startTime"] or now, now),
            "sport": short_sport(run["sport"]),
            "distanceText": format_distance(run["distanceMeters"], units),
            "distanceUnits": round(run["distanceMeters"] / divisor, 2),
            "runUnits": (
                round(known_run_meters(run) / divisor, 2) if known_run_meters(run) is not None else None
            ),
            "inWindow": bool(run["startTime"] and run["startTime"].astimezone() >= month_start),
            "isLast": run is last,
        }
        for run, pace in list(zip(runs, progression.pace_series(runs)))[-RECENT_LIMIT:]
    ]
    prior_paces = [progression.recorded_pace(run) for run in month_runs if run is not last
                   and bool(run.get("trainingNotes", progression.parse_notes(run.get("notes")))["isCircuit"]) == notes["isCircuit"]]
    prior_paces = [pace for pace in prior_paces if pace is not None]
    status["paceBaselineSecondsPerKm"] = round(statistics.median(prior_paces), 2) if prior_paces else None
    return status


def training_display(last, status, units):
    """One static summary using the phone's existing fields and notes."""
    circuit = last.get("circuit")
    if circuit:
        headline = f"{last['laps']} laps · {format_duration(circuit['seconds'])}"
        short_headline = f"{last['laps']} laps"
    else:
        headline = status["lastDistanceText"] + " · " + status["lastDurationText"]
        short_headline = status["lastDistanceText"]
    detail = status["lastStrengthText"] or status["lastHeartRateText"] or status["monthSummaryText"]
    short_detail = ("/".join(str((last.get("reps") or {}).get(k, "?")) for k in progression.EXERCISES)
                    + (" /lap" if last.get("repsPerLap") else " reps")) if last.get("reps") else detail
    pace = (("Run " + status["lastRunPaceText"]) if status["lastRunPaceText"] else ("Pace " + status["lastPaceText"])).replace(" /", "/")
    assessment = status["performance"]["running"]
    change = ""
    if assessment["state"] in ("improving", "declining"):
        delta = assessment["change"]
        if assessment["unit"] == "s/km":
            delta *= units["distanceDivisor"] / 1000
            change = format_signed_duration(delta)
        else:
            change = f"{delta:+.0f} bpm"
    return {"trainingHeadline": headline, "trainingShortHeadline": short_headline,
            "trainingDetail": detail, "trainingShortDetail": short_detail, "trainingPace": pace,
            "trainingComparison": change, "trainingKind": assessment["kind"]}


def write_error(message):
    try:
        previous = json.loads(STATUS_PATH.read_text())
    except (OSError, ValueError):
        previous = {}
    if not isinstance(previous, dict):
        previous = {}
    payload = ({**previous, "stale": True, "error": message} if previous.get("ok") else {
            "ok": False,
            "stale": False,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "error": message,
        })
    atomic_write_json(STATUS_PATH, payload)
    log_event(f"error: {message}")


def refresh():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()
    try:
        units_config = units()
        hr_settings()
    except ValueError as error:
        write_error(str(error))
        return 1

    workouts_dir = Path(os.environ.get("WORKOUTS_DIR", "") or DEFAULT_WORKOUTS_DIR)
    if not workouts_dir.is_dir():
        write_error(f"Workouts directory missing: {workouts_dir}")
        return 1

    workouts, failures = load_workouts(workouts_dir, ANALYSIS_PATH)
    if not workouts:
        write_error("No workouts uploaded yet")
        return 1

    now = datetime.now(timezone.utc)
    raw_user_id = os.environ.get("WEIGHT_USER_ID", "").strip()
    try:
        user_id = int(raw_user_id) if raw_user_id else None
        workouts, context_status = workout_context.enrich(
            workouts, workouts_dir, CACHE_DIR / "workout-context.json", now,
            weight_dir=os.environ.get("WEIGHT_DIR") or None, user_id=user_id,
            weather_enabled=os.environ.get("WORKOUTS_WEATHER_ENABLED", "1") != "0",
        )
    except (OSError, ValueError) as error:
        context_status = {"issues": [str(error)], "weatherPending": len(workouts)}
    status = build_status(workouts, units_config, now.astimezone())
    status["contextStatus"] = context_status
    if failures:
        status["skippedFiles"] = failures
    if not status["ok"]:
        write_error(status["error"])
        return 1
    atomic_write_json(STATUS_PATH, status)
    log_event(
        f"summarized workouts={len(workouts)} runs={status['runCount']} skipped={failures} "
        f"last={status['lastDistanceText']} {status['lastDateText']} "
        f"run_pace={status['lastRunPaceText'] or '--'} laps={status.get('lastLapCount')} "
        f"performance={status['trendText'] or '--'} "
        f"verdict={status['progressVerdict']}"
    )
    print(json.dumps(status, indent=2))
    return 0


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with (CACHE_DIR / "workouts-fetch.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                print(STATUS_PATH.read_text())
            except OSError:
                pass
            return 0
        return refresh()


if __name__ == "__main__":
    raise SystemExit(main())

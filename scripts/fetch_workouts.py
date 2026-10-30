#!/usr/bin/env python3
"""Summarize phone-uploaded TCX workouts into the panel cache.

Reads the workouts directory fed by the rclone WebDAV service (see
docs/workout-data-source.md) and writes cache/workouts-status.json for the
weather and running overlay's training section. Walk/run splits, effort
scores, and the fitness trend come from run_analysis.py.
"""
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fetch_common as common
import run_analysis


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
STATUS_PATH = CACHE_DIR / "workouts-status.json"
ANALYSIS_PATH = CACHE_DIR / "workouts-analysis.json"
LOG_PATH = CACHE_DIR / "conky-workouts.log"
DEFAULT_WORKOUTS_DIR = CACHE_DIR / "workouts"

# Bump when parsing or run_analysis changes what a cached file summary means.
ANALYSIS_VERSION = 3
RECENT_LIMIT = 14
WEEK_WINDOW = timedelta(days=7)
TREND_WINDOW_DAYS = 28
TREND_MIN_SCORED_RUNS = 3
TREND_CONFIDENCE = 0.8
TREND_MIN_SECONDS = 15
EQUIVALENT_METERS = 5000.0
NON_RUN_SPORTS = {"biking", "cycling", "swimming", "walking", "hiking", "elliptical"}
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
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
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
    cadences = []
    track = []
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
        duration += common.as_float(fields.get("TotalTimeSeconds"))
        distance += common.as_float(fields.get("DistanceMeters"))
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
                stamp = meters = steps = None
                for child in element:
                    child_tag = local_tag(child)
                    if child_tag == "Time":
                        stamp = parse_time(child.text)
                    elif child_tag == "DistanceMeters":
                        meters = common.as_float(child.text, None)
                    elif child_tag == "HeartRateBpm":
                        for sub_child in child:
                            if local_tag(sub_child) == "Value":
                                rate = common.as_int(sub_child.text, 0)
                                if rate > 0:
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
    }


def analyze_file(path):
    workout = parse_workout(path)
    track = workout.pop("track")
    if is_run(workout):
        workout.update(run_analysis.analyze_track(track))
    laps = workout.get("laps", 1)
    workout.update(
        run_analysis.workout_strain(
            workout["durationSeconds"],
            workout.get("avgHeartRate"),
            workout.get("notes"),
            lap_count=laps,
            sport=workout.get("sport", "Running"),
        )
    )
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
    if not isinstance(data, dict) or data.get("version") != ANALYSIS_VERSION:
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
                entry = {"key": key, "error": str(error)}
        entries[path.name] = entry
        if isinstance(entry.get("workout"), dict):
            workouts.append(decode_workout(entry["workout"]))
        else:
            failures += 1
    if analysis_path and entries != previous:
        atomic_write_json(analysis_path, {"version": ANALYSIS_VERSION, "files": entries})
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


def equivalent_text(score):
    return format_duration(run_analysis.equivalent_seconds(score, EQUIVALENT_METERS))


def known_run_meters(workout):
    """Running meters, or None when the track misses part of the workout (a truncated upload)."""
    run_meters = workout.get("runMeters")
    if run_meters is None or workout.get("trackMeters", 0.0) < TRACK_COVERAGE * workout["distanceMeters"]:
        return None
    return run_meters


def trend_status(runs, last_age_days, now):
    """Fitness level per run and the verdict on whether runs are getting better."""
    samples = [
        (run["startTime"].timestamp() if run["startTime"] else now.timestamp() + 1, run.get("score"))
        for run in runs
    ]
    trend = run_analysis.fitness_trend(samples, now.timestamp(), TREND_WINDOW_DAYS)
    scored = sum(1 for _, score in samples if score is not None)
    status = {"progressVerdict": "Steady", "progressKind": "neutral", "trendText": ""}
    if trend:
        now_seconds = run_analysis.equivalent_seconds(trend["now"], EQUIVALENT_METERS)
        then_seconds = run_analysis.equivalent_seconds(trend["then"], EQUIVALENT_METERS)
        status.update(
            {
                "fitnessScore": round(trend["now"], 2),
                "fitnessText": format_duration(now_seconds),
                "fitnessBaselineScore": round(trend["then"], 2),
                "trendWindowDays": TREND_WINDOW_DAYS,
                "trendProbability": round(trend["probability"], 2),
            }
        )
        if scored >= TREND_MIN_SCORED_RUNS:
            delta = int(round(now_seconds - then_seconds))
            status.update({"trendSeconds": delta, "trendText": format_signed_duration(delta)})
            if trend["probability"] >= TREND_CONFIDENCE and delta <= -TREND_MIN_SECONDS:
                status.update(progressVerdict="Better", progressKind="good")
            elif trend["probability"] <= 1 - TREND_CONFIDENCE and delta >= TREND_MIN_SECONDS:
                status.update(progressVerdict="Worse", progressKind="danger")
    if status["progressVerdict"] == "Steady" and last_age_days >= 10:
        status["progressKind"] = "caution"
    return status, (trend["levels"] if trend else [None] * len(runs))


def build_status(workouts, units, now=None):
    if now is None:
        now = datetime.now().astimezone()
    runs = [workout for workout in workouts if is_run(workout)]
    status = {
        "ok": True,
        "stale": False,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "workoutCount": len(workouts),
        "runCount": len(runs),
        "unitName": units["name"],
    }

    if not runs:
        status["ok"] = False
        status["error"] = "No runs uploaded yet" if workouts else "No workouts uploaded yet"
        return status

    last = runs[-1]
    last_duration = last["durationSeconds"]
    last_distance = last["distanceMeters"]
    last_stamp = (last["startTime"] or now).astimezone()
    last_age_days = max(0, (now.date() - last_stamp.date()).days)
    run_meters = last.get("runMeters")
    split_known = known_run_meters(last) is not None
    last_score = last.get("score")
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
            "lastScore": last_score,
            "lastScoreText": equivalent_text(last_score) if last_score is not None else "",
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

    trend, levels = trend_status(runs, last_age_days, now)
    status.update(trend)

    reps = last.get("reps") or {}
    strength_parts = []
    if reps.get("pushups"):
        strength_parts.append(f"{reps['pushups']} push")
    if reps.get("pullups"):
        strength_parts.append(f"{reps['pullups']} pull")
    if reps.get("situps"):
        strength_parts.append(f"{reps['situps']} sit")
    last_strength_text = " · ".join(strength_parts)
    status["lastStrengthText"] = last_strength_text
    status["lastTotalLoad"] = last.get("totalLoad")
    status["lastCardioLoad"] = last.get("cardioLoad")
    status["lastStrengthLoad"] = last.get("strengthLoad")

    load_history = [
        (w["startTime"].timestamp() if w["startTime"] else now.timestamp(), w.get("totalLoad", 0.0))
        for w in workouts
    ]
    capacity = run_analysis.training_capacity(load_history, now.timestamp(), TREND_WINDOW_DAYS)
    if capacity:
        rop = capacity["rateOfProgress"]
        status["rateOfProgress"] = rop
        status["rateOfProgressText"] = f"{int(round(rop)):+d}%"
        status["chronicTrainingLoad"] = capacity["now"]
        status["chronicTrainingBaseline"] = capacity["then"]
        if last_strength_text:
            status["trendText"] = status["rateOfProgressText"]
            if rop >= 10.0:
                status.update(progressVerdict="Better", progressKind="good")
            elif rop <= -5.0:
                status.update(progressVerdict="Worse", progressKind="danger")
            else:
                status.update(progressVerdict="Steady", progressKind="neutral")
            if last_age_days >= 10:
                status["progressKind"] = "caution"

    divisor = units["distanceDivisor"]
    status["recent"] = [
        {
            "dateText": format_date_text(run["startTime"] or now, now),
            "sport": short_sport(run["sport"]),
            "distanceText": format_distance(run["distanceMeters"], units),
            "distanceUnits": round(run["distanceMeters"] / divisor, 2),
            "runUnits": (
                round(known_run_meters(run) / divisor, 2) if known_run_meters(run) is not None else None
            ),
            "score": run.get("score"),
            "fitness": round(level, 2) if level is not None else None,
            "inWindow": bool(run["startTime"] and run["startTime"].astimezone() >= month_start),
            "isLast": run is last,
        }
        for run, level in list(zip(runs, levels))[-RECENT_LIMIT:]
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

    workouts, failures = load_workouts(workouts_dir, ANALYSIS_PATH)
    if not workouts:
        write_error("No workouts uploaded yet")
        return 1

    status = build_status(workouts, units_config)
    if failures:
        status["skippedFiles"] = failures
    atomic_write_json(STATUS_PATH, status)
    if not status["ok"]:
        log_event(f"error: {status['error']}")
        return 1
    log_event(
        f"summarized workouts={len(workouts)} runs={status['runCount']} skipped={failures} "
        f"last={status['lastDistanceText']} {status['lastDateText']} "
        f"run_pace={status['lastRunPaceText'] or '--'} score={status['lastScoreText'] or '--'} "
        f"fitness={status.get('fitnessText', '--')} trend={status['trendText'] or '--'} "
        f"verdict={status['progressVerdict']}"
    )
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

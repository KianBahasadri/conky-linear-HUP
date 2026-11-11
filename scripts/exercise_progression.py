"""Observed performance, separate workload series, and conservative comparisons.

Pure calculations. TCX/weight/weather I/O is owned by the fetcher and
workout_context. No cross-exercise point conversions or weather bonuses.
"""
import itertools
import math
import re
import statistics
from datetime import datetime, timezone

DAY = 86400.0
EXERCISES = ("pushups", "pullups", "situps")
NAMES = {"pushups": r"push[\s-]*ups?", "pullups": r"pull[\s-]*ups?", "situps": r"sit[\s-]*ups?"}
NON_RUN_SPORTS = {"biking", "cycling", "swimming", "walking", "hiking", "elliptical"}


def finite(value, default=None):
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def epoch(value):
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not isinstance(value, datetime) or value.tzinfo is None:
            return None
        return value.timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def parse_notes(notes):
    """Numeric shorthand or named reps; optional explicit semicolon metadata."""
    parts = str(notes or "").strip().lower().split(";")
    text = parts[0].strip()
    result = {"perLap": True, "counts": {}, "unquantified": [], "errors": [],
              "rpe": None, "rir": {}, "variant": "usual", "restSeconds": None,
              "test": None, "lapOverride": None}
    seen = set()
    for part in parts[1:]:
        if not part.strip():
            continue
        match = re.fullmatch(r"\s*([a-z]+)\s*[:=]\s*(.*?)\s*", part)
        if not match:
            result["errors"].append("Invalid note metadata")
            continue
        key, value = match.groups()
        if key in seen:
            result["errors"].append("Repeated " + key)
            continue
        seen.add(key)
        number = finite(value)
        if key == "rpe" and number is not None and 0 <= number <= 10:
            result["rpe"] = number
        elif key == "rest" and number is not None and 0 <= number <= 3600:
            result["restSeconds"] = number
        elif key == "laps" and number is not None and number.is_integer() and 1 <= number <= 1000:
            result["lapOverride"] = int(number)
        elif key == "rir":
            values = [finite(v) for v in value.split("/")]
            if len(values) in (1, 3) and all(v is not None and 0 <= v <= 30 for v in values):
                result["rir"] = dict(zip(EXERCISES, values * 3 if len(values) == 1 else values))
            else:
                result["errors"].append("Invalid rir")
        elif key == "variant" and re.fullmatch(r"[a-z0-9][a-z0-9 _+-]{0,39}", value):
            result["variant"] = re.sub(r"\s+", " ", value)
        elif key == "test" and value in ("run",) + EXERCISES:
            result["test"] = value
        else:
            result["errors"].append("Invalid " + key)

    shorthand = re.fullmatch(r"(\d+)\s+(\d+)\s+(\d+)", text)
    if shorthand:
        result["counts"] = dict(zip(EXERCISES, map(int, shorthand.groups())))
    elif re.fullmatch(r"[-+\d.]+\s+[-+\d.]+\s+[-+\d.]+", text):
        result["errors"].append("Rep shorthand requires three nonnegative integers")
    else:
        for exercise, pattern in NAMES.items():
            if not re.search(r"(?:" + pattern + r")\b", text):
                continue
            matches = list(re.finditer(r"(?<![\d.\-])(\d+)\s*(?:" + pattern + r")\b", text))
            if len(matches) == 1:
                result["counts"][exercise] = int(matches[0][1])
            else:
                result["unquantified"].append(exercise)
                if len(matches) > 1:
                    result["errors"].append("Repeated " + exercise)
    if re.search(r"\btotal\b", text) or result["test"] in EXERCISES:
        result["perLap"] = False
    if any(value > 100000 for value in result["counts"].values()):
        result["errors"].append("Rep count exceeds supported range")
        result["counts"] = {}
    result["isCircuit"] = bool(result["counts"] or result["unquantified"])
    return result


def repetition_summary(notes, gps_laps):
    override = notes["lapOverride"]
    conflict = override is not None and gps_laps is not None and override != gps_laps
    laps = None if conflict else (override if override is not None else gps_laps)
    per_lap = notes["isCircuit"] and notes["perLap"] and laps is None
    multiplier = laps if notes["perLap"] and laps is not None else 1
    return {"laps": laps, "lapCountSource": "conflict" if conflict else "notes" if override is not None else "gps" if laps is not None else "unknown",
            "reps": {key: value * multiplier for key, value in notes["counts"].items()},
            "repsPerLap": per_lap, "repsIncomplete": bool(notes["isCircuit"] and (notes["unquantified"] or notes["errors"] or per_lap)),
            "lapCountConflict": conflict}


def heart_rate_load(samples, duration, resting=50.0, maximum=195.0):
    """Time-resolved Banister estimate with explicit coverage and calibration."""
    duration = finite(duration, 0)
    if duration <= 0 or not (20 <= resting < maximum <= 240):
        return {"value": None, "coverage": 0.0, "method": "hr-trimp", "reason": "Invalid HR calibration or duration"}
    points, conflict = {}, False
    for stamp, rate in samples:
        stamp, rate = finite(stamp), finite(rate)
        if stamp is None or rate is None or not 30 <= rate <= 240:
            continue
        if stamp in points and abs(points[stamp] - rate) > 20:
            conflict = True
        points[stamp] = rate
    points = sorted(points.items())
    covered = dose = 0.0
    for before, after in zip(points, points[1:]):
        dt = after[0] - before[0]
        if not 0 < dt <= 10:
            continue
        # Trapezoidal integration of the nonlinear rate, not the mean HR.
        values = []
        for rate in (before[1], after[1]):
            reserve = max(0.0, min(1.0, (rate - resting) / (maximum - resting)))
            values.append(reserve * 0.64 * math.exp(1.92 * reserve))
        dose += dt / 60 * sum(values) / 2
        covered += dt
    coverage = min(1.0, covered / duration)
    timing_valid = covered <= duration * 1.05 + 5
    return {"value": round(dose, 2) if coverage >= 0.9 and not conflict and timing_valid else None,
            "coverage": round(coverage, 4), "method": "hr-trimp", "estimated": True,
            "restingHR": resting, "maximumHR": maximum,
            "reason": "HR timing exceeds duration" if not timing_valid else "Conflicting HR samples" if conflict else "HR coverage below 90%" if coverage < 0.9 else None}


def usable_workouts(workouts, now):
    """Completed, finite, unique sessions; reuploads cannot multiply volume."""
    records, seen = [], {}
    for workout in sorted(workouts, key=lambda w: epoch(w.get("startTime")) or -math.inf):
        start, end = epoch(workout.get("startTime")), epoch(workout.get("endTime"))
        duration, meters = finite(workout.get("durationSeconds")), finite(workout.get("distanceMeters"))
        if start is None or start > now or (end is not None and end > now):
            continue
        if duration is None or duration <= 0 or meters is None or meters < 0:
            continue
        if start + duration > now:
            continue
        if end is not None and end < start:
            continue
        identity = (str(workout.get("sport", "")).lower(), round(start), round(duration), round(meters))
        if identity in seen:
            index = seen[identity]
            def quality(record):
                notes = record.get("trainingNotes", parse_notes(record.get("notes")))
                return (not record.get("analysisStale", False), not record.get("truncated", False),
                        record.get("sourceMtimeNs", 0), notes["rpe"] is not None,
                        finite((record.get("hrLoad") or {}).get("value")) is not None)
            if quality(workout) > quality(records[index]):
                records[index] = workout
            continue
        seen[identity] = len(records)
        records.append(workout)
    return sorted(records, key=lambda record: epoch(record["startTime"]))


def _route_match(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    keys = ("latitude", "longitude", "lapMeters")
    if any(finite(item.get(key)) is None for item in (a, b) for key in keys):
        return False
    left_values, right_values = {k: finite(a[k]) for k in keys}, {k: finite(b[k]) for k in keys}
    offset = math.hypot((left_values["latitude"] - right_values["latitude"]) * 111320,
                        (left_values["longitude"] - right_values["longitude"]) * 111320 * math.cos(math.radians(left_values["latitude"])))
    if offset > 50 or min(left_values["lapMeters"], right_values["lapMeters"]) <= 0 or abs(left_values["lapMeters"] / right_values["lapMeters"] - 1) > 0.05:
        return False
    for key in ("widthMeters", "heightMeters"):
        left, right = finite(a.get(key)), finite(b.get(key))
        if left is None or right is None or abs(left - right) > max(20, 0.1 * max(left, right)):
            return False
    return True


def _context_match(a, b, weather=True):
    wa, wb = a.get("weight", {}), b.get("weight", {})
    if not wa.get("available") or not wb.get("available") or wa.get("stale") or wb.get("stale"):
        return "Recent weight needed"
    ma, mb = finite(wa.get("medianKg")), finite(wb.get("medianKg"))
    if ma is None or mb is None or min(ma, mb) <= 0 or abs(ma / mb - 1) > 0.02:
        return "Different bodyweight"
    if weather:
        xa, xb = a.get("weather", {}), b.get("weather", {})
        if not xa.get("available") or not xb.get("available") or xa.get("stale") or xb.get("stale"):
            return "Weather context needed"
        for key, limit in (("temperatureC", 3), ("dewPointC", 3), ("windKmh", 5), ("solarWm2", 150)):
            va, vb = finite(xa.get(key)), finite(xb.get(key))
            if va is None or vb is None or abs(va - vb) > limit:
                return "Different weather"
    return None


def _comparison(workout, history, category, now):
    neutral = {"state": "baseline", "kind": "neutral", "text": "Building baseline", "matchedCount": 0,
               "change": None, "unit": "seconds" if category == "circuit" else "s/km" if category == "running" else "reps"}
    notes = workout.get("trainingNotes", parse_notes(workout.get("notes")))
    if notes["errors"] or workout.get("analysisStale") or workout.get("truncated"):
        return {**neutral, "reason": "Incomplete workout or notes"}
    if now - epoch(workout["startTime"]) > 10 * DAY:
        return {**neutral, "reason": "Recent workout needed"}
    if category == "circuit":
        observation = workout.get("circuit")
        if not notes["isCircuit"] or not isinstance(observation, dict) or workout.get("repsIncomplete"):
            return {**neutral, "reason": "Complete circuit prescription needed"}
        value, resolution = finite(observation.get("seconds")), finite(observation.get("timingResolutionSeconds"), 40)
    elif category == "running":
        observation = workout.get("continuousRun")
        if notes["isCircuit"] or not isinstance(observation, dict):
            return {**neutral, "reason": "Continuous run needed"}
        use_hr = notes["rpe"] is None
        if use_hr and (observation.get("steadyHR") is None or observation.get("hrCoverage", 0) < 0.9):
            return {**neutral, "reason": "RPE or steady HR needed"}
        value, resolution = finite(observation.get("steadyHR") if use_hr else observation.get("paceSecondsPerKm")), 1.0
        if use_hr:
            neutral["unit"] = "bpm"
    else:
        exercise = notes["test"]
        if exercise not in EXERCISES or exercise not in notes["rir"] or notes["restSeconds"] is None:
            return {**neutral, "reason": "Rep benchmark + RIR needed"}
        observation = notes["counts"].get(exercise)
        if observation is None:
            return {**neutral, "reason": "Rep count needed"}
        value, resolution = observation, 1.0
    if finite(value) is None or value < 0 or (value == 0 and category != "strength") or resolution < 0:
        return {**neutral, "reason": "Invalid performance measurement"}
    if notes["rpe"] is None and category == "circuit":
        return {**neutral, "reason": "Add RPE for comparisons"}
    matches = []
    reasons = []
    latest_start = epoch(workout["startTime"])
    for other in history:
        start = epoch(other["startTime"])
        if other is workout or not latest_start - 84 * DAY <= start < latest_start:
            continue
        if other.get("analysisStale") or other.get("truncated"):
            continue
        if other.get("sport", "").strip().lower() != workout.get("sport", "").strip().lower():
            continue
        n = other.get("trainingNotes", parse_notes(other.get("notes")))
        if n["errors"] or n["variant"] != notes["variant"] or n["restSeconds"] != notes["restSeconds"]:
            continue
        if category != "strength" and not (category == "running" and use_hr) and (n["rpe"] is None or abs(n["rpe"] - notes["rpe"]) > 1):
            continue
        if category == "circuit":
            obs = other.get("circuit")
            if n["counts"] != notes["counts"] or n["perLap"] != notes["perLap"] or other.get("laps") != workout.get("laps") or other.get("repsIncomplete"):
                continue
            if not _route_match(observation, obs):
                continue
            measure = finite(obs.get("seconds"))
        elif category == "running":
            obs = other.get("continuousRun")
            if n["isCircuit"] or not obs or not _route_match(observation, obs):
                continue
            if use_hr:
                if obs.get("steadyHR") is None or obs.get("hrCoverage", 0) < 0.9 or abs(obs["paceSecondsPerKm"] / observation["paceSecondsPerKm"] - 1) > 0.02:
                    continue
                measure = finite(obs["steadyHR"])
            else:
                measure = finite(obs.get("paceSecondsPerKm"))
        else:
            if n["test"] != exercise or exercise not in n["rir"] or abs(n["rir"][exercise] - notes["rir"][exercise]) > 1:
                continue
            measure = n["counts"].get(exercise)
        reason = _context_match(workout.get("context", {}), other.get("context", {}), category != "strength")
        if reason:
            reasons.append(reason)
            continue
        if finite(measure) is not None:
            matches.append((start, measure))
    # One observation per UTC day. Repeated laps and same-day tests are not
    # independent evidence of a longitudinal change.
    by_day = {int(stamp // DAY): (stamp, measure) for stamp, measure in matches}
    by_day.pop(int(latest_start // DAY), None)
    matches = sorted(by_day.values())
    if not matches:
        return {**neutral, "reason": reasons[-1] if reasons else "Same prescription needed"}
    descriptive = value - statistics.median(measure for _, measure in matches[-4:])
    result = {**neutral, "matchedCount": len(matches), "change": round(descriptive, 2),
              "reason": "More matched sessions needed", "method": "matched-session medians"}
    if len(matches) < 7:
        return result
    baseline = [measure for _, measure in matches[-7:-3]]
    recent = [measure for _, measure in matches[-3:]] + [value]
    difference = statistics.median(recent) - statistics.median(baseline)
    pooled = baseline + recent
    observed = abs(difference)
    # An exact rank-sum screen is resistant to outlying magnitudes and handles
    # tied measurements; median effects alone have very low permutation power.
    ranks = [1 + sum(other < value for other in pooled) + (sum(other == value for other in pooled) - 1) / 2 for value in pooled]
    observed_rank = abs(sum(ranks[4:]) - sum(ranks[:4]))
    statistics_ = []
    for indices in itertools.combinations(range(8), 4):
        chosen = set(indices)
        statistic = abs(sum(ranks[i] for i in chosen) - sum(ranks[i] for i in range(8) if i not in chosen))
        statistics_.append(statistic)
    p = sum(statistic >= observed_rank - 1e-9 for statistic in statistics_) / len(statistics_)
    result.update(change=round(difference, 2), pValue=round(p, 4), baselineCount=4, recentCount=4,
                  method="exact two-sided rank-sum permutation with median effect",
                  baselineFromEpoch=matches[-7][0], baselineToEpoch=matches[-4][0],
                  recentFromEpoch=matches[-3][0], recentToEpoch=latest_start,
                  reason="Change within observed variation")
    if p <= 0.05 and observed > resolution:
        better = difference > 0 if category == "strength" else difference < 0
        result.update(state="improving" if better else "declining", kind="good" if better else "danger",
                      text="More reps" if category == "strength" and better else "Fewer reps" if category == "strength" else "Faster" if better else "Slower",
                      reason="Matched performance change")
        if category == "running" and use_hr:
            result["text"] = "Lower HR" if better else "Higher HR"
    else:
        result.update(state="steady", text="Within variation")
    return result


def summarize(workouts, now, subject=None):
    records = usable_workouts(workouts, now)
    performance = {}
    latest = subject if subject is not None else records[-1] if records else None
    for category in ("circuit", "running", "strength"):
        performance[category] = _comparison(latest, records, category, now) if latest else {
            "state": "baseline", "kind": "neutral", "text": "Building baseline", "reason": "No completed workouts", "matchedCount": 0, "change": None}
    periods = {}
    for days in (7, 28):
        group = [w for w in records if now - days * DAY <= epoch(w["startTime"]) <= now]
        run_group = [w for w in group if w.get("sport", "").lower() == "running" or (w.get("sport", "").lower() not in NON_RUN_SPORTS and w.get("runSeconds", 0) >= 300)]
        totals = {exercise: 0 for exercise in EXERCISES}
        unknown_reps = 0
        hr_values, rpe_values = [], []
        for w in group:
            if w.get("repsPerLap"):
                unknown_reps += 1
            else:
                for key, value in (w.get("reps") or {}).items():
                    if key in totals and finite(value) is not None:
                        totals[key] += value
                if w.get("repsIncomplete"):
                    unknown_reps += 1
            hr = (w.get("hrLoad") or {}).get("value")
            if finite(hr) is not None and not w.get("analysisStale"):
                hr_values.append(hr)
            notes = w.get("trainingNotes", parse_notes(w.get("notes")))
            if notes["rpe"] is not None and not notes["errors"] and not w.get("analysisStale"):
                rpe_values.append(notes["rpe"] * w["durationSeconds"] / 60)
        periods[str(days)] = {"sessions": len(group), "runs": len(run_group),
                             "staleSessions": sum(bool(w.get("analysisStale")) for w in group),
                             "runMeters": round(sum(w["distanceMeters"] for w in run_group), 1),
                             "minutes": round(sum(w["durationSeconds"] for w in group) / 60, 1),
                             "reps": totals, "unquantifiedRepSessions": unknown_reps,
                             "hrTrimp": {"value": round(sum(hr_values), 1) if hr_values else None, "coveredSessions": len(hr_values), "totalSessions": len(group), "estimated": True},
                             "sessionRpe": {"value": round(sum(rpe_values), 1) if rpe_values else None, "coveredSessions": len(rpe_values), "totalSessions": len(group)}}
    return {"performance": performance, "workload": periods, "acceptedSessions": len(records),
            "excludedSessions": len(workouts) - len(records)}

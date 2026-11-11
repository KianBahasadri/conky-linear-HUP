import json
import math
import xml.etree.ElementTree as ET

import pytest

from datetime import datetime, timedelta, timezone

import fetch_workouts as workouts


TCX_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2">
  <Activities>
    <Activity Sport="{sport}">
      <Id>{start}</Id>
      <Lap StartTime="{start}">
        <TotalTimeSeconds>{duration}</TotalTimeSeconds>
        <DistanceMeters>{distance}</DistanceMeters>
        <Calories>{calories}</Calories>
        <Track>
          <Trackpoint>
            <Time>{start}</Time>
            <DistanceMeters>10.0</DistanceMeters>
            {heart_rate}
            <Extensions>
              <ns3:TPX>
                <ns3:RunCadence>{cadence}</ns3:RunCadence>
              </ns3:TPX>
            </Extensions>
          </Trackpoint>
          <Trackpoint>
            <Time>{end}</Time>
            <DistanceMeters>{distance}</DistanceMeters>
            {heart_rate}
            <Extensions>
              <ns3:TPX>
                <ns3:RunCadence>{cadence}</ns3:RunCadence>
              </ns3:TPX>
            </Extensions>
          </Trackpoint>
        </Track>
      </Lap>
      {notes_block}
    </Activity>
  </Activities>
</TrainingCenterDatabase>
"""


def heart_rate_block(bpm):
    if bpm is None:
        return ""
    return f"<HeartRateBpm><Value>{bpm}</Value></HeartRateBpm>"


def write_tcx(
    path,
    sport="Running",
    start="2026-08-26T21:30:48Z",
    duration_seconds=1429,
    distance=2482.9,
    bpm=154,
    cadence=61,
    calories=180,
    notes="",
):
    start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
    path.write_text(
        TCX_TEMPLATE.format(
            sport=sport,
            start=start,
            end=(start_dt + timedelta(seconds=duration_seconds)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            duration=duration_seconds,
            distance=distance,
            calories=calories,
            heart_rate=heart_rate_block(bpm),
            cadence=cadence,
            notes_block=f"<Notes>{notes}</Notes>" if notes else "",
        ),
        encoding="utf-8",
    )


def write_circuit_tcx(path, positions, notes="8 3 11"):
    ns = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
    ext = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
    root = ET.Element(f"{{{ns}}}TrainingCenterDatabase")
    activities = ET.SubElement(root, f"{{{ns}}}Activities")
    activity = ET.SubElement(activities, f"{{{ns}}}Activity", Sport="Running")
    lap = ET.SubElement(activity, f"{{{ns}}}Lap")
    ET.SubElement(lap, f"{{{ns}}}TotalTimeSeconds").text = str(positions[-1][0] - positions[0][0])
    lap_distance = ET.SubElement(lap, f"{{{ns}}}DistanceMeters")
    track = ET.SubElement(lap, f"{{{ns}}}Track")
    meters = 0.0
    previous = positions[0]
    for stamp, latitude, longitude in positions:
        step = math.hypot(
            (latitude - previous[1]) * 111320.0,
            (longitude - previous[2]) * 111320.0 * math.cos(math.radians(40.0)),
        )
        meters += step
        point = ET.SubElement(track, f"{{{ns}}}Trackpoint")
        ET.SubElement(point, f"{{{ns}}}Time").text = datetime.fromtimestamp(stamp, timezone.utc).isoformat()
        ET.SubElement(point, f"{{{ns}}}DistanceMeters").text = str(meters)
        position = ET.SubElement(point, f"{{{ns}}}Position")
        ET.SubElement(position, f"{{{ns}}}LatitudeDegrees").text = str(latitude)
        ET.SubElement(position, f"{{{ns}}}LongitudeDegrees").text = str(longitude)
        extensions = ET.SubElement(point, f"{{{ns}}}Extensions")
        tpx = ET.SubElement(extensions, f"{{{ext}}}TPX")
        ET.SubElement(tpx, f"{{{ext}}}RunCadence").text = "80" if step > 0.1 else "0"
        previous = (stamp, latitude, longitude)
    lap_distance.text = str(meters)
    ET.SubElement(activity, f"{{{ns}}}Notes").text = notes
    path.write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")


def test_parse_workout_extracts_summary(tmp_path):
    tcx_path = tmp_path / "run.tcx"
    write_tcx(tcx_path)

    workout = workouts.parse_workout(tcx_path)

    assert workout["sport"] == "Running"
    assert workout["durationSeconds"] == 1429
    assert workout["distanceMeters"] == pytest.approx(2482.9)
    assert workout["calories"] == 180
    assert workout["avgHeartRate"] == 154
    assert workout["maxHeartRate"] == 154
    assert workout["avgCadence"] == 61
    assert workout["startTime"] == datetime(2026, 8, 26, 21, 30, 48, tzinfo=timezone.utc)
    assert workout["truncated"] is False
    assert [point[1:] for point in workout["track"]] == [(10.0, 61), (2482.9, 61)]


def test_parse_workout_salvages_a_truncated_upload(tmp_path):
    tcx_path = tmp_path / "run.tcx"
    write_tcx(tcx_path)
    text = tcx_path.read_text(encoding="utf-8")
    second_point = text.index("<Trackpoint>", text.index("<Trackpoint>") + 1)
    tcx_path.write_text(text[: second_point + 30], encoding="utf-8")

    workout = workouts.parse_workout(tcx_path)

    assert workout["truncated"] is True
    assert workout["durationSeconds"] == 1429
    assert workout["distanceMeters"] == pytest.approx(2482.9)
    assert len(workout["track"]) == 1


def test_parse_workout_without_heart_rate(tmp_path):
    tcx_path = tmp_path / "run.tcx"
    write_tcx(tcx_path, bpm=None)

    workout = workouts.parse_workout(tcx_path)

    assert workout["avgHeartRate"] is None
    assert workout["maxHeartRate"] is None
    assert workout["avgCadence"] == 61


def test_parse_workout_rejects_files_without_activity(tmp_path):
    tcx_path = tmp_path / "bad.tcx"
    tcx_path.write_text("<TrainingCenterDatabase/>", encoding="utf-8")

    with pytest.raises(ValueError, match="no Activity"):
        workouts.parse_workout(tcx_path)


def test_load_workouts_skips_broken_files(tmp_path):
    write_tcx(tmp_path / "good.tcx")
    (tmp_path / "bad.tcx").write_text("<not-tcx>", encoding="utf-8")

    parsed, failures = workouts.load_workouts(tmp_path)

    assert len(parsed) == 1
    assert failures == 1


def test_load_workouts_reuses_analysis_until_a_file_changes(monkeypatch, tmp_path):
    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir()
    write_tcx(workouts_dir / "good.tcx")
    (workouts_dir / "bad.tcx").write_text("<not-tcx>", encoding="utf-8")
    analysis_path = tmp_path / "analysis.json"
    first, first_failures = workouts.load_workouts(workouts_dir, analysis_path)
    analyzed = []
    real_analyze = workouts.analyze_file
    monkeypatch.setattr(
        workouts, "analyze_file", lambda path: analyzed.append(path.name) or real_analyze(path)
    )

    second, second_failures = workouts.load_workouts(workouts_dir, analysis_path)

    assert analyzed == []
    assert second == first
    assert second[0]["startTime"] == datetime(2026, 8, 26, 21, 30, 48, tzinfo=timezone.utc)
    assert first_failures == second_failures == 1

    write_tcx(workouts_dir / "good.tcx", distance=12345.6)
    third, _ = workouts.load_workouts(workouts_dir, analysis_path)

    assert analyzed == ["good.tcx"]
    assert third[0]["distanceMeters"] == pytest.approx(12345.6)


def test_load_workouts_ignores_an_analysis_cache_from_another_version(tmp_path):
    write_tcx(tmp_path / "good.tcx")
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(json.dumps({"version": -1, "files": {"good.tcx": {}}}), encoding="utf-8")

    parsed, failures = workouts.load_workouts(tmp_path, analysis_path)

    assert len(parsed) == 1 and failures == 0
    assert json.loads(analysis_path.read_text(encoding="utf-8"))["version"] == workouts.ANALYSIS_VERSION


def metric_units():
    return {
        "name": "metric",
        "distanceDivisor": 1000.0,
        "distanceSymbol": "km",
        "paceSymbol": "/km",
    }


def test_build_status_last_and_week(monkeypatch):
    now = datetime(2026, 8, 27, 12, 0, 0).astimezone()
    monkeypatch.setattr(workouts, "WEEK_WINDOW", timedelta(days=7))

    run_10k = {
        "file": "a.tcx",
        "sport": "Running",
        "startTime": now - timedelta(days=2),
        "endTime": now - timedelta(days=2),
        "durationSeconds": 3000,
        "distanceMeters": 10000,
        "calories": 0,
        "avgHeartRate": 155,
        "maxHeartRate": 172,
        "avgCadence": None,
    }
    ride_old = {
        "file": "b.tcx",
        "sport": "Cycling",
        "startTime": now - timedelta(days=20),
        "endTime": now - timedelta(days=20),
        "durationSeconds": 3600,
        "distanceMeters": 30000,
        "calories": 0,
        "avgHeartRate": None,
        "maxHeartRate": None,
        "avgCadence": None,
    }
    run_5k = {
        "file": "c.tcx",
        "sport": "Running",
        "startTime": now - timedelta(hours=3),
        "endTime": now - timedelta(hours=3),
        "durationSeconds": 1429,
        "distanceMeters": 2482.9,
        "calories": 0,
        "avgHeartRate": None,
        "maxHeartRate": None,
        "avgCadence": 61,
    }

    status = workouts.build_status([ride_old, run_10k, run_5k], metric_units(), now)

    assert status["ok"] is True
    assert status["workoutCount"] == 3
    assert status["runCount"] == 2
    assert status["lastSport"] == "Run"
    assert status["lastDateText"] == "Today"
    assert status["lastDistanceText"] == "2.5 km"
    assert status["lastDurationText"] == "23:49"
    assert status["lastPaceText"] == "9:36 /km"
    assert status["lastRunPaceText"] == ""
    assert "lastScoreText" not in status
    assert status["lastHeartRateText"] == ""
    assert status["lastCadenceText"] == "61 spm avg"
    assert status["weekRuns"] == 2
    assert status["weekDistanceText"] == "12.5 km"
    assert status["weekDurationText"] == "1:13:49"
    assert status["monthRuns"] == 2
    assert status["progressVerdict"] == "Building baseline"
    assert status["workload"]["7"]["runMeters"] == pytest.approx(12482.9)
    assert "runs / 28d" in status["monthSummaryText"]
    assert [entry["distanceUnits"] for entry in status["recent"]] == [10.0, 2.48]
    assert [entry["runUnits"] for entry in status["recent"]] == [None, None]
    assert status["recent"][-1]["isLast"] is True
    assert status["recent"][0]["isLast"] is False


def analyzed_run(stamp, score, meters=6000.0, run_meters=5000.0, sport="Running", **extra):
    run = {
        "file": f"{stamp:%Y%m%d%H%M}.tcx",
        "sport": sport,
        "startTime": stamp,
        "endTime": stamp + timedelta(seconds=2400),
        "durationSeconds": 2400,
        "distanceMeters": meters,
        "calories": 0,
        "avgHeartRate": None,
        "maxHeartRate": None,
        "avgCadence": None,
        "truncated": False,
        "trackMeters": meters,
        "runSeconds": 1650,
        "runMeters": run_meters,
        "walkSeconds": 600,
        "walkMeters": meters - run_meters,
        "warmupMeters": 400.0,
        "cooldownMeters": 400.0,
        "score": score,
    }
    run.update(extra)
    return run


def history(now, level_at_day, days=84, every_days=2.5):
    runs = []
    for index in range(int(days / every_days)):
        day = index * every_days
        easy = 7 if index % 4 == 3 else 0
        gap = (0.4, 1.9, 1.1, 2.6)[index % 4]
        runs.append(analyzed_run(now - timedelta(days=days - day), level_at_day(day) - gap - easy))
    return runs


def test_build_status_reports_walk_excluded_pace_and_effort(monkeypatch):
    now = datetime(2026, 10, 22, 20, 0, 0).astimezone()
    runs = history(now - timedelta(days=1), lambda day: 33)

    status = workouts.build_status(runs, metric_units(), now)

    assert status["lastDistanceText"] == "6.0 km"
    assert status["lastPaceText"] == "6:40 /km"
    assert status["lastRunPaceText"] == "5:30 /km"
    assert status["lastRunDistanceText"] == "5.0 km"
    assert status["lastWalkDistanceText"] == "1.0 km"
    assert "fitnessText" not in status and "lastScoreText" not in status
    assert status["progressVerdict"] == "Building baseline"
    assert status["progressKind"] == "neutral"
    recent = status["recent"]
    assert len(recent) == workouts.RECENT_LIMIT
    assert recent[-1]["runUnits"] == 5.0
    assert all("fitness" not in entry and "score" not in entry for entry in recent)
    assert recent[-1]["inWindow"] is True and recent[0]["inWindow"] is False


def test_unvalidated_rising_scores_cannot_trigger_a_performance_verdict():
    now = datetime(2026, 10, 22, 20, 0, 0).astimezone()
    runs = history(now, lambda day: 29 + max(0.0, day - 42) * 5 / 42)

    status = workouts.build_status(runs, metric_units(), now)

    assert status["progressVerdict"] == "Building baseline"
    assert status["progressKind"] == "neutral"
    assert "trendSeconds" not in status


def test_unvalidated_falling_scores_cannot_trigger_a_performance_verdict():
    now = datetime(2026, 10, 22, 20, 0, 0).astimezone()
    runs = history(now, lambda day: 34 - max(0.0, day - 42) * 5 / 42)

    status = workouts.build_status(runs, metric_units(), now)

    assert status["progressVerdict"] == "Building baseline"
    assert status["progressKind"] == "neutral"


def test_build_status_flags_a_long_break_without_calling_it_better():
    now = datetime(2026, 10, 22, 20, 0, 0).astimezone()
    runs = history(now - timedelta(days=40), lambda day: 33)

    status = workouts.build_status(runs, metric_units(), now)

    assert status["progressVerdict"] != "Better"
    assert status["progressKind"] in {"caution", "danger"}
    assert status["performance"]["running"]["reason"] == "Recent workout needed"


def test_build_status_counts_only_runs():
    now = datetime(2026, 10, 22, 20, 0, 0).astimezone()
    run = analyzed_run(now - timedelta(days=3), 32.0)
    ride = analyzed_run(now - timedelta(days=2), None, sport="Biking", runSeconds=0, runMeters=0.0)
    walk = analyzed_run(now - timedelta(days=1), None, sport="Other", runSeconds=120, runMeters=400.0)
    jog = analyzed_run(now - timedelta(hours=5), 30.0, sport="Other", runSeconds=900, runMeters=2700.0)

    status = workouts.build_status([run, ride, walk, jog], metric_units(), now)

    assert status["workoutCount"] == 4
    assert status["runCount"] == 2
    assert status["weekRuns"] == 2
    assert status["lastSport"] == "Other"
    assert len(status["recent"]) == 2
    assert status["workload"]["7"]["runs"] == 2


def test_build_status_without_runs_reports_an_error():
    now = datetime(2026, 10, 22, 20, 0, 0).astimezone()
    ride = analyzed_run(now - timedelta(days=2), None, sport="Biking", runSeconds=0, runMeters=0.0)

    status = workouts.build_status([ride], metric_units(), now)

    assert status["ok"] is False
    assert status["error"] == "No runs uploaded yet"


def test_truncated_runs_keep_their_pace_but_not_a_walk_split():
    now = datetime(2026, 10, 22, 20, 0, 0).astimezone()
    cut = analyzed_run(now - timedelta(hours=2), 33.0, meters=10000.0, truncated=True, trackMeters=5500.0)

    status = workouts.build_status([cut], metric_units(), now)

    assert status["lastDistanceText"] == "10.0 km"
    assert status["lastRunPaceText"] == "5:30 /km"
    assert status["lastWalkDistanceText"] == ""
    assert status["recent"][0]["runUnits"] is None


def test_build_status_week_window_excludes_old(monkeypatch):
    now = datetime(2026, 8, 27, 12, 0, 0).astimezone()
    old_run = {
        "file": "old.tcx",
        "sport": "Running",
        "startTime": now - timedelta(days=9),
        "endTime": now - timedelta(days=9),
        "durationSeconds": 600,
        "distanceMeters": 1000,
        "calories": 0,
        "avgHeartRate": None,
        "maxHeartRate": None,
        "avgCadence": None,
    }

    status = workouts.build_status([old_run], metric_units(), now)

    assert status["weekRuns"] == 0
    assert status["weekDistanceText"] == "0.0 km"


def test_units_rejects_unknown(monkeypatch):
    monkeypatch.setenv("WORKOUTS_UNITS", "furlongs")
    with pytest.raises(ValueError, match="metric or imperial"):
        workouts.units()


def test_format_pace_handles_zero_distance():
    assert workouts.format_pace(100, 0, metric_units()) == "--"


def test_main_writes_status_cache(monkeypatch, tmp_path):
    workouts_dir = tmp_path / "workouts"
    workouts_dir.mkdir()
    write_tcx(workouts_dir / "run.tcx")
    monkeypatch.setenv("WORKOUTS_DIR", str(workouts_dir))
    monkeypatch.setenv("WORKOUTS_WEATHER_ENABLED", "0")
    monkeypatch.setattr(workouts, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(workouts, "STATUS_PATH", tmp_path / "cache" / "workouts-status.json")
    monkeypatch.setattr(workouts, "ANALYSIS_PATH", tmp_path / "cache" / "workouts-analysis.json")

    exit_code = workouts.main()

    assert exit_code == 0
    status = json.loads(
        (tmp_path / "cache" / "workouts-status.json").read_text(encoding="utf-8")
    )
    assert status["ok"] is True
    assert status["lastSport"] == "Run"
    analysis = json.loads(
        (tmp_path / "cache" / "workouts-analysis.json").read_text(encoding="utf-8")
    )
    assert list(analysis["files"]) == ["run.tcx"]


def test_main_reports_missing_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKOUTS_DIR", str(tmp_path / "nope"))
    monkeypatch.setattr(workouts, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(workouts, "STATUS_PATH", tmp_path / "cache" / "workouts-status.json")
    monkeypatch.setattr(workouts, "ANALYSIS_PATH", tmp_path / "cache" / "workouts-analysis.json")

    exit_code = workouts.main()

    assert exit_code == 1
    status = json.loads(
        (tmp_path / "cache" / "workouts-status.json").read_text(encoding="utf-8")
    )
    assert status["ok"] is False
    assert "missing" in status["error"]


def test_parse_workout_extracts_notes(tmp_path):
    tcx_path = tmp_path / "run_notes.tcx"
    write_tcx(tcx_path, notes="7 pushup 5 pullup 10 situp")

    workout = workouts.parse_workout(tcx_path)
    assert workout["notes"] == "7 pushup 5 pullup 10 situp"


def test_circuit_volume_is_separate_from_performance():
    now = datetime(2026, 10, 30, 12, 0, 0).astimezone()
    run = analyzed_run(
        now - timedelta(hours=1),
        score=30.0,
        notes="7 pushup 5 pullup 10 situp",
        avgHeartRate=147,
        laps=6,
        reps={"pushups": 42, "pullups": 30, "situps": 60},
        totalLoad=180.0,
        cardioLoad=60.0,
        strengthLoad=120.0,
    )
    status = workouts.build_status([run], metric_units(), now)
    assert status["lastStrengthText"] == "42 push · 30 pull · 60 sit"
    assert "rateOfProgress" not in status and "chronicTrainingLoad" not in status
    assert status["workload"]["7"]["reps"] == {"pushups": 42, "pullups": 30, "situps": 60}
    assert status["progressKind"] == "neutral"


def test_numeric_notes_reanalyze_existing_upload_and_reach_overlay_status(tmp_path, circuit_positions):
    tcx_path = tmp_path / "run.tcx"
    write_circuit_tcx(tcx_path, circuit_positions())
    legacy_workout = workouts.analyze_file(tcx_path)
    legacy_workout.update(
        laps=9, reps={"pushups": 72, "pullups": 27, "situps": 99},
        strengthLoad=106.2, totalLoad=166.2, cardioLoad=60.0,
    )
    stat = tcx_path.stat()
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(
        json.dumps({
            "version": 7,
            "files": {
                tcx_path.name: {
                    "key": [stat.st_size, stat.st_mtime_ns],
                    "workout": workouts.encode_workout(legacy_workout),
                }
            },
        }),
        encoding="utf-8",
    )

    parsed, failures = workouts.load_workouts(tmp_path, analysis_path)
    now = parsed[0]["startTime"] + timedelta(hours=1)
    status = workouts.build_status(parsed, metric_units(), now)

    assert failures == 0
    assert parsed[0]["runBouts"] > parsed[0]["laps"]
    assert status["lastLapCount"] == 4
    assert status["lastLapCountSource"] == "gps"
    assert status["lastStrengthText"] == "32 push · 12 pull · 44 sit"
    assert "lastStrengthLoad" not in status and "lastTotalLoad" not in status
    assert status["workload"]["7"]["reps"] == {"pushups": 32, "pullups": 12, "situps": 44}
    assert status["performance"]["circuit"]["reason"] == "No matching routine in recorded history"
    assert status["trainingHeadline"].startswith("4 laps")
    assert status["trainingShortDetail"] == "32/12/44 reps"
    assert "trainingPages" not in status
    saved = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert saved["version"] == workouts.ANALYSIS_VERSION
    assert saved["files"][tcx_path.name]["workout"]["reps"] == {
        "pushups": 32, "pullups": 12, "situps": 44,
    }


def test_unknown_gps_laps_display_per_lap_reps_and_mark_load_incomplete(tmp_path):
    tcx_path = tmp_path / "run.tcx"
    write_tcx(tcx_path, notes="8 3 11")
    run = workouts.analyze_file(tcx_path)

    status = workouts.build_status([run], metric_units(), run["startTime"] + timedelta(hours=1))

    assert status["lastLapCount"] is None
    assert status["lastLapCountSource"] == "unknown"
    assert status["lastStrengthText"] == "8 push · 3 pull · 11 sit /lap"
    assert status["workload"]["7"]["reps"] == {"pushups": 0, "pullups": 0, "situps": 0}
    assert status["workload"]["7"]["unquantifiedRepSessions"] == 1
    assert status["trainingShortDetail"].endswith("/lap")
    assert "rateOfProgressText" not in status
    assert status["progressVerdict"] == "Building baseline"
    assert status["progressKind"] == "neutral"


@pytest.mark.parametrize("incomplete", ["truncated", "distance"])
def test_incomplete_track_does_not_extrapolate_circuit_totals(
    tmp_path, monkeypatch, circuit_positions, incomplete
):
    tcx_path = tmp_path / "run.tcx"
    write_circuit_tcx(tcx_path, circuit_positions())
    parsed = workouts.parse_workout(tcx_path)
    if incomplete == "truncated":
        parsed["truncated"] = True
    else:
        parsed["distanceMeters"] *= 2
    monkeypatch.setattr(workouts, "parse_workout", lambda _path: dict(parsed))

    run = workouts.analyze_file(tcx_path)

    assert run["laps"] is None
    assert run["reps"] == {"pushups": 8, "pullups": 3, "situps": 11}
    assert run["repsPerLap"] is True
    assert run["repsIncomplete"] is True


def test_optional_effort_keeps_numeric_shorthand_and_source_laps(tmp_path, circuit_positions):
    path = tmp_path / "run.tcx"
    write_circuit_tcx(path, circuit_positions(), notes="8 3 11; rpe=7; variant=standard")
    result = workouts.analyze_file(path)
    assert result["laps"] == 4
    assert result["reps"] == {"pushups": 32, "pullups": 12, "situps": 44}
    assert result["trainingNotes"]["rpe"] == 7
    assert result["circuit"]["seconds"] > 0
    assert "totalLoad" not in result and "strengthLoad" not in result


def test_hr_calibration_change_invalidates_per_file_cache(tmp_path, monkeypatch):
    path = tmp_path / "run.tcx"
    write_tcx(path)
    cache = tmp_path / "analysis.json"
    workouts.load_workouts(tmp_path, cache)
    calls = []
    original = workouts.analyze_file
    monkeypatch.setattr(workouts, "analyze_file", lambda path: calls.append(path.name) or original(path))
    monkeypatch.setenv("WORKOUTS_MAX_HR", "200")
    workouts.load_workouts(tmp_path, cache)
    assert calls == ["run.tcx"]
    assert json.loads(cache.read_text())["hrSettings"]["maximumHR"] == 200


def test_changed_unreadable_upload_retains_last_good_file_summary(tmp_path):
    path = tmp_path / "run.tcx"
    write_tcx(path)
    cache = tmp_path / "analysis.json"
    first, _ = workouts.load_workouts(tmp_path, cache)
    path.write_text("<upload-in-progress>")
    retained, failures = workouts.load_workouts(tmp_path, cache)
    assert failures == 1 and len(retained) == 1
    assert retained[0]["distanceMeters"] == first[0]["distanceMeters"]
    assert retained[0]["analysisStale"] is True


def test_refresh_error_retains_a_visible_stale_status(tmp_path, monkeypatch):
    path = tmp_path / "status.json"
    path.write_text(json.dumps({"ok": True, "updatedAt": "earlier", "lastDistanceText": "4.0 km"}))
    monkeypatch.setattr(workouts, "STATUS_PATH", path)
    workouts.write_error("Upload unreadable")
    status = json.loads(path.read_text())
    assert status["ok"] and status["stale"] and status["lastDistanceText"] == "4.0 km"
    assert status["updatedAt"] == "earlier" and status["error"] == "Upload unreadable"


@pytest.mark.parametrize("previous", ["null", "[]", '"broken"'])
def test_refresh_error_recovers_from_a_nonobject_status(tmp_path, monkeypatch, previous):
    path = tmp_path / "status.json"
    path.write_text(previous)
    monkeypatch.setattr(workouts, "STATUS_PATH", path)
    workouts.write_error("Upload unreadable")
    status = json.loads(path.read_text())
    assert status["ok"] is False and status["error"] == "Upload unreadable"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-10"])
def test_nonfinite_or_negative_workout_totals_are_rejected(tmp_path, value):
    path = tmp_path / "run.tcx"
    write_tcx(path)
    path.write_text(path.read_text().replace("<TotalTimeSeconds>1429</TotalTimeSeconds>", f"<TotalTimeSeconds>{value}</TotalTimeSeconds>"))
    with pytest.raises(ValueError, match="Invalid workout totals"):
        workouts.parse_workout(path)

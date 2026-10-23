import json

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
        ),
        encoding="utf-8",
    )


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
    assert status["lastScoreText"] == ""
    assert status["lastHeartRateText"] == ""
    assert status["lastCadenceText"] == "61 spm avg"
    assert status["weekRuns"] == 2
    assert status["weekDistanceText"] == "12.5 km"
    assert status["weekDurationText"] == "1:13:49"
    assert status["monthRuns"] == 2
    assert status["progressVerdict"] == "Steady"
    assert status["trendText"] == ""
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
    assert status["lastScoreText"] == workouts.equivalent_text(runs[-1]["score"])
    assert status["fitnessText"] and status["trendText"]
    assert status["progressVerdict"] == "Steady"
    assert status["progressKind"] == "neutral"
    recent = status["recent"]
    assert len(recent) == workouts.RECENT_LIMIT
    assert recent[-1]["runUnits"] == 5.0 and recent[-1]["score"] == runs[-1]["score"]
    assert all(entry["fitness"] == pytest.approx(33, abs=2.5) for entry in recent)
    assert recent[-1]["inWindow"] is True and recent[0]["inWindow"] is False


def test_build_status_calls_rising_fitness_better():
    now = datetime(2026, 10, 22, 20, 0, 0).astimezone()
    runs = history(now, lambda day: 29 + max(0.0, day - 42) * 5 / 42)

    status = workouts.build_status(runs, metric_units(), now)

    assert status["progressVerdict"] == "Better"
    assert status["progressKind"] == "good"
    assert status["trendText"].startswith("−")
    assert status["trendSeconds"] <= -workouts.TREND_MIN_SECONDS


def test_build_status_calls_falling_fitness_worse():
    now = datetime(2026, 10, 22, 20, 0, 0).astimezone()
    runs = history(now, lambda day: 34 - max(0.0, day - 42) * 5 / 42)

    status = workouts.build_status(runs, metric_units(), now)

    assert status["progressVerdict"] == "Worse"
    assert status["progressKind"] == "danger"
    assert status["trendText"].startswith("+")


def test_build_status_flags_a_long_break_without_calling_it_better():
    now = datetime(2026, 10, 22, 20, 0, 0).astimezone()
    runs = history(now - timedelta(days=40), lambda day: 33)

    status = workouts.build_status(runs, metric_units(), now)

    assert status["progressVerdict"] != "Better"
    assert status["progressKind"] in {"caution", "danger"}
    assert status["trendSeconds"] > 0


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
    assert [entry["score"] for entry in status["recent"]] == [32.0, 30.0]


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

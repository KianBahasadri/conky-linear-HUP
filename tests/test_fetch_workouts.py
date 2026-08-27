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

    def fake_now():
        return now

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

    status = workouts.build_status([ride_old, run_10k, run_5k], metric_units())

    assert status["ok"] is True
    assert status["workoutCount"] == 3
    assert status["lastSport"] == "Run"
    assert status["lastDateText"] == "Today"
    assert status["lastDistanceText"] == "2.5 km"
    assert status["lastDurationText"] == "23:49"
    assert status["lastPaceText"] == "9:36 /km"
    assert status["lastHeartRateText"] == ""
    assert status["lastCadenceText"] == "61 spm avg"
    assert status["weekRuns"] == 2
    assert status["weekDistanceText"] == "12.5 km"
    assert status["weekDurationText"] == "1:13:49"
    assert [entry["distanceUnits"] for entry in status["recent"]] == [30.0, 10.0, 2.48]
    assert status["recent"][-1]["isLast"] is True
    assert status["recent"][0]["isLast"] is False


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

    status = workouts.build_status([old_run], metric_units())

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

    exit_code = workouts.main()

    assert exit_code == 0
    status = json.loads(
        (tmp_path / "cache" / "workouts-status.json").read_text(encoding="utf-8")
    )
    assert status["ok"] is True
    assert status["lastSport"] == "Run"


def test_main_reports_missing_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("WORKOUTS_DIR", str(tmp_path / "nope"))
    monkeypatch.setattr(workouts, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(workouts, "STATUS_PATH", tmp_path / "cache" / "workouts-status.json")

    exit_code = workouts.main()

    assert exit_code == 1
    status = json.loads(
        (tmp_path / "cache" / "workouts-status.json").read_text(encoding="utf-8")
    )
    assert status["ok"] is False
    assert "missing" in status["error"]

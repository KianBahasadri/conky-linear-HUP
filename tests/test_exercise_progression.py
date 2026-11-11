from datetime import datetime, timedelta, timezone

import pytest

import exercise_progression as p

BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)
NOW = (BASE + timedelta(days=20)).timestamp()


def context():
    return {"weight": {"available": True, "medianKg": 94, "stale": False},
            "weather": {"available": True, "temperatureC": 10, "dewPointC": 5, "windKmh": 8, "solarWm2": 30}}


def session(day, seconds=2400, notes="8 3 11"):
    parsed = p.parse_notes(notes)
    record = {"file": f"run-{day}.tcx", "sport": "Running", "startTime": BASE + timedelta(days=day),
              "endTime": BASE + timedelta(days=day, seconds=seconds + 600),
              "durationSeconds": seconds + 600, "distanceMeters": 4000, "runSeconds": 1200,
              "notes": notes, "trainingNotes": parsed, "context": context(),
              "circuit": {"laps": 4, "seconds": seconds, "latitude": 44, "longitude": -76,
                          "lapMeters": 850, "widthMeters": 300, "heightMeters": 200, "timingResolutionSeconds": 40}}
    record.update(p.repetition_summary(parsed, 4))
    return record


@pytest.mark.parametrize("notes, expected", [
    ("8 3 11", {"pushups": 8, "pullups": 3, "situps": 11}),
    ("8 push-ups + 3 pullups + 11 sit ups", {"pushups": 8, "pullups": 3, "situps": 11}),
    ("8pushups", {"pushups": 8}),
])
def test_rep_formats_and_optional_effort_are_independent(notes, expected):
    result = p.parse_notes(notes + "; rpe=7; variant=standard; rest=60")
    assert result["counts"] == expected
    assert result["rpe"] == 7 and result["variant"] == "standard" and result["restSeconds"] == 60
    assert result["errors"] == []


@pytest.mark.parametrize("suffix", ["rpe=nan", "rpe=11", "rpe=-1", "rpe=6; rpe=8", "laps=2.5", "rir=2/3", "rest=-10", "variant=<script>", "unknown=1"])
def test_bad_metadata_remains_visible_and_cannot_qualify_comparisons(suffix):
    result = p.parse_notes("8 3 11; " + suffix)
    assert result["counts"] == {"pushups": 8, "pullups": 3, "situps": 11}
    assert result["errors"]


@pytest.mark.parametrize("text", ["8 -3 11", "8 3.5 11", "-8 3 11"])
def test_invalid_numeric_prescriptions_cannot_masquerade_as_normal_runs(text):
    parsed = p.parse_notes(text + "; rpe=7")
    assert parsed["errors"] and parsed["counts"] == {}


def test_unquantified_exercises_and_unknown_laps_never_become_zero_or_guessed_totals():
    notes = p.parse_notes("6 pushups + pullups")
    result = p.repetition_summary(notes, None)
    assert notes["unquantified"] == ["pullups"]
    assert result["reps"] == {"pushups": 6} and result["repsPerLap"] and result["repsIncomplete"]
    ordinary = p.repetition_summary(p.parse_notes("felt good"), None)
    assert not ordinary["repsPerLap"] and not ordinary["repsIncomplete"]


def test_explicit_totals_and_conflicting_lap_sources_are_respected():
    total = p.repetition_summary(p.parse_notes("total 32 pushups 12 pullups 44 situps"), 4)
    assert total["reps"] == {"pushups": 32, "pullups": 12, "situps": 44}
    conflict = p.repetition_summary(p.parse_notes("8 3 11; laps=5"), 4)
    assert conflict["laps"] is None and conflict["lapCountSource"] == "conflict" and conflict["repsPerLap"]


def test_integrated_hr_load_preserves_intensity_variation_and_coverage():
    constant = [(second, 150) for second in range(601)]
    varying = [(second, 110 if second < 300 else 190) for second in range(601)]
    a, b = p.heart_rate_load(constant, 600), p.heart_rate_load(varying, 600)
    assert a["coverage"] == b["coverage"] == 1
    assert b["value"] > a["value"]
    assert p.heart_rate_load([(0, 150), (600, 150)], 600)["value"] is None
    assert p.heart_rate_load(constant, 20)["value"] is None
    assert p.heart_rate_load(constant, 600, resting=200, maximum=190)["value"] is None


def test_conflicting_hr_readings_and_nonfinite_values_cannot_make_a_good_load():
    samples = [(second, 150) for second in range(601)]
    samples.append((20, 200))
    assert p.heart_rate_load(samples, 600)["value"] is None
    assert p.heart_rate_load([(0, float("nan")), (1, 999)], 600)["value"] is None


def test_completed_unique_workouts_only_and_no_mixed_load_units():
    valid = session(1, notes="8 3 11; rpe=7")
    duplicate = {**valid, "file": "uploaded-again.tcx"}
    future = session(30)
    invalid = {**session(3), "durationSeconds": float("nan")}
    valid["hrLoad"] = {"value": 50}
    summary = p.summarize([future, duplicate, valid, invalid], NOW)
    assert summary["acceptedSessions"] == 1 and summary["excludedSessions"] == 3
    week = summary["workload"]["28"]
    assert week["reps"] == {"pushups": 32, "pullups": 12, "situps": 44}
    assert week["hrTrimp"]["value"] == 50
    assert week["sessionRpe"]["value"] == 350
    assert "totalLoad" not in summary and "rateOfProgress" not in summary


def test_unknown_repetitions_and_effort_are_missing_instead_of_zero_observations():
    record = session(18, notes="8 3 11")
    record.update(p.repetition_summary(record["trainingNotes"], None))
    summary = p.summarize([record], NOW)
    week = summary["workload"]["7"]
    assert week["reps"] == {"pushups": 0, "pullups": 0, "situps": 0}
    assert week["unquantifiedRepSessions"] == 1
    assert week["sessionRpe"]["value"] is None and week["sessionRpe"]["coveredSessions"] == 0


def improving_sessions():
    return [session(day, 2400 if day < 4 else 2000) for day in range(8)]


def test_reproducible_matched_performance_change_needs_independent_history():
    records = improving_sessions()
    result = p.summarize(records, (BASE + timedelta(days=8)).timestamp())["performance"]["circuit"]
    assert result["state"] == "improving" and result["text"] == "Faster"
    assert result["change"] == -400 and result["pValue"] < 0.05
    assert result["baselineCount"] == result["recentCount"] == 4
    assert result["baselineFromEpoch"] == BASE.timestamp()
    assert result["baselineToEpoch"] == (BASE + timedelta(days=3)).timestamp()
    assert result["recentFromEpoch"] == (BASE + timedelta(days=4)).timestamp()
    assert result["recentToEpoch"] == (BASE + timedelta(days=7)).timestamp()
    small = p.summarize(records[:4] + records[-1:], (BASE + timedelta(days=8)).timestamp())["performance"]["circuit"]
    assert small["state"] == "baseline" and small["change"] == -400


@pytest.mark.parametrize("change, reason", [
    (lambda w: w["trainingNotes"]["counts"].update(pushups=9), "No matching routine"),
    (lambda w: w["context"]["weight"].update(medianKg=100), "Different bodyweight"),
    (lambda w: w["context"]["weight"].update(stale=True), "Recent weight"),
    (lambda w: w["context"]["weather"].update(temperatureC=30), "Different weather"),
    (lambda w: w["context"]["weather"].update(available=False), "Weather context"),
    (lambda w: w["circuit"].update(longitude=-70), "No matching routine"),
    (lambda w: w["circuit"].update(widthMeters=1000), "No matching routine"),
])
def test_confounded_changes_do_not_generate_an_improvement(change, reason):
    records = improving_sessions()
    change(records[-1])
    result = p.summarize(records, (BASE + timedelta(days=8)).timestamp())["performance"]["circuit"]
    assert result["kind"] == "neutral" and result["state"] == "baseline"
    assert reason in result["reason"]


def test_timing_resolution_noise_and_same_day_repetitions_do_not_create_trends():
    records = [session(day, 2400 if day < 4 else 2390) for day in range(8)]
    result = p.summarize(records, (BASE + timedelta(days=8)).timestamp())["performance"]["circuit"]
    assert result["state"] == "steady"
    same_day = [session(7 + index / 24, 2000) for index in range(8)]
    result = p.summarize(same_day, (BASE + timedelta(days=8)).timestamp())["performance"]["circuit"]
    assert result["state"] == "baseline" and result["matchedCount"] == 0


def test_hr_response_can_be_compared_only_at_matched_continuous_pace():
    records = []
    for day in range(8):
        record = session(day, notes="easy run")
        record["continuousRun"] = {**record["circuit"], "seconds": 1800, "paceSecondsPerKm": 360,
                                   "steadyHR": 150 if day < 4 else 140, "hrCoverage": 1}
        record["avgHeartRate"] = record["continuousRun"]["steadyHR"]
        record["hrLoad"] = {"coverage": 1}
        records.append(record)
    result = p.summarize(records, (BASE + timedelta(days=8)).timestamp())["performance"]["running"]
    assert result["text"] == "Lower HR" and result["unit"] == "bpm"
    records[-1]["continuousRun"]["paceSecondsPerKm"] = 400
    result = p.summarize(records, (BASE + timedelta(days=8)).timestamp())["performance"]["running"]
    assert result["state"] == "baseline"


def test_normal_notes_alone_produce_reps_and_automatic_circuit_comparisons():
    records = improving_sessions()
    result = p.summarize(records, (BASE + timedelta(days=8)).timestamp())
    assert result["performance"]["circuit"]["text"] == "Faster"
    assert "strength" not in result["performance"]
    assert result["workload"]["28"]["reps"] == {"pushups": 256, "pullups": 96, "situps": 352}


def test_workout_without_an_end_timestamp_must_still_be_finished():
    unfinished = session(19.99)
    del unfinished["endTime"]
    assert p.usable_workouts([unfinished], NOW) == []


def test_latest_comparison_is_independent_of_upload_order():
    records = improving_sessions()
    result = p.summarize(list(reversed(records)), (BASE + timedelta(days=8)).timestamp())["performance"]["circuit"]
    assert result["text"] == "Faster" and result["recentToEpoch"] == (BASE + timedelta(days=7)).timestamp()


def test_optional_preexisting_zero_effort_is_still_recorded():
    record = session(18, notes="easy session; rpe=0")
    result = p.summarize([record], NOW)
    assert result["workload"]["7"]["sessionRpe"] == {"value": 0.0, "coveredSessions": 1, "totalSessions": 1}


def test_nonfinite_observation_cannot_produce_a_performance_change():
    records = improving_sessions()
    records[-1]["circuit"]["seconds"] = float("nan")
    result = p.summarize(records, (BASE + timedelta(days=8)).timestamp())["performance"]["circuit"]
    assert result["state"] == "baseline" and result["change"] is None


def test_interval_running_compares_existing_pace_without_additional_logging():
    records = [session(day) for day in range(8)]
    for day, record in enumerate(records):
        record.update(runMeters=3000 if day < 4 else 3300, trackMeters=4000)
    result = p.summarize(records, (BASE + timedelta(days=8)).timestamp())["performance"]["running"]
    assert result["text"] == "Faster" and result["unit"] == "s/km"
    assert result["change"] == pytest.approx(-36.36)
    records[-1]["trainingNotes"]["counts"]["pullups"] = 6
    assert p.summarize(records, (BASE + timedelta(days=8)).timestamp())["performance"]["running"]["state"] == "baseline"


def test_pace_trend_uses_past_recordings_and_breaks_at_missing_data():
    records = [session(day) for day in range(4)]
    for record, meters in zip(records, (4000, 2000, 3600, 3000)):
        record.update(runMeters=meters, trackMeters=4000)
    values = p.pace_series(records)
    assert [v["paceTrendSecondsPerKm"] for v in values[:3]] == [300, 450, 333.33]
    records[2]["truncated"] = True
    values = p.pace_series(records)
    assert values[2]["paceTrendSecondsPerKm"] is None and values[2]["paceBreak"]
    assert values[3]["paceTrendSecondsPerKm"] == 400
    records[3]["runMeters"] = float("nan")
    assert p.recorded_pace(records[3]) is None


def test_same_day_workouts_do_not_overweight_the_pace_median():
    records = [session(1), session(2), session(2.1)]
    for record, meters in zip(records, (4000, 2000, 3000)):
        record.update(runMeters=meters, trackMeters=4000)
    assert p.pace_series(records)[-1]["paceTrendSecondsPerKm"] == 350


@pytest.mark.parametrize("changed", ["class", "long_break"])
def test_pace_median_resets_across_different_session_classes_or_long_breaks(changed):
    records = [session(1), session(2)]
    for record, meters in zip(records, (4000, 3000)):
        record.update(runMeters=meters, trackMeters=4000)
    if changed == "class":
        records[-1]["trainingNotes"] = p.parse_notes("normal run")
    else:
        records[-1]["startTime"] += timedelta(days=30)
    last = p.pace_series(records)[-1]
    assert last["paceBreak"] and last["paceTrendSecondsPerKm"] == 400

import random

import pytest

import run_analysis as analysis


START = 1_700_000_000.0
NOW = 1_800_000_000.0
DAY = 86400.0


def track(segments, start=START):
    """1 Hz (epoch, meters, cadence) points for (seconds, meters per second, cadence) segments."""
    points = [(start, 0.0, None)]
    stamp, meters = start, 0.0
    for seconds, speed, cadence in segments:
        for _ in range(seconds):
            stamp += 1
            meters += speed
            points.append((stamp, meters, cadence))
    return points


def states_for(segments):
    states, _ = analysis.gait_states(*analysis.resample(track(segments)))
    return states


def test_walking_warmup_and_cooldown_count_as_volume_not_running():
    summary = analysis.analyze_track(track([(300, 1.4, 54), (1500, 3.3, 82), (300, 1.4, 54)]))

    assert summary["trackMeters"] == pytest.approx(5790, abs=1)
    assert summary["runSeconds"] == pytest.approx(1500, abs=15)
    assert summary["runMeters"] == pytest.approx(4950, abs=50)
    assert summary["walkMeters"] == pytest.approx(840, abs=50)
    assert summary["warmupMeters"] == pytest.approx(420, abs=30)
    assert summary["cooldownMeters"] == pytest.approx(420, abs=30)
    assert summary["score"] == pytest.approx(analysis.effort_score(1500, 4950), abs=0.3)


def test_speed_alone_classifies_tracks_without_cadence():
    summary = analysis.analyze_track(track([(300, 1.4, None), (1500, 3.3, None), (300, 1.4, None)]))

    assert summary["runMeters"] == pytest.approx(4950, abs=50)
    assert summary["walkMeters"] == pytest.approx(840, abs=50)


def test_walking_cadence_at_running_speed_is_a_sensor_fault_not_a_vehicle():
    states = states_for([(600, 3.6, 82), (400, 3.6, 55), (600, 3.6, 82)])

    assert analysis.VEHICLE not in states
    assert states.count(analysis.RUNNING) >= 1590


def test_vehicle_speeds_are_excluded_from_running():
    states = states_for([(600, 3.2, 82), (600, 11.0, None), (600, 3.2, 82)])
    summary = analysis.analyze_track(track([(600, 3.2, 82), (600, 11.0, None), (600, 3.2, 82)]))

    assert states.count(analysis.VEHICLE) == pytest.approx(600, abs=15)
    assert summary["runMeters"] == pytest.approx(3840, abs=80)


def test_recording_pauses_add_no_time():
    points = track([(600, 3.0, 80)])
    resumed = points[-1][0] + 300
    points += [(resumed + second, points[-1][1] + 3.0 * second, 80) for second in range(1, 601)]

    summary = analysis.analyze_track(points)

    assert summary["runSeconds"] == pytest.approx(1200, abs=15)
    assert summary["walkSeconds"] < 30


def test_short_or_mostly_walked_sessions_get_no_score():
    assert "score" not in analysis.analyze_track(track([(400, 3.2, 82)]))
    assert "score" not in analysis.analyze_track(track([(1800, 1.4, 54), (300, 3.2, 82)]))
    assert analysis.analyze_track([]) == {}


def test_effort_score_puts_short_fast_and_long_steady_runs_on_one_scale():
    five_k = analysis.effort_score(25 * 60, 5000)
    ten_k_matched = analysis.effort_score(25 * 60 * 2 ** 1.15, 10000)
    ten_k_slow = analysis.effort_score(65 * 60, 10000)

    assert abs(five_k - ten_k_matched) < 1.5
    assert five_k - ten_k_slow > 3


def test_equivalent_seconds_inverts_the_score():
    score = analysis.effort_score(1500, 5000)

    assert analysis.equivalent_seconds(score) == pytest.approx(1500, abs=0.5)
    assert analysis.equivalent_seconds(score + 1) < 1500


def synthetic_history(level_at_day, days=84, every_days=2.5, easy_every=4, seed=1):
    rng = random.Random(seed)
    history = []
    stamp = NOW - days * DAY
    index = 0
    while stamp <= NOW - 3600:
        level = level_at_day((stamp - (NOW - days * DAY)) / DAY)
        easy = 8 if index % easy_every == easy_every - 1 else 0
        history.append((stamp, level - rng.expovariate(1 / 1.5) - easy))
        index += 1
        stamp += every_days * DAY
    return history


def test_fitness_trend_detects_improvement_through_easy_days():
    trend = analysis.fitness_trend(synthetic_history(lambda day: 30 + max(0, day - 42) * 4 / 42), NOW)

    assert trend["now"] > trend["then"]
    assert trend["probability"] >= 0.8


def test_fitness_trend_detects_decline():
    trend = analysis.fitness_trend(synthetic_history(lambda day: 34 - max(0, day - 42) * 4 / 42), NOW)

    assert trend["now"] < trend["then"]
    assert trend["probability"] <= 0.2


def test_fitness_trend_stays_undecided_for_a_flat_history():
    trend = analysis.fitness_trend(synthetic_history(lambda day: 32), NOW)

    assert 0.2 < trend["probability"] < 0.8
    assert trend["now"] == pytest.approx(32, abs=1.5)


def test_one_easy_run_does_not_drag_the_level_down():
    history = synthetic_history(lambda day: 33, easy_every=1000)
    baseline = analysis.fitness_trend(history, NOW)
    with_easy = analysis.fitness_trend(history + [(NOW - 3600, 22.0)], NOW)

    assert baseline["now"] - with_easy["now"] < 0.6


def test_fitness_levels_keep_input_order_and_cover_unscored_runs():
    history = synthetic_history(lambda day: 32)
    samples = list(reversed(history)) + [(NOW - 2 * DAY, None), (NOW + DAY, 40.0)]

    trend = analysis.fitness_trend(samples, NOW)

    assert len(trend["levels"]) == len(samples)
    assert trend["levels"][-1] is None
    assert trend["levels"][-2] == pytest.approx(32, abs=2)
    assert all(level is not None for level in trend["levels"][:-1])


def test_fitness_trend_needs_a_score():
    assert analysis.fitness_trend([(NOW - DAY, None)], NOW) is None
    assert analysis.fitness_trend([], NOW) is None


def test_cardio_load_with_and_without_heart_rate():
    # 35 min at avg HR 164 bpm
    hr_load = analysis.cardio_load(35 * 60, avg_hr=164)
    assert hr_load == pytest.approx(79.6, abs=2.0)

    # 35 min running without HR
    no_hr_run = analysis.cardio_load(35 * 60, avg_hr=None, sport="Running")
    assert no_hr_run == pytest.approx(63.0, abs=1.0)

    # 60 min cycling without HR
    no_hr_cycle = analysis.cardio_load(60 * 60, avg_hr=None, sport="Cycling")
    assert no_hr_cycle == pytest.approx(72.0, abs=1.0)


def test_parse_calisthenics_extracts_reps_and_load():
    notes = "7 pushup 5 pullup 10 situp"
    reps, load = analysis.parse_calisthenics(notes, lap_count=6)
    assert reps == {"pushups": 42, "pullups": 30, "situps": 60}
    # 42*0.5 + 30*1.5 + 60*0.3 = 21 + 45 + 18 = 84.0
    assert load == pytest.approx(84.0)

    # Singular or varied spelling
    reps_single, _ = analysis.parse_calisthenics("10 push-ups + 5 pull-ups", lap_count=1)
    assert reps_single["pushups"] == 10
    assert reps_single["pullups"] == 5

    # Empty notes
    assert analysis.parse_calisthenics("") == ({}, 0.0)


@pytest.mark.parametrize(
    "notes, lap_count, expected_reps, expected_load",
    [
        ("8 5 10", 5, {"pushups": 40, "pullups": 25, "situps": 50}, 72.5),
        ("7 3 10", 5, {"pushups": 35, "pullups": 15, "situps": 50}, 55.0),
        ("8 3 11", 9, {"pushups": 72, "pullups": 27, "situps": 99}, 106.2),
        (" 8\t3  11\n", 1, {"pushups": 8, "pullups": 3, "situps": 11}, 11.8),
        ("0 0 0", 5, {"pushups": 0, "pullups": 0, "situps": 0}, 0.0),
    ],
)
def test_numeric_circuit_notes_use_push_pull_sit_order_per_lap(
    notes, lap_count, expected_reps, expected_load
):
    reps, load = analysis.parse_calisthenics(notes, lap_count)

    assert reps == expected_reps
    assert load == pytest.approx(expected_load)


@pytest.mark.parametrize(
    "notes", ["8 3", "8 3 11 5", "slept 8 3 11 hours", "2026-11-11", "8 -3 11", "8 3.5 11"]
)
def test_other_numeric_notes_are_not_circuits(notes):
    assert analysis.parse_calisthenics(notes, lap_count=5) == ({}, 0.0)


def test_unknown_lap_count_keeps_reps_per_lap_without_inventing_total_load():
    strain = analysis.workout_strain(1800, 150, "8 3 11", lap_count=None)

    assert strain["reps"] == {"pushups": 8, "pullups": 3, "situps": 11}
    assert strain["repsPerLap"] is True
    assert strain["strengthLoad"] is None
    assert strain["totalLoad"] == strain["cardioLoad"]


def test_exercise_names_without_counts_do_not_invent_repetitions():
    assert analysis.parse_calisthenics("pushups", lap_count=4) == ({}, None)


def test_partially_quantified_strength_notes_preserve_known_load_and_flag_missing_counts():
    strain = analysis.workout_strain(1800, 150, "6 pushups + pull-ups", lap_count=4)

    assert strain["reps"] == {"pushups": 24}
    assert strain["strengthLoad"] == 12.0
    assert strain["strengthLoadIncomplete"] is True
    assert strain["totalLoad"] == pytest.approx(strain["cardioLoad"] + 12.0, abs=0.2)


@pytest.mark.parametrize("notes", ["-3 pushups", "3.5 pushups", "push-ups"])
def test_invalid_or_unspecified_named_counts_remain_unknown(notes):
    assert analysis.parse_calisthenics(notes, lap_count=4) == ({}, None)


def test_explicit_total_repetitions_are_not_multiplied_by_laps():
    reps, load = analysis.parse_calisthenics("total 32 pushups 12 pullups 44 situps", lap_count=4)

    assert reps == {"pushups": 32, "pullups": 12, "situps": 44}
    assert load == pytest.approx(47.2)


@pytest.mark.parametrize("turns, expected", [(2.0, 2), (4.0, 4), (3.5, 3)])
def test_gps_laps_count_closed_courses_through_exercise_stops(circuit_positions, turns, expected):
    assert analysis.estimate_circuit_laps(circuit_positions(turns)) == expected


def test_walking_out_and_back_does_not_add_a_circuit_lap(circuit_positions):
    assert analysis.estimate_circuit_laps(circuit_positions(detour=True)) == 4


def test_duplicate_timestamps_with_small_gps_jitter_do_not_add_laps(circuit_positions):
    points = circuit_positions()
    stamp, latitude, longitude = points[400]
    points.insert(401, (stamp, latitude + 0.00001, longitude))

    assert analysis.estimate_circuit_laps(points) == 4


def test_gps_gap_leaves_lap_count_unknown(circuit_positions):
    points = circuit_positions()
    points[400:] = [(stamp + 60, lat, lon) for stamp, lat, lon in points[400:]]

    assert analysis.estimate_circuit_laps(points) is None


def test_gps_jump_leaves_lap_count_unknown(circuit_positions):
    points = circuit_positions()
    stamp, latitude, longitude = points[400]
    points[400] = (stamp, latitude + 0.01, longitude)

    assert analysis.estimate_circuit_laps(points) is None


def test_conflicting_positions_at_same_timestamp_leave_laps_unknown(circuit_positions):
    points = circuit_positions()
    stamp, latitude, longitude = points[400]
    points.insert(401, (stamp, latitude + 0.001, longitude))

    assert analysis.estimate_circuit_laps(points) is None


def test_out_and_back_and_stationary_gps_noise_do_not_become_laps():
    out_and_back = [
        (NOW + index, 40.0 + meters / 111320, -75.0)
        for index, meters in enumerate(list(range(0, 402, 2)) + list(range(400, -2, -2)))
    ]
    noise = [(NOW + index, 40.0 + (index % 3) * 0.000001, -75.0) for index in range(1000)]

    assert analysis.estimate_circuit_laps(out_and_back) is None
    assert analysis.estimate_circuit_laps(noise) is None


@pytest.mark.parametrize("latitude", [float("nan"), float("inf"), 100.0])
def test_invalid_gps_coordinates_leave_laps_unknown(circuit_positions, latitude):
    points = circuit_positions()
    stamp, _, longitude = points[400]
    points[400] = (stamp, latitude, longitude)

    assert analysis.estimate_circuit_laps(points) is None


def test_insufficient_gps_does_not_turn_running_bouts_into_laps(circuit_positions):
    assert analysis.estimate_circuit_laps([]) is None
    assert analysis.estimate_circuit_laps(circuit_positions(turns=1)) is None


def test_workout_strain_combines_cardio_and_strength():
    strain = analysis.workout_strain(
        duration_seconds=35 * 60,
        avg_hr=147,
        notes="7 pushup 5 pullup 10 situp",
        lap_count=6,
        sport="Running",
    )
    assert strain["cardioLoad"] > 50
    assert strain["strengthLoad"] == pytest.approx(84.0)
    assert strain["totalLoad"] == pytest.approx(strain["cardioLoad"] + 84.0, abs=0.2)
    assert strain["reps"]["pushups"] == 42


def test_training_capacity_calculates_ctl_and_rate_of_progress():
    # 84 days history: steady 50 load/day building to 100 load/day in last 28 days
    history = []
    start_stamp = NOW - 84 * DAY
    for i in range(84):
        load = 50.0 if i < 56 else 100.0
        history.append((start_stamp + i * DAY, load))

    res = analysis.training_capacity(history, NOW, window_days=28.0)
    assert res is not None
    assert res["now"] > res["then"]
    assert res["rateOfProgress"] > 30.0  # Significant capacity growth


def test_interval_running_with_calisthenics_stops_scores_running_pace():
    # 6 laps of: 120s running at 3.0 m/s (5:33/km) + 60s stopped (0 m/s)
    lap = [(120, 3.0, 82), (60, 0.0, 0)]
    track_pts = track(lap * 6)
    summary = analysis.analyze_track(track_pts)

    assert summary["runSeconds"] == pytest.approx(720, abs=10)
    assert summary["runMeters"] == pytest.approx(2160, abs=50)
    # The pure running score should reflect 3.0 m/s (~5:33/km) over 720s (~30+ VDOT),
    # not diluted by the 60s rest periods down to 2.0 m/s
    assert summary["score"] >= 28.0
    assert summary["runBouts"] == 6
    assert "laps" not in summary


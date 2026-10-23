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

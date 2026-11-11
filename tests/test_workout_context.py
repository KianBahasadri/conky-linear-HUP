import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.error import HTTPError

import pytest

import workout_context as c

BASE = datetime(2026, 11, 1, tzinfo=timezone.utc)


def workout(hour=0.5, longitude=-76.0):
    return {"startTime": BASE + timedelta(hours=hour), "endTime": BASE + timedelta(hours=hour + 1),
            "location": {"latitude": 44, "longitude": longitude}}


def payload():
    hourly = {"time": [(BASE + timedelta(hours=hour)).timestamp() for hour in range(48)]}
    for key, value in zip(c.VARIABLES, (10, 50, 5, 8, 30)):
        hourly[key] = [value] * 48
    hourly["temperature_2m"] = [10 + hour / 10 for hour in range(48)]
    return {"hourly": hourly, "hourly_units": dict(zip(("time",) + c.VARIABLES, ("unixtime",) + c.UNITS))}


@pytest.fixture
def sources(tmp_path, monkeypatch):
    directory = tmp_path / "weight"
    directory.mkdir()
    (directory / "backup.zip").touch()
    reading = {"timestamp": BASE - timedelta(days=1), "value": 200.0, "unit": "LB", "userId": 1}
    monkeypatch.setattr(c.fetch_weight, "read_backup", lambda *_args: [reading])
    return directory, tmp_path / "context.json"


def test_weight_is_matched_as_of_exercise_and_units_are_not_converted_twice():
    readings = [{"timestamp": BASE - timedelta(hours=1), "value": 200.0, "unit": "LB"},
                {"timestamp": BASE + timedelta(hours=1), "value": 100.0, "unit": "LB"}]
    result = c.weight_context(readings, BASE.timestamp())
    assert result["available"] and result["value"] == 200
    assert result["valueKg"] == pytest.approx(90.718, abs=0.001)
    assert result["medianKg"] == pytest.approx(90.718, abs=0.001)
    assert result["sampleCount"] == 1 and result["ageDays"] > 0


@pytest.mark.parametrize("age, stale, available", [(7, False, True), (8, False, False), (1, True, False)])
def test_stale_or_old_weights_do_not_qualify_for_performance_comparisons(age, stale, available):
    result = c.weight_context([{"timestamp": BASE - timedelta(days=age), "value": 94, "unit": "KG"}], BASE.timestamp(), stale)
    assert result["available"] is available


def test_future_and_invalid_weights_remain_unknown():
    assert not c.weight_context([{"timestamp": BASE + timedelta(hours=1), "value": 94, "unit": "KG"}], BASE.timestamp())["available"]
    assert not c.weight_context([{"timestamp": BASE, "value": float("nan"), "unit": "KG"}], BASE.timestamp())["available"]


def test_hourly_weather_is_time_weighted_in_utc_including_dst_day():
    result = c.weather_context(workout(), {"hourly": c._validate_hourly(payload()), "retrievedAt": BASE.isoformat()})
    assert result["available"] and result["estimated"]
    assert result["temperatureC"] == pytest.approx(10.1)
    assert result["humidityPercent"] == 50 and result["model"] == "ecmwf_ifs"


@pytest.mark.parametrize("broken", ["units", "short_array", "duplicate_hour", "misaligned_hour", "numeric_string", "nonfinite", "missing_variable"])
def test_malformed_weather_response_is_rejected(broken):
    data = payload()
    if broken == "units":
        data["hourly_units"]["temperature_2m"] = "°F"
    elif broken == "short_array":
        data["hourly"]["temperature_2m"].pop()
    elif broken == "duplicate_hour":
        data["hourly"]["time"][1] = data["hourly"]["time"][0]
    elif broken == "misaligned_hour":
        data["hourly"]["time"] = [stamp + 1 for stamp in data["hourly"]["time"]]
    elif broken == "numeric_string":
        data["hourly"]["temperature_2m"][0] = "10"
    elif broken == "nonfinite":
        data["hourly"]["temperature_2m"][0] = float("nan")
    else:
        del data["hourly"]["dew_point_2m"]
    with pytest.raises(ValueError):
        c._validate_hourly(data)


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), 999])
def test_missing_or_bad_weather_cannot_become_a_comparison_adjustment(value):
    data = payload()["hourly"]
    data["temperature_2m"][1] = value
    assert not c.weather_context(workout(), {"hourly": data})["available"]


def test_context_cache_is_reused_and_failed_weight_upload_is_marked_stale(sources, monkeypatch):
    directory, path = sources
    calls = []
    def request(params):
        calls.append(params)
        return payload()
    rows, meta = c.enrich([workout()], directory.parent, path, BASE + timedelta(days=2), weight_dir=directory, request=request)
    assert rows[0]["context"]["weight"]["available"] and rows[0]["context"]["weather"]["available"]
    assert len(calls) == 1 and calls[0]["timezone"] == "UTC" and calls[0]["timeformat"] == "unixtime"
    c.enrich([workout()], directory.parent, path, BASE + timedelta(days=2, hours=1), weight_dir=directory, request=request)
    assert len(calls) == 1
    def broken(*_args):
        raise ValueError("Incomplete upload")
    monkeypatch.setattr(c.fetch_weight, "read_backup", broken)
    rows, _ = c.enrich([workout()], directory.parent, path, BASE + timedelta(days=2, hours=2), weight_dir=directory, request=request)
    weight = rows[0]["context"]["weight"]
    assert weight["stale"] and not weight["available"] and weight["value"] == 200.0


def test_weather_failure_preserves_workouts_and_retries_are_bounded(sources):
    directory, path = sources
    calls = []
    def failed(params):
        calls.append(params)
        raise TimeoutError("Provider unavailable")
    rows, meta = c.enrich([workout()], directory.parent, path, BASE + timedelta(days=2), weight_dir=directory, request=failed)
    assert len(rows) == 1 and not rows[0]["context"]["weather"]["available"]
    assert meta["weatherPending"] == 1 and len(calls) == 1
    c.enrich([workout()], directory.parent, path, BASE + timedelta(days=2, minutes=1), weight_dir=directory, request=failed)
    assert len(calls) == 1


@pytest.mark.parametrize("http_date", [False, True])
def test_rate_limit_honors_retry_after_across_weather_tiles(sources, http_date):
    directory, path = sources
    now = BASE + timedelta(days=2)
    retry = format_datetime(now + timedelta(hours=2), usegmt=True) if http_date else "7200"
    calls = []
    def limited(params):
        calls.append(params)
        raise HTTPError(c.ENDPOINT, 429, "Too Many Requests", {"Retry-After": retry}, None)
    records = [workout(), workout(longitude=-77)]
    rows, meta = c.enrich(records, directory.parent, path, now, weight_dir=directory, request=limited)
    assert len(rows) == 2 and meta["requests"] == len(calls) == 1
    assert json.loads(path.read_text())["weatherRetryAfter"] == (now + timedelta(hours=2)).timestamp()
    c.enrich(records, directory.parent, path, now + timedelta(hours=1), weight_dir=directory, request=limited)
    assert len(calls) == 1
    c.enrich(records, directory.parent, path, now + timedelta(hours=2), weight_dir=directory, request=limited)
    assert len(calls) == 2


def test_provider_failure_keeps_already_retrieved_history(sources):
    directory, path = sources
    now = BASE + timedelta(days=4)
    c.enrich([workout()], directory.parent, path, now, weight_dir=directory, request=lambda _: payload())
    def failed(_):
        raise TimeoutError()
    rows, _ = c.enrich([workout(), workout(hour=60)], directory.parent, path, now + timedelta(hours=7), weight_dir=directory, request=failed)
    assert rows[0]["context"]["weather"]["available"]
    assert not rows[1]["context"]["weather"]["available"]


def test_backfill_request_budget_does_not_block_all_history_on_startup(sources):
    directory, path = sources
    calls = []
    def request(params):
        calls.append(params)
        return payload()
    records = [workout(longitude=-76 - index / 100) for index in range(4)]
    rows, meta = c.enrich(records, directory.parent, path, BASE + timedelta(days=2), weight_dir=directory, max_requests=2, request=request)
    assert len(calls) == 2 and meta["weatherPending"] == 2
    rows, meta = c.enrich(records, directory.parent, path, BASE + timedelta(days=2), weight_dir=directory, max_requests=2, request=request)
    assert len(calls) == 4 and meta["weatherPending"] == 0


def test_corrupt_cache_and_missing_gps_do_not_generate_zero_weather(sources):
    directory, path = sources
    path.write_text("{incomplete")
    record = workout()
    del record["location"]
    rows, meta = c.enrich([record], directory.parent, path, BASE + timedelta(days=2), weight_dir=directory,
                          request=lambda _: pytest.fail("Missing GPS must not send a weather request"))
    assert not rows[0]["context"]["weather"]["available"]
    assert "temperatureC" not in rows[0]["context"]["weather"] and meta["weatherPending"] == 0

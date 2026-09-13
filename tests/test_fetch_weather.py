import copy
import json
from datetime import date, timedelta

import pytest

import fetch_weather as weather


@pytest.fixture
def thermometer_weather():
    today = date(2026, 9, 13)
    dates = [(today - timedelta(days=days)).isoformat() for days in range(7, -1, -1)]
    return {
        "current": {"time": "2026-09-13T14:00", "temperature_2m": 23.1, "weather_code": 2},
        "current_units": {"temperature_2m": "°C"},
        "daily_units": {"temperature_2m_mean": "°C"},
        "utc_offset_seconds": -14400,
        "daily": {"time": dates, "temperature_2m_mean": [18, 20, 22, 21, 23, 24, 19, 100],
                  "sunrise": [day + "T06:54" for day in dates],
                  "sunset": [day + "T19:31" for day in dates]},
    }


def test_thermometer_uses_seven_complete_local_days_and_todays_sun_times(thermometer_weather):
    thermometer_weather["daily"]["sunrise"][0] = "2026-09-06T06:46"
    status = weather.normalize_thermometer(thermometer_weather)
    assert status["ok"]
    assert status["temperatureCelsius"] == 23.1
    assert [day["date"] for day in status["previousDays"]] == [
        "2026-09-06", "2026-09-07", "2026-09-08", "2026-09-09",
        "2026-09-10", "2026-09-11", "2026-09-12"]
    assert sum(day["temperatureCelsius"] for day in status["previousDays"]) / 7 == 21
    assert status["sunriseMinute"] == 414
    assert status["sunsetMinute"] == 1171
    assert status["utcOffsetSeconds"] == -14400
    assert status["condition"] == "cloudy"


@pytest.mark.parametrize("bad", [None, float("nan"), float("inf"), True])
@pytest.mark.parametrize("source", ["current", "history"])
def test_thermometer_rejects_invalid_readings(thermometer_weather, source, bad):
    if source == "current":
        thermometer_weather["current"]["temperature_2m"] = bad
    else:
        thermometer_weather["daily"]["temperature_2m_mean"][3] = bad
    assert weather.normalize_thermometer(thermometer_weather)["ok"] is False


@pytest.mark.parametrize("fault", ["missing_day", "duplicate_day", "short_week", "wrong_date", "reversed_sun", "units", "offset"])
def test_thermometer_rejects_incomplete_history_or_local_events(thermometer_weather, fault):
    daily = thermometer_weather["daily"]
    if fault == "missing_day":
        daily["time"][2] = "2026-09-01"
    elif fault == "duplicate_day":
        daily["time"][2] = daily["time"][1]
    elif fault == "short_week":
        daily["temperature_2m_mean"] = [18, 20]
    elif fault == "wrong_date":
        daily["sunrise"][-1] = "2026-09-12T06:54"
    elif fault == "reversed_sun":
        daily["sunrise"][-1] = "2026-09-13T20:00"
    elif fault == "units":
        thermometer_weather["daily_units"]["temperature_2m_mean"] = "°F"
    else:
        thermometer_weather["utc_offset_seconds"] = None
    assert weather.normalize_thermometer(thermometer_weather)["ok"] is False


@pytest.mark.parametrize("code,condition", [(0, "clear"), (1, "clear"), (45, "cloudy"),
                                           (61, "rain"), (95, "rain"), (73, "snow"), (86, "snow")])
def test_thermometer_maps_weather_to_reference_conditions(thermometer_weather, code, condition):
    thermometer_weather["current"]["weather_code"] = code
    assert weather.normalize_thermometer(thermometer_weather)["condition"] == condition


def test_thermometer_stays_in_celsius_when_legacy_readouts_use_fahrenheit(thermometer_weather, monkeypatch):
    monkeypatch.setenv("WEATHER_UNITS", "imperial")
    original = copy.deepcopy(thermometer_weather)
    converted = weather.weather_for_display(thermometer_weather, weather.units_for({}))
    assert converted["current"]["temperature_2m"] == pytest.approx(73.58)
    assert thermometer_weather == original
    assert weather.normalize_thermometer(thermometer_weather)["temperatureCelsius"] == 23.1


def test_forecast_requests_history_in_celsius_without_expanding_air_history(monkeypatch):
    calls = []
    monkeypatch.setattr(weather, "request_json", lambda url, params, timeout: calls.append((url, params)) or {})
    monkeypatch.setenv("WEATHER_UNITS", "imperial")
    weather.fetch_forecasts({"latitude": 40, "longitude": -74}, weather.units_for({}), 10)
    forecast, air = calls
    assert forecast[1]["temperature_unit"] == "celsius"
    assert forecast[1]["past_days"] == 7
    assert "temperature_2m_mean" in forecast[1]["daily"]
    assert "past_days" not in air[1]


def test_configured_coordinates_require_both_values(monkeypatch):
    monkeypatch.setenv("WEATHER_LATITUDE", "40.7")
    monkeypatch.delenv("WEATHER_LONGITUDE", raising=False)

    with pytest.raises(ValueError, match="Set both"):
        weather.configured_coordinates()


def test_configured_coordinates_validate_range(monkeypatch):
    monkeypatch.setenv("WEATHER_LATITUDE", "91")
    monkeypatch.setenv("WEATHER_LONGITUDE", "-74")

    with pytest.raises(ValueError, match="between -90 and 90"):
        weather.configured_coordinates()


def test_units_auto_uses_ip_country(monkeypatch):
    monkeypatch.setenv("WEATHER_UNITS", "auto")

    assert weather.units_for({"countryCode": "US"})["name"] == "imperial"
    assert weather.units_for({"countryCode": "DE"})["name"] == "metric"


def test_score_run_marks_good_and_dangerous_conditions():
    good = weather.score_run(
        {
            "apparentTemperature": 62,
            "windGust": 8,
            "aqi": 25,
            "precipitationProbability": 5,
            "uvIndex": 2,
            "humidityPercent": 50,
            "weatherCode": 1,
        }
    )
    dangerous = weather.score_run(
        {
            "apparentTemperature": 99,
            "windGust": 44,
            "aqi": 175,
            "precipitationProbability": 90,
            "uvIndex": 9,
            "humidityPercent": 88,
            "weatherCode": 95,
        }
    )

    assert good == {
        "score": 100,
        "status": "GREAT",
        "color": "39ff88",
        "advice": "Excellent conditions for a run",
    }
    assert dangerous["score"] == 0
    assert dangerous["status"] == "WAIT"
    assert "Thunderstorms" in dangerous["advice"]


def test_normalize_status_combines_weather_air_and_best_window(monkeypatch):
    monkeypatch.setenv("WEATHER_UNITS", "imperial")
    location = {
        "latitude": 40.7,
        "longitude": -74.0,
        "label": "New York, NY",
        "countryCode": "US",
        "source": "location",
    }
    units = weather.units_for(location)
    weather_payload = {
        "current": {
            "temperature_2m": 84.2,
            "relative_humidity_2m": 66,
            "apparent_temperature": 88.1,
            "weather_code": 2,
            "wind_speed_10m": 9.2,
            "wind_direction_10m": 225,
            "wind_gusts_10m": 17.4,
            "visibility": 16093.44,
            "is_day": 1,
        },
        "hourly": {
            "time": ["2026-07-19T15:00", "2026-07-19T16:00"],
            "temperature_2m": [84, 81],
            "relative_humidity_2m": [66, 60],
            "apparent_temperature": [88, 83],
            "precipitation_probability": [30, 5],
            "weather_code": [2, 1],
            "wind_speed_10m": [9, 7],
            "wind_gusts_10m": [17, 12],
            "visibility": [16093, 16093],
        },
        "daily": {
            "sunrise": ["2026-07-19T05:42"],
            "sunset": ["2026-07-19T20:23"],
        },
    }
    air_payload = {
        "current": {"us_aqi": 42, "pm2_5": 8.5, "uv_index": 6.2},
        "hourly": {
            "time": ["2026-07-19T15:00", "2026-07-19T16:00"],
            "us_aqi": [42, 35],
            "pm2_5": [8.5, 7.1],
            "uv_index": [6.2, 4.0],
        },
    }

    status = weather.normalize_status(location, units, weather_payload, air_payload)

    assert status["location"] == "New York, NY"
    assert status["temperature"] == 84
    assert status["condition"] == "Partly cloudy"
    assert status["aqi"] == 42
    assert status["aqiLabel"] == "Good"
    assert status["windDirection"] == "SW"
    assert status["visibility"] == 10.0
    assert status["sunset"] == "8:23 PM"
    assert status["bestWindow"]["label"] == "4 PM"
    assert status["attribution"] == "Open-Meteo / CAMS"


def test_normalize_status_rejects_missing_current_aqi(monkeypatch):
    location = {
        "latitude": 40.7,
        "longitude": -74.0,
        "label": "New York, NY",
        "countryCode": "US",
        "source": "location",
    }
    units = weather.units_for(location)
    weather_payload = {
        "current": {
            "temperature_2m": 70,
            "relative_humidity_2m": 50,
            "apparent_temperature": 70,
            "weather_code": 1,
            "wind_speed_10m": 5,
            "wind_direction_10m": 180,
            "wind_gusts_10m": 8,
            "visibility": 16000,
            "is_day": 1,
        }
    }

    with pytest.raises(ValueError, match="us_aqi"):
        weather.normalize_status(
            location,
            units,
            weather_payload,
            {"current": {"pm2_5": 5, "uv_index": 2}},
        )


def test_request_json_reports_safe_response_metadata(monkeypatch):
    class Response:
        status = 502
        headers = {"Content-Type": "text/html; charset=utf-8"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"<html>gateway error</html>"

    monkeypatch.setattr(weather.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())

    with pytest.raises(
        ValueError,
        match=r"api\.open-meteo\.com returned invalid JSON .*HTTP 502.*text/html",
    ):
        weather.request_json("https://api.open-meteo.com/v1/forecast?secret=hidden")


def test_hourly_rows_drop_weather_hours_without_matching_air_quality():
    weather_payload = {
        "hourly": {
            "time": ["2026-07-19T15:00"],
            "temperature_2m": [84],
            "apparent_temperature": [88],
            "precipitation_probability": [30],
            "weather_code": [2],
            "wind_speed_10m": [9],
            "wind_gusts_10m": [17],
            "relative_humidity_2m": [66],
            "visibility": [16093],
        }
    }

    assert weather.hourly_rows(weather_payload, {"hourly": {"time": []}}) == []


def test_write_error_keeps_last_successful_cache(monkeypatch, tmp_path):
    status_path = tmp_path / "weather-status.json"
    status_path.write_text(json.dumps({"ok": True, "temperature": 70}), encoding="utf-8")
    monkeypatch.setattr(weather, "STATUS_PATH", status_path)
    monkeypatch.setattr(weather, "log_event", lambda _message: None)

    weather.write_error("network down")

    cached = json.loads(status_path.read_text(encoding="utf-8"))
    assert cached["ok"] is True
    assert cached["stale"] is True
    assert cached["error"] == "network down"

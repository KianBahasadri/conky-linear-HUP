import json

import pytest

import fetch_weather as weather


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


def test_normalize_status_combines_weather_air_and_best_window():
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

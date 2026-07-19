#!/usr/bin/env python3
import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
STATUS_PATH = CACHE_DIR / "weather-status.json"
LOG_PATH = CACHE_DIR / "conky-weather.log"

IP_LOCATION_URL = "https://ipapi.co/json/"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
USER_AGENT = "conky-linear-HUP/1.0"


log_event = common.make_logger(LOG_PATH, "fetch_weather")
atomic_write_json = common.atomic_write_json


WEATHER_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Icy fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light showers",
    81: "Showers",
    82: "Heavy showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorms",
    96: "Storms with hail",
    99: "Storms with hail",
}


def request_json(url, params=None, timeout=10):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_coordinate(value, name, minimum, maximum):
    try:
        coordinate = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a number") from error
    if not math.isfinite(coordinate) or not minimum <= coordinate <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return coordinate


def configured_coordinates():
    latitude_text = os.environ.get("WEATHER_LATITUDE", "").strip()
    longitude_text = os.environ.get("WEATHER_LONGITUDE", "").strip()
    if not latitude_text and not longitude_text:
        return None
    if not latitude_text or not longitude_text:
        raise ValueError("Set both WEATHER_LATITUDE and WEATHER_LONGITUDE")

    latitude = parse_coordinate(latitude_text, "WEATHER_LATITUDE", -90, 90)
    longitude = parse_coordinate(longitude_text, "WEATHER_LONGITUDE", -180, 180)
    label = os.environ.get("WEATHER_LOCATION_LABEL", "").strip() or "Configured location"
    return {
        "latitude": latitude,
        "longitude": longitude,
        "label": label,
        "countryCode": "",
        "source": "coordinates",
    }


def geocode_location(location, timeout):
    payload = request_json(
        GEOCODING_URL,
        {"name": location, "count": 1, "language": "en", "format": "json"},
        timeout,
    )
    results = payload.get("results") or []
    if not results:
        raise ValueError(f"No location matched WEATHER_LOCATION={location}")
    result = results[0]
    name = str(result.get("name") or location)
    region = str(result.get("admin1") or result.get("country") or "")
    label = ", ".join(part for part in (name, region) if part)
    return {
        "latitude": parse_coordinate(result.get("latitude"), "latitude", -90, 90),
        "longitude": parse_coordinate(result.get("longitude"), "longitude", -180, 180),
        "label": os.environ.get("WEATHER_LOCATION_LABEL", "").strip() or label,
        "countryCode": str(result.get("country_code") or "").upper(),
        "source": "location",
    }


def locate_by_ip(timeout):
    payload = request_json(IP_LOCATION_URL, timeout=timeout)
    if payload.get("error"):
        raise ValueError(str(payload.get("reason") or "IP location lookup failed"))
    city = str(payload.get("city") or "").strip()
    region = str(payload.get("region_code") or payload.get("region") or "").strip()
    country = str(payload.get("country_code") or payload.get("country") or "").upper()
    label = ", ".join(part for part in (city, region) if part) or "Approximate location"
    return {
        "latitude": parse_coordinate(payload.get("latitude"), "latitude", -90, 90),
        "longitude": parse_coordinate(payload.get("longitude"), "longitude", -180, 180),
        "label": os.environ.get("WEATHER_LOCATION_LABEL", "").strip() or label,
        "countryCode": country,
        "source": "ip",
    }


def resolve_location(timeout):
    configured = configured_coordinates()
    if configured:
        return configured

    location = os.environ.get("WEATHER_LOCATION", "").strip()
    if location:
        return geocode_location(location, timeout)

    return locate_by_ip(timeout)


def units_for(location):
    units = os.environ.get("WEATHER_UNITS", "imperial").strip().lower()
    if units == "auto":
        units = "imperial" if location.get("countryCode") == "US" else "metric"
    if units not in {"imperial", "metric"}:
        raise ValueError("WEATHER_UNITS must be imperial, metric, or auto")
    if units == "imperial":
        return {
            "name": units,
            "temperature": "fahrenheit",
            "wind": "mph",
            "precipitation": "inch",
            "temperatureSymbol": "F",
            "windSymbol": "mph",
            "visibilityDivisor": 1609.344,
            "visibilitySymbol": "mi",
        }
    return {
        "name": units,
        "temperature": "celsius",
        "wind": "kmh",
        "precipitation": "mm",
        "temperatureSymbol": "C",
        "windSymbol": "km/h",
        "visibilityDivisor": 1000,
        "visibilitySymbol": "km",
    }


def fetch_forecasts(location, units, timeout):
    base_params = {
        "latitude": location["latitude"],
        "longitude": location["longitude"],
        "timezone": "auto",
        "forecast_hours": 8,
    }
    weather_params = {
        **base_params,
        "temperature_unit": units["temperature"],
        "wind_speed_unit": units["wind"],
        "precipitation_unit": units["precipitation"],
        "current": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation",
                "weather_code",
                "cloud_cover",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "visibility",
                "is_day",
            ]
        ),
        "hourly": ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "apparent_temperature",
                "precipitation_probability",
                "weather_code",
                "wind_speed_10m",
                "wind_gusts_10m",
                "visibility",
            ]
        ),
        "daily": "sunrise,sunset",
        "forecast_days": 1,
    }
    air_params = {
        **base_params,
        "current": "us_aqi,pm2_5,uv_index",
        "hourly": "us_aqi,pm2_5,uv_index",
    }
    return (
        request_json(WEATHER_URL, weather_params, timeout),
        request_json(AIR_QUALITY_URL, air_params, timeout),
    )


def as_number(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def rounded(value, digits=0):
    number = as_number(value)
    return round(number, digits) if digits else int(round(number))


def compass_direction(degrees):
    directions = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    return directions[int((as_number(degrees) + 22.5) // 45) % 8]


def aqi_details(value):
    aqi = rounded(value)
    if aqi <= 50:
        return aqi, "Good", "39ff88"
    if aqi <= 100:
        return aqi, "Moderate", "facc15"
    if aqi <= 150:
        return aqi, "Sensitive", "fb923c"
    if aqi <= 200:
        return aqi, "Unhealthy", "f87171"
    if aqi <= 300:
        return aqi, "Very unhealthy", "c084fc"
    return aqi, "Hazardous", "f472b6"


def uv_label(value):
    uv = as_number(value)
    if uv < 3:
        return "Low"
    if uv < 6:
        return "Moderate"
    if uv < 8:
        return "High"
    if uv < 11:
        return "Very high"
    return "Extreme"


def score_run(conditions, imperial=True):
    apparent = as_number(conditions.get("apparentTemperature"))
    gust = as_number(conditions.get("windGust"))
    if not imperial:
        apparent = apparent * 9 / 5 + 32
        gust = gust / 1.609344

    aqi = as_number(conditions.get("aqi"))
    rain = as_number(conditions.get("precipitationProbability"))
    uv = as_number(conditions.get("uvIndex"))
    humidity = as_number(conditions.get("humidityPercent"))
    weather_code = int(as_number(conditions.get("weatherCode")))
    score = 100
    reasons = []

    if aqi > 300:
        score -= 90
        reasons.append((100, "Hazardous air quality"))
    elif aqi > 200:
        score -= 75
        reasons.append((90, "Very unhealthy air"))
    elif aqi > 150:
        score -= 55
        reasons.append((80, "Unhealthy air quality"))
    elif aqi > 100:
        score -= 35
        reasons.append((65, "Sensitive runners: limit exertion"))
    elif aqi > 50:
        score -= 10
        reasons.append((25, "Air quality is moderate"))

    if apparent > 105 or apparent < 0:
        score -= 80
        reasons.append((95, "Dangerous apparent temperature"))
    elif apparent > 95:
        score -= 45
        reasons.append((75, "Heat stress risk"))
    elif apparent < 20:
        score -= 45
        reasons.append((75, "Bitter cold; cover exposed skin"))
    elif apparent > 90:
        score -= 25
        reasons.append((55, "Hot: slow down and hydrate"))
    elif apparent < 32:
        score -= 25
        reasons.append((55, "Freezing: dress in warm layers"))
    elif apparent > 85:
        score -= 10
        reasons.append((30, "Warm: carry water"))
    elif apparent < 40:
        score -= 8
        reasons.append((25, "Chilly: add a light layer"))

    if weather_code >= 95:
        score -= 90
        reasons.append((100, "Thunderstorms: run indoors"))
    elif weather_code in {65, 67, 75, 82, 86}:
        score -= 45
        reasons.append((70, "Heavy precipitation"))
    elif weather_code in {56, 57, 66, 71, 73, 77, 85}:
        score -= 30
        reasons.append((60, "Slippery conditions possible"))

    if rain >= 80:
        score -= 30
        reasons.append((50, "Rain is very likely"))
    elif rain >= 60:
        score -= 20
        reasons.append((40, "Rain is likely"))
    elif rain >= 35:
        score -= 10
        reasons.append((20, "A shower is possible"))

    if gust >= 40:
        score -= 45
        reasons.append((75, "Dangerous wind gusts"))
    elif gust >= 30:
        score -= 25
        reasons.append((50, "Strong gusts"))
    elif gust >= 22:
        score -= 10
        reasons.append((25, "Breezy on exposed routes"))

    if uv >= 11:
        score -= 20
        reasons.append((45, "Extreme UV: avoid midday sun"))
    elif uv >= 8:
        score -= 12
        reasons.append((35, "Very high UV: use sun protection"))
    elif uv >= 6:
        score -= 5
        reasons.append((20, "Use sun protection"))

    if humidity >= 85 and apparent >= 75:
        score -= 8
        reasons.append((20, "Humid: hydrate and ease your pace"))

    score = max(0, min(100, score))
    if score >= 85:
        status, color, default_advice = "GREAT", "39ff88", "Excellent conditions for a run"
    elif score >= 70:
        status, color, default_advice = "GOOD", "00e5ff", "Good conditions for a run"
    elif score >= 40:
        status, color, default_advice = "CAUTION", "facc15", "Adjust your route or pace"
    else:
        status, color, default_advice = "WAIT", "f87171", "Consider running indoors"

    reasons.sort(reverse=True)
    advice = "; ".join(reason for _priority, reason in reasons[:2]) or default_advice
    return {"score": score, "status": status, "color": color, "advice": advice}


def hourly_rows(weather, air):
    weather_hourly = weather.get("hourly") or {}
    air_hourly = air.get("hourly") or {}
    air_by_time = {}
    for index, time_value in enumerate(air_hourly.get("time") or []):
        air_by_time[time_value] = {
            key: (air_hourly.get(key) or [None] * (index + 1))[index]
            if index < len(air_hourly.get(key) or [])
            else None
            for key in ("us_aqi", "pm2_5", "uv_index")
        }

    rows = []
    times = weather_hourly.get("time") or []
    for index, time_value in enumerate(times):
        def weather_value(key):
            values = weather_hourly.get(key) or []
            return values[index] if index < len(values) else None

        air_values = air_by_time.get(time_value, {})
        rows.append(
            {
                "time": time_value,
                "temperature": rounded(weather_value("temperature_2m")),
                "apparentTemperature": rounded(weather_value("apparent_temperature")),
                "precipitationProbability": rounded(weather_value("precipitation_probability")),
                "weatherCode": rounded(weather_value("weather_code")),
                "windSpeed": rounded(weather_value("wind_speed_10m")),
                "windGust": rounded(weather_value("wind_gusts_10m")),
                "humidityPercent": rounded(weather_value("relative_humidity_2m")),
                "visibility": as_number(weather_value("visibility")),
                "aqi": rounded(air_values.get("us_aqi")),
                "pm25": rounded(air_values.get("pm2_5"), 1),
                "uvIndex": rounded(air_values.get("uv_index"), 1),
            }
        )
    return rows


def format_hour(time_value):
    try:
        hour = datetime.fromisoformat(time_value).hour
    except (TypeError, ValueError):
        return "Later"
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"{display_hour} {suffix}"


def format_sun_time(time_value):
    if not time_value:
        return "--"
    try:
        parsed = datetime.fromisoformat(time_value)
    except ValueError:
        return "--"
    suffix = "AM" if parsed.hour < 12 else "PM"
    display_hour = parsed.hour % 12 or 12
    return f"{display_hour}:{parsed.minute:02d} {suffix}"


def best_run_window(rows, units):
    if not rows:
        return {"label": "Now", "detail": "Forecast unavailable", "score": 0}
    scored = [(score_run(row, units["name"] == "imperial"), row) for row in rows[:7]]
    best_index = max(range(len(scored)), key=lambda index: scored[index][0]["score"])
    best_score, best_row = scored[best_index]
    label = "Now" if best_index == 0 else format_hour(best_row.get("time"))
    detail = (
        f"{best_row['temperature']}{units['temperatureSymbol']} / "
        f"rain {best_row['precipitationProbability']}% / AQI {best_row['aqi']}"
    )
    return {"label": label, "detail": detail, "score": best_score["score"]}


def normalize_status(location, units, weather, air):
    current = weather.get("current") or {}
    air_current = air.get("current") or {}
    rows = hourly_rows(weather, air)
    first_hour = rows[0] if rows else {}
    aqi, aqi_label, aqi_color = aqi_details(air_current.get("us_aqi"))
    weather_code = rounded(current.get("weather_code"))
    visibility = as_number(current.get("visibility")) / units["visibilityDivisor"]
    condition = {
        "apparentTemperature": rounded(current.get("apparent_temperature")),
        "precipitationProbability": rounded(first_hour.get("precipitationProbability")),
        "weatherCode": weather_code,
        "windGust": rounded(current.get("wind_gusts_10m")),
        "humidityPercent": rounded(current.get("relative_humidity_2m")),
        "aqi": aqi,
        "uvIndex": rounded(air_current.get("uv_index"), 1),
    }
    run = score_run(condition, units["name"] == "imperial")
    daily = weather.get("daily") or {}
    sunrise_values = daily.get("sunrise") or []
    sunset_values = daily.get("sunset") or []

    return {
        "ok": True,
        "stale": False,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "location": location["label"],
        "locationSource": location["source"],
        "temperature": rounded(current.get("temperature_2m")),
        "temperatureUnit": units["temperatureSymbol"],
        "apparentTemperature": condition["apparentTemperature"],
        "condition": WEATHER_DESCRIPTIONS.get(weather_code, "Unknown conditions"),
        "weatherCode": weather_code,
        "isDay": bool(rounded(current.get("is_day"))),
        "aqi": aqi,
        "aqiLabel": aqi_label,
        "aqiColor": aqi_color,
        "pm25": rounded(air_current.get("pm2_5"), 1),
        "uvIndex": condition["uvIndex"],
        "uvLabel": uv_label(condition["uvIndex"]),
        "humidityPercent": condition["humidityPercent"],
        "precipitationProbability": condition["precipitationProbability"],
        "windSpeed": rounded(current.get("wind_speed_10m")),
        "windGust": condition["windGust"],
        "windDirection": compass_direction(current.get("wind_direction_10m")),
        "windUnit": units["windSymbol"],
        "visibility": round(visibility, 1),
        "visibilityUnit": units["visibilitySymbol"],
        "sunrise": format_sun_time(sunrise_values[0] if sunrise_values else ""),
        "sunset": format_sun_time(sunset_values[0] if sunset_values else ""),
        "runScore": run["score"],
        "runStatus": run["status"],
        "runColor": run["color"],
        "runAdvice": run["advice"],
        "bestWindow": best_run_window(rows, units),
        "attribution": "Open-Meteo / CAMS",
    }


def write_error(message):
    old_status = None
    try:
        old_status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass

    if old_status and old_status.get("ok"):
        old_status["stale"] = True
        old_status["error"] = message
        atomic_write_json(STATUS_PATH, old_status)
    else:
        atomic_write_json(
            STATUS_PATH,
            {
                "ok": False,
                "stale": False,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "error": message,
            },
        )
    log_event(f"error: {message}")


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    common.load_env()
    try:
        timeout = float(os.environ.get("WEATHER_TIMEOUT_SECONDS", "10"))
        location = resolve_location(timeout)
        units = units_for(location)
        log_event(
            f"querying location={location['label']} source={location['source']} "
            f"latitude={location['latitude']:.3f} longitude={location['longitude']:.3f}"
        )
        weather, air = fetch_forecasts(location, units, timeout)
        status = normalize_status(location, units, weather, air)
    except Exception as error:
        write_error(f"Weather fetch failed: {error}")
        return 1

    atomic_write_json(STATUS_PATH, status)
    log_event(
        f"completed fetch location={status['location']} temperature={status['temperature']} "
        f"aqi={status['aqi']} run_status={status['runStatus']}"
    )
    print(json.dumps(status, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

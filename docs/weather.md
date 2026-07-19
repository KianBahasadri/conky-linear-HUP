# Weather and running overlay

The bottom-right panel combines current weather and air quality with running-specific guidance. It shows temperature and apparent temperature, weather, U.S. AQI, rain probability, wind and gusts, humidity, UV, visibility, sunset, a current run score, and the best window in the next several hours.

Weather forecasts come from Open-Meteo. Air-quality data comes from the Copernicus Atmosphere Monitoring Service (CAMS) through Open-Meteo. The panel keeps the last successful result and marks it `STALE` when a refresh fails.

## Location

Location resolution uses the first configured option:

1. `WEATHER_LATITUDE` and `WEATHER_LONGITUDE` for the most accurate local result.
2. `WEATHER_LOCATION` for Open-Meteo city/postal-code geocoding.
3. Public-IP geolocation for a no-configuration, city-level approximation. A `~` after the location label identifies this mode.

Public-IP location is inherently approximate. Set coordinates in `.env` if the detected city is wrong or conditions vary significantly across your area.

## Run score

The guidance weighs apparent temperature, AQI, rain probability, weather hazards, wind gusts, UV, and hot-weather humidity. It is a quick planning aid, not a health or safety alert. The next-hours forecast is scored with the same rules to select the displayed best running window.

Set `WEATHER_OVERLAY_ENABLED=0` to disable the panel and its fetch loop. Placement, units, request timeout, and refresh cadence are documented in [Configuration](configuration.md).

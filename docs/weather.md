# Weather and running overlay

The bottom-right panel combines current weather and air quality with a training summary. It shows temperature and apparent temperature, weather, U.S. AQI, UV, and sunset. A training section summarizes workouts uploaded from the phone: last workout (distance, duration, pace, heart rate or cadence when recorded) and rolling 7-day distance/time/runs.

A weight section follows the running stats. It shows the latest weigh-in and
the signed change from the preceding weigh-in, with the measurement date, age,
and comparison date underneath. A first reading has no change value. Both
metrics stay neutral: weight gain and loss do not imply good or bad status.
The [phone data source](workout-data-source.md#weight-backups-from-openscale)
describes how openScale backups are read. An unreadable or incomplete upload
keeps the last successful weight summary and marks it `Stale`; without a
successful reading, the section shows an explanatory placeholder.

Weather forecasts come from Open-Meteo. Air-quality data comes from the Copernicus Atmosphere Monitoring Service (CAMS) through Open-Meteo. The panel keeps the last successful result and marks it `STALE` when a refresh fails. Partial responses missing valid current weather or air-quality fields are treated as failed refreshes instead of being rendered as zero-valued, reassuring conditions.

## Location

Location resolution uses the first configured option:

1. `WEATHER_LATITUDE` and `WEATHER_LONGITUDE` for the most accurate local result.
2. `WEATHER_LOCATION` for Open-Meteo city/postal-code geocoding.
3. Public-IP geolocation for a no-configuration, city-level approximation. A `~` after the location label identifies this mode.

Public-IP location is inherently approximate. Set coordinates in `.env` if the detected city is wrong or conditions vary significantly across your area.

## Run score

The backend guidance weighs apparent temperature, AQI, rain probability, weather hazards, wind gusts, UV, and hot-weather humidity into a planning score and best-window forecast in the cache.

Set `WEATHER_OVERLAY_ENABLED=0` to disable the panel and its fetch loop. Placement, units, request timeout, and refresh cadence are documented in [Configuration](configuration.md).

## Display

Weather and AQI use neutral metrics. The condition and location share one line,
and a stale cache replaces the location with a caution `Stale`. Feels-like
temperature, UV, and sunset are aligned label-and-value readouts. Training
preserves distance, duration, pace, heart rate/cadence, and weekly totals.
Weight uses the same metric columns and detail typography beneath training.
The full stack fits in a 320px window. When less space is available, whole
sections are packed in order into pages that rotate every 30 seconds, with
`1/2` or `1/3` style page labels. Shared styling and layout belong to the
[Desktop design system](design-system.md).

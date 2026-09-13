# Weather and running overlay

The right rail keeps training and weight below the resource gauges. A separate
thermometer window sits at the bottom left of each monitor.
The former temperature, apparent-temperature, AQI, UV, condition, and location
readouts are removed. Training summarizes workouts uploaded from the phone:
last workout (distance, duration, pace, heart rate or cadence when recorded)
and rolling 7-day distance/time/runs.

A weight section follows the running stats. It shows the latest weigh-in and
the signed change from the preceding weigh-in, with the measurement date, age,
and comparison date underneath. A first reading has no change value. Both
metrics stay neutral: weight gain and loss do not imply good or bad status.
The [phone data source](workout-data-source.md#weight-backups-from-openscale)
describes how openScale backups are read. An unreadable or incomplete upload
keeps the last successful weight summary and marks it `Stale`; without a
successful reading, the section shows an explanatory placeholder.

Weather forecasts come from Open-Meteo. Air-quality data from the Copernicus
Atmosphere Monitoring Service (CAMS) through Open-Meteo remains in the cache
for run guidance. The fetcher keeps the last successful result when a refresh
fails; the thermometer is dimmed and marked `Stale`. Partial responses missing
valid current weather or air-quality fields are treated as failed refreshes.

## Thermometer

`conky/thermometer-component.lua` implements a compact design-guide weather
summary: a transparent 96px-wide, 181px-high component, a 92px thermometer,
a 16px Lucide weather glyph close to the tube's right side, and two centered
rows of 12px sunrise/sunset glyphs with 11px IBM Plex Mono `HH:mm` times. There are no
persistent temperature numbers, ticks, average markers, or enclosing panel.
The component also accepts the reference's six glyph placements and 16–64px
glyph sizes at its original scale. The shipped overlay uses half-size graphics
and spacing, with minimum text and sun-glyph sizes to keep the times readable.

The cyan fill compares the unrounded current Celsius reading with the mean of
the previous seven complete local days' daily mean temperatures, excluding
today. The [Open-Meteo forecast request](https://open-meteo.com/en/docs) includes
`past_days=7` and `temperature_2m_mean` for the same coordinates. The comparison
data stays in Celsius; unit conversion applies only to the other cached
weather and run-guidance fields.

| Difference from the seven-day mean | Fill |
| --- | --- |
| At or below −6°C | Bulb only |
| Above −6°C and below −2°C | Quarter tube |
| −2°C through +2°C | Half tube |
| Above +2°C and below +6°C | Three-quarter tube |
| At or above +6°C | Full tube |

The cache's `thermometer` object contains the current reading, seven dated
daily readings, condition, local date, UTC offset, and today's sunrise/sunset
in local minutes. Missing, nonfinite, incomplete, or incorrectly dated inputs
show `Weather unavailable`; a partial week never becomes a comparison against
zero. After local midnight, yesterday's summary is unavailable until refreshed.
Sun events are selected by today's date because the daily response includes
historical events too. The renderer uses location time on every draw, switching
clear/cloudy Sun glyphs to Moon glyphs at sunset and back at sunrise. Rain and
snow use `CloudRain` and `Snowflake`. The passive overlay has no hover controls.

## Location

Location resolution uses the first configured option:

1. `WEATHER_LATITUDE` and `WEATHER_LONGITUDE` for the most accurate local result.
2. `WEATHER_LOCATION` for Open-Meteo city/postal-code geocoding.
3. Public-IP geolocation for a no-configuration, city-level approximation.

Public-IP location is inherently approximate. Set coordinates in `.env` if the detected city is wrong or conditions vary significantly across your area.

## Run score

The backend guidance weighs apparent temperature, AQI, rain probability, weather hazards, wind gusts, UV, and hot-weather humidity into a planning score and best-window forecast in the cache.

Set `WEATHER_OVERLAY_ENABLED=0` to disable both windows and their fetch loops.
Units, request timeout, refresh cadence, and the personal-metrics window's
position overrides are documented in [Configuration](configuration.md).

## Display

Training preserves distance, duration, pace, heart rate/cadence, and weekly
totals. Weight uses the same neutral metric columns and detail typography
beneath training. Their 204px-high window remains below the resource gauges at
the top right. The separate thermometer window is pinned 8px from the
left and bottom monitor edges. When Minecraft is enabled, the thermometer sits
24px above it. Repository and standalone session lists reserve room above the
thermometer and page their records when needed.

All three components stay visible at the supported monitor sizes, including
1280×720. Training and weight retain whole-section paging every 30 seconds if
their window is manually shortened below 204px. Both windows use
`WEATHER_OVERLAY_ENABLED`; `WEATHER_GAP_X` and `WEATHER_GAP_Y` continue to move
only the right-side personal metrics. Shared styling belongs to the
[Desktop design system](design-system.md).

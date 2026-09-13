# Weather and running overlay

The right rail keeps training and weight below the resource gauges. A separate
thermometer window sits at the bottom left of each monitor.
The former top-right temperature, apparent-temperature, AQI, UV, condition, and
location readouts are removed. Training summarizes workouts uploaded from the phone:
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

`conky/thermometer-component.lua` implements the design-guide weather summary in
a transparent 120px-wide, 124px-high window. A 92px thermometer sits beside a
16px Lucide weather glyph above four detail rows: sunrise, sunset, UV index,
and rain chance. Detail rows use 12px glyphs and 11px IBM Plex Mono text.
All thermometer text and glyphs use the muted color. Sun times use 12-hour time with
AM/PM, such as `6:30 AM` and `7:00 PM`. There are no persistent temperature
numbers, ticks, average markers, or enclosing panel. The shipped overlay uses half-size
graphics and spacing, with minimum text and detail-glyph sizes for readability.

The component measures the visible detail rows to size its content and centers
the weather glyph over the full detail group. Its default placement is
`right-icon-above`; alternatives are `left-icon-above`, `right-icon-below`,
`left-icon-below`, `stack-above`, and `stack-below`. Side placements center the
whole information stack against the thermometer; vertical placements share a
center axis. Glyph sizes accept 16–64px before scaling. The independent boolean
options `show_sun_times`, `show_uv_index`, and `show_rain_chance` default to
`true`; hiding rows removes their space and recenters the remaining content.

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

UV and rain chance use the cache's top-level `uvIndex` and
`precipitationProbability` fields. UV uses at most one decimal place, such as
`UV 4.2`; rain chance rounds to a whole percentage. Missing or invalid optional
readings show `UV —` or `—` without removing the thermometer. UV must be finite
and nonnegative, and rain chance must be finite and between 0 and 100. Zero is
a valid reading for both.

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

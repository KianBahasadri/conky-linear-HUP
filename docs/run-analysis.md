# Exercise progression

`scripts/run_analysis.py` measures gait and GPS circuits. The pure
`scripts/exercise_progression.py` module parses training notes, keeps workloads
separate, and compares matched performances. `scripts/workout_context.py`
attaches preceding weight and hourly weather. `fetch_workouts.py` owns TCX I/O,
caching, and the [overlay](weather.md) output. Cache contracts belong to
[Caches](caches.md); settings belong to [Configuration](configuration.md).

## Input and integrity

- Lap totals give distance and duration, including walking. Negative, nonfinite,
  or malformed totals are rejected. Missing totals can use the available track
  duration; an upload cut off mid-file retains readable totals and is marked
  truncated. An incomplete track never establishes a circuit total.
- Only completed workouts with timezone-aware timestamps and finite totals
  contribute to statistics. Identical sport/start/duration/distance reuploads
  count once; complete, current analyses take precedence, then newer valid
  uploads. Future sessions and invalid intervals are excluded.
- Running workouts count as runs. Biking, cycling, walking, hiking, swimming,
  and elliptical workouts never do. Other sports require five minutes of
  detected running. All sports remain eligible for workload bookkeeping.
- An unreadable replacement upload retains its previous successful per-file
  summary with a stale flag. It cannot qualify for a performance comparison.
  An overall refresh failure retains and visibly marks the last good display.
  An advisory lock prevents concurrent refreshes from racing cache writes.

## Walk/run split and sustained runs

The track is resampled to 1 Hz. Recording gaps longer than 10 seconds are
pauses, capped at ten minutes. An 11-second median speed and cadence feed a
four-state Viterbi model: stopped, walking, running, vehicle. RunCadence counts
strides per minute, roughly 54 walking and 82 running. Cadence below 66 at speeds
above 2.6 m/s is ignored as a sensor fault. Missing cadence uses speed alone;
sustained speeds above about 5.5 m/s are treated as vehicle travel.

Running pace includes only running seconds and distance. Warm-up and cooldown
are measured around running stretches of at least 60 seconds. `runBouts` counts
those stretches; it is never a circuit-lap multiplier. A known walk/run bar
requires track coverage of at least 90% of the lap distance.

A sustained-running observation requires at least ten uninterrupted running
minutes and no recording gap over ten seconds. Its pace comes from that
continuous block, with no rests removed or running segments concatenated. GPS
location, course bounds, and block distance describe its comparison route.
Steady HR uses the final five minutes with at least 90% valid timestamp coverage.

Legacy VDOT and latent-fitness helpers remain diagnostic utilities. Their scores
are not published in the display status or used to judge progression.

## Exercise notes

Exactly three nonnegative integers mean **push-ups, pull-ups, sit-ups per lap**:

```text
8 3 11
8 3 11; rpe=7
8 3 11; rpe=7; variant=standard; rest=60
```

Named routines such as `8 push-ups + 3 pullups + 11 situps` use the same order
and per-lap interpretation. Explicit `total` notes are not multiplied. Unknown
rep counts, such as a bare `pullups`, stay unknown; no default count is invented.

Optional metadata follows semicolons and uses `key=value` or `key:value`:

| Field | Meaning |
| --- | --- |
| `rpe` | Whole-session effort, 0–10; enables matched-effort circuit and running comparisons and session-RPE workload |
| `variant` | Exercise/form identifier; defaults to `usual`, which assumes the usual form was maintained |
| `rest` | Recorded rest protocol in seconds, 0–3600; comparisons require the same recorded value |
| `laps` | Explicit positive integer count; disagreement with GPS leaves the count conflicted and unmultiplied |
| `rir` | Estimated reps in reserve, 0–30; one value for all named exercises or push/pull/sit values such as `2/1/3` |
| `test` | `run`, `pushups`, `pullups`, or `situps`; an exercise test describes a single recorded benchmark set |

A repetition-capacity benchmark can be logged as:

```text
20 pushups total; test=pushups; rir=2; rest=120; variant=standard
```

Repeated or invalid metadata is retained as a quality error and excludes the
session from comparisons. Valid recorded reps and basic volumes remain usable.
Effort ratings are optional; missing ratings never become inferred zeroes.

## GPS circuits

Circuit measurements require repeated closed GPS loops. At least two loops
must return within 20 m of an anchor, travel at least 200 m over at least one
minute, enclose at least 2000 m², and have area at least 0.02 times squared
path length. Comparable loop lengths must be within 25%. Five-metre thinning
reduces GPS jitter. Ten-metre anchor cells retain the course entrance.

Nearby duplicate timestamps are tolerated; contradictory positions, jumps
above 15 m/s, recording gaps over ten seconds, truncated uploads, and inadequate
track coverage leave the GPS count unknown. Short out-and-back detours cannot
become laps. An explicit note count can supply the rep multiplier but cannot
manufacture a timed GPS circuit.

Circuit elapsed time spans first gate entry to the final completed-loop entry,
including exercise/rest time and intervening detours, while excluding approach
and cooldown. Loop times, geometry, and a conservative 40-second gate-timing
resolution are retained. The timing resolution is an engineering guard against
boundary placement, not a validated physiological-change threshold. Rep totals
are inferred from the logged prescription and lap count; GPS does not observe
whether every prescribed rep was performed or its technique.

## Independent workload measures

Seven- and 28-day windows report run distance/count, total session minutes, and
separate push/pull/sit totals. Unknown-multiplier reps do not enter total reps;
partly quantified sessions retain known totals and an incomplete count.

Two internal-load series remain separate:

- **HR TRIMP estimate:** integrate the Banister rate over successive valid HR
  samples using trapezoidal integration. Coverage must be at least 90%; gaps
  over ten seconds, conflicting duplicate readings, invalid calibration, or
  coverage inconsistent with duration leave the load unknown. Resting and
  maximal HR are configurable estimates. No MET fallback fills missing HR.
- **Session-RPE:** session minutes multiplied by the recorded RPE. Only sessions
  with valid effort metadata contribute. Report the number of covered sessions
  beside each sum, so partial histories are not silently treated as complete.

Neither series includes arbitrary cross-exercise rep points. Neither is a
percentage improvement in fitness, and workload changes do not set the
performance color.

## Weight and workout-time weather

Weight comes from the selected openScale user's backup, including its WAL.
Each workout uses only preceding measurements, with explicit kg conversion,
source age, sample count, and a trailing seven-day median. A measurement more
than seven days old is unavailable for matching. A broken backup retains
previous readings as stale and excludes them from comparisons.

Hourly Open-Meteo ECMWF IFS temperature, humidity, dew point, wind, and solar
radiation are interpolated and averaged over the workout interval in UTC.
Coordinates are rounded to 0.01 degrees. Units, timestamp spacing, array lengths,
missing hours, and supported value ranges are validated. Model weather is
marked estimated; it does not imply on-site readings or measured WBGT.

Monthly weather tiles are cached. At most three requests of ten seconds each
run per refresh, prioritizing recent sessions; history fills over subsequent
refreshes. Failures preserve already usable historical tiles and retry after an
hour. HTTP 429/503 responses pause all weather requests and honor a longer
`Retry-After` interval. A successful but incomplete tile is retried no sooner than six hours.
Missing location or weather stays unknown and never prevents local statistics.

Weight and weather select comparable sessions; they do not award bonus points
or apply an unvalidated seconds-per-pound or seconds-per-degree correction.

## Performance comparisons

Comparisons use up to 84 days of earlier sessions and distinguish:

- **Circuit performance:** the same rep prescription, per-lap/total convention,
  lap count, route, form identifier, rest protocol, and RPE within one point.
- **Running performance:** sustained runs on comparable routes/distances.
  With RPE, compare pace at matched effort. Without RPE, valid steady HR can
  be compared at paces within 2%, yielding `Lower HR`/`Higher HR` response labels.
- **Repetition capacity:** the same exercise test, form, recorded rest protocol,
  and RIR within one repetition. Ordinary circuit rep totals remain workload.

Routes must have centres within 50 m, distances within 5%, and similar width
and height (within 10% or 20 m). Weight medians must be within 2%. Circuit and
running comparisons additionally require temperature and dew point within 3°C,
wind within 5 km/h, and solar radiation within 150 W/m². These are conservative
matching calipers, not validated correction equations. Missing context, stale
uploads, changed prescriptions, and workouts older than ten days prevent a
current performance verdict.

A single matched difference is descriptive and stays neutral. At least eight
sessions on distinct UTC days are required for the change screen: the latest
four versus the preceding four. An exact two-sided rank-sum permutation screen
must meet p ≤ 0.05, and the median difference must exceed measurement resolution
(40 seconds for circuits, 1 second/km or bpm for running, 1 rep for capacity).
Otherwise the result stays within variation or continues building a baseline.

The screen assumes comparable, sufficiently independent observations. It labels
an observed matched performance change (`Faster`, `Slower`, or a specific HR/rep
response); it does not establish a causal training effect or a calibrated
probability that overall fitness changed. Repeated laps and same-day sessions
are not counted as independent longitudinal evidence.

## Evidence behind the design

The separation of load, athlete state, and adaptation follows the
[2026 athlete-monitoring framework](https://doi.org/10.1007/s40279-026-02417-4).
Distinct resistance-training outcomes are described by the
[2026 ACSM position stand](https://pmc.ncbi.nlm.nih.gov/articles/PMC12965823/).
[Session-RPE research](https://pubmed.ncbi.nlm.nih.gov/11708692/) and
[longitudinal HR/running-speed research](https://pmc.ncbi.nlm.nih.gov/articles/PMC7967764/)
support those measures within their intended scope. Environmental context is
supported by [race-weather research](https://pmc.ncbi.nlm.nih.gov/articles/PMC8677617/),
while [push-up force measurements](https://pubmed.ncbi.nlm.nih.gov/20179649/)
and [running bodyweight experiments](https://pubmed.ncbi.nlm.nih.gov/18055630/)
support retaining bodyweight context. None validates this application's complete
comparison pipeline; its numerical matching rules are documented above.

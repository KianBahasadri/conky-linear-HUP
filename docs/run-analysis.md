# Run analysis

`scripts/run_analysis.py` turns each uploaded TCX track into a walk-aware
summary and turns the run history into a fitness trend. `fetch_workouts.py`
caches the per-file results and writes the status fields listed in
[Caches](caches.md); the running band of the
[weather and running overlay](weather.md) draws them.

## Input

- Lap totals give each workout's distance and time, so walking still counts
  toward volume. Trackpoints (time, cumulative distance, `RunCadence`) feed the
  gait split.
- An upload that ends mid-file is kept and marked `truncated`. RunnerUp writes
  the lap totals before the track, so the totals stay complete and the
  trackpoints before the break still give a pace and score. When the track
  covers less than 90% of the lap distance, the walk/run split of the missing
  part is unknown, so the sparkline draws that bar solid.
- `Running` workouts always count as runs. `Biking`, `Cycling`, `Walking`,
  `Hiking`, `Swimming`, and `Elliptical` never do. Any other sport (RunnerUp's
  `Other`) counts only with at least 5 minutes of detected running. The week
  and 28-day totals and the recent-run list use the same set.

## Gait split

- The track is resampled to 1 Hz. Recording gaps longer than 10 s are pauses
  (capped at 10 minutes) and count as neither running nor walking time.
- Speed is the median per-second distance over an 11 s window. A four-state
  hidden Markov model (stopped, walking, running, vehicle), decoded with
  Viterbi, labels every second from speed and cadence. `RunCadence` counts
  strides per minute, about 54 walking and 82 running.
- A cadence below 66 at more than 2.6 m/s is a sensor fault, not a long
  stride, so it is ignored, and tracks without cadence fall back to speed
  alone. Sustained speeds above about 5.5 m/s are a vehicle and count as
  neither running nor walking.
- Running pace uses only running seconds and meters. Warm-up and cool-down are
  the distances before the first and after the last run of at least 60 s.

## Effort score

- A run's score is the best Daniels–Gilbert VDOT over any window of either the moving
  track or the concentrated running bouts lasting at least max(8 min, min(60 min, half the
  running time)), plus `2.5 × ln(T / 20 min)` for a window of length `T`. For interval runs
  or circuit workouts with bodyweight exercise stops between laps, evaluating the running
  segments ensures stationary rests do not artificially depress the runner's speed score.
  The adjustment credits longer windows for the faster fatigue of recreational
  runners, so a short hard run and a long steady one share one scale (roughly
  a Riegel exponent of 1.1–1.15).
- Runs with less than 8 minutes or 1.2 km of running get no score. They still
  count toward volume and reset the detraining clock.
- Scores are shown as the 5K time that would earn the same score (`5K 29:23`).

## Workout load and Rate of Progress

- For cross-training, calisthenics runs, and multi-sport sessions, each workout receives
  a unified physical strain score (`totalLoad`):
  - **Cardio Load (TRIMP):** Duration scaled by Heart Rate Reserve factor $\Delta\text{HR} = (\text{HR} - 50) / 145$
    via Banister's impulse equation ($t \times \Delta\text{HR} \times 0.64 e^{1.92 \Delta\text{HR}}$), falling back to
    sport MET multipliers when heart rate is absent.
  - **Strength Load:** Bodyweight reps extracted from TCX `<Notes>` (`pushups`, `pullups`, `situps`), multiplied
    by lap count for per-lap routines and weighted by biomechanical load points (pull-ups 1.5, push-ups 0.5, sit-ups 0.3).
- **Chronic Training Load (CTL):** An exponential moving average of daily workout load with a 28-day time constant.
- **Rate of Progress:** The 28-day percentage change in training capacity $\frac{\text{CTL}_{\text{now}} - \text{CTL}_{\text{28d ago}}}{\text{CTL}_{\text{28d ago}}} \times 100\%$.
  When bodyweight circuits are detected, the progress headline shows this rate of progress (`+59%`) in semantic green
  (`Better`) or red (`Worse`), and the telemetry line highlights total strength reps (`35 push · 25 pull · 50 sit`).

## Fitness trend

- Fitness is a latent level on a 0.25-point grid, filtered forward and
  smoothed backward over every run. Each run gets a smoothed level, including
  unscored runs.
- A scored run usually lands a little below the level: an exponential gap with
  mean 1.5 points, plus 1 point of noise. Sometimes it lands anywhere up to 25
  points below (a 35% easy-day share), and rarely far off in either direction
  (a 4% outlier share, sd 8). Easy days and GPS glitches therefore barely move
  the level.
- Between runs the level drifts (variance 0.03 per day) and occasionally jumps
  (4% per week, sd 4), which absorbs comebacks and layoffs. After 7 days
  without a run it loses 0.06 points a day, up to 5 points per break.
- The verdict compares the smoothed level now with the level 28 days ago. It is
  `Better` when the chance the level rose is at least 80% and the 5K
  equivalent improved by at least 15 s, `Worse` in the mirror case, and
  `Steady` otherwise. A trend needs at least three scored runs.
- The chance treats the two estimates as independent. That understates
  confidence and keeps the verdict conservative. After a long break,
  detraining shows as a slower trend in amber (the 10-day age rule), usually
  before the evidence is strong enough for `Worse`.
- Heat, hills, and heart rate are not modeled. GPS altitude is too noisy for
  grade. Open-Meteo history for these runs showed no measurable heat effect on
  the scores, so the fetcher stays offline.

"""Walk-aware run analysis: gait split, effort score, and fitness trend.

Pure functions over parsed TCX tracks; fetch_workouts.py owns file I/O and
caching. See docs/run-analysis.md for the model.
"""
import math


STOPPED, WALKING, RUNNING, VEHICLE = range(4)
STATE_COUNT = 4

PAUSE_GAP_SECONDS = 10
MAX_PAUSE_SECONDS = 600
SPEED_HALF_WINDOW = 5

# RunCadence counts one foot, so these are strides (not steps) per minute.
SPEED_MODELS = {STOPPED: (0.0, 0.3), WALKING: (1.4, 0.35), RUNNING: (3.1, 0.8)}
CADENCE_MODELS = {
    STOPPED: (25.0, 25.0),
    WALKING: (54.0, 6.0),
    RUNNING: (82.0, 6.0),
    VEHICLE: (40.0, 40.0),
}
VEHICLE_SPEED = 5.5
# Each reading mixes its model with a flat floor, so one bad sample cannot force a state.
SPEED_TRUST = math.log(0.98)
SPEED_FLOOR = math.log(0.02 / 15.0)
CADENCE_TRUST = math.log(0.90)
CADENCE_FLOOR = math.log(0.10 / 200.0)
# A walking cadence at running speed is a sensor fault, not a long stride.
CADENCE_FAULT_MAX = 66
CADENCE_FAULT_SPEED = 2.6
GAIT_SWITCH = 1.0 / 45.0
VEHICLE_SWITCH = 1.0 / 3000.0
SUSTAINED_RUN_SECONDS = 60
MAX_STEP_METERS = 7.0

MIN_SCORED_RUN_SECONDS = 480
MIN_SCORED_RUN_METERS = 1200.0
EFFORT_MIN_SECONDS = 480
EFFORT_SHARE = 0.5
EFFORT_SHARE_CAP_SECONDS = 3600
EFFORT_GROWTH = 1.05
# Recreational runners slow with duration faster than the Daniels curve
# assumes; the slope credits longer efforts so they compare with short ones.
ENDURANCE_SLOPE = 2.5
ENDURANCE_REFERENCE_SECONDS = 1200.0

GRID_STEP = 0.25
GRID_BELOW = 12.0
GRID_ABOVE = 10.0
OBSERVATION_SD = 1.0
EFFORT_GAP_MEAN = 1.5
EASY_SHARE = 0.35
EASY_SPAN = 25.0
OUTLIER_SHARE = 0.04
OUTLIER_SD = 8.0
DRIFT_PER_DAY = 0.03
JUMP_PER_WEEK = 0.04
JUMP_SD = 4.0
DETRAIN_GRACE_DAYS = 7.0
DETRAIN_PER_DAY = 0.06
DETRAIN_CAP = 5.0

SQRT2 = math.sqrt(2.0)
LOG_SQRT_2PI = 0.5 * math.log(2.0 * math.pi)


def _logaddexp(a, b):
    if a < b:
        a, b = b, a
    return a + math.log1p(math.exp(b - a))


def _log_normal(x, mean, sd):
    z = (x - mean) / sd
    return -0.5 * z * z - math.log(sd) - LOG_SQRT_2PI


def resample(track):
    """Per-second distance, cadence, and pause flags from (epoch, meters, cadence) points."""
    points = sorted((point for point in track if point[0] is not None), key=lambda point: point[0])
    first_distance = next((point[1] for point in points if point[1] is not None), None)
    if len(points) < 2 or first_distance is None:
        return [], [], []
    distance, cadence, paused = [first_distance], [points[0][2]], [False]
    previous_time, previous_distance = points[0][0], first_distance
    for stamp, meters, steps in points[1:]:
        meters = previous_distance if meters is None else max(previous_distance, meters)
        seconds = int(round(stamp - previous_time))
        if seconds < 1:
            previous_distance = meters
            continue
        if stamp - previous_time > PAUSE_GAP_SECONDS:
            for _ in range(min(seconds, MAX_PAUSE_SECONDS) - 1):
                distance.append(previous_distance)
                cadence.append(None)
                paused.append(True)
            distance.append(meters)
            cadence.append(steps)
            paused.append(False)
        else:
            for second in range(1, seconds + 1):
                distance.append(previous_distance + (meters - previous_distance) * second / seconds)
                cadence.append(steps if second == seconds else None)
                paused.append(False)
        previous_time, previous_distance = stamp, meters
    return distance, cadence, paused


def _median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return 0.5 * (ordered[middle - 1] + ordered[middle])


def _speeds(distance):
    increments = [later - earlier for earlier, later in zip(distance, distance[1:])] + [0.0]
    count = len(increments)
    speeds = [
        _median(increments[max(0, index - SPEED_HALF_WINDOW) : index + SPEED_HALF_WINDOW + 1])
        for index in range(count)
    ]
    return speeds, increments


def _speed_loglik(speed, state):
    if state == VEHICLE:
        x = (speed - VEHICLE_SPEED) / 0.4
        return (-math.log1p(math.exp(-x)) if x > -30 else x) - math.log(20.0)
    mean, sd = SPEED_MODELS[state]
    return _logaddexp(SPEED_TRUST + _log_normal(speed, mean, sd), SPEED_FLOOR)


def _emissions(speed, steps, paused):
    if paused:
        return [0.0, -50.0, -50.0, -50.0]
    trusted = (
        steps is not None
        and steps > 0
        and not (steps < CADENCE_FAULT_MAX and speed > CADENCE_FAULT_SPEED)
    )
    scores = []
    for state in range(STATE_COUNT):
        score = _speed_loglik(speed, state)
        if trusted:
            mean, sd = CADENCE_MODELS[state]
            score += _logaddexp(CADENCE_TRUST + _log_normal(steps, mean, sd), CADENCE_FLOOR)
        scores.append(score)
    return scores


def _transition_logs():
    rows = []
    for source in range(STATE_COUNT):
        row = []
        for target in range(STATE_COUNT):
            if source == target:
                row.append(None)
            elif VEHICLE in (source, target):
                row.append(VEHICLE_SWITCH)
            else:
                row.append(GAIT_SWITCH / 2.0)
        stay = 1.0 - sum(value for value in row if value is not None)
        rows.append([math.log(stay if value is None else value) for value in row])
    return rows


TRANSITION_LOGS = _transition_logs()


def gait_states(distance, cadence, paused):
    """Most likely stopped/walking/running/vehicle state for every second (Viterbi)."""
    if not distance:
        return [], []
    speeds, increments = _speeds(distance)
    scores = _emissions(speeds[0], cadence[0], paused[0])
    scores[VEHICLE] -= 8.0
    backpointers = []
    for index in range(1, len(speeds)):
        emissions = _emissions(speeds[index], cadence[index], paused[index])
        pointers = [0] * STATE_COUNT
        updated = [0.0] * STATE_COUNT
        for target in range(STATE_COUNT):
            best_source, best = 0, -math.inf
            for source in range(STATE_COUNT):
                value = scores[source] + TRANSITION_LOGS[source][target]
                if value > best:
                    best_source, best = source, value
            pointers[target] = best_source
            updated[target] = best + emissions[target]
        backpointers.append(pointers)
        scores = updated
    state = max(range(STATE_COUNT), key=lambda candidate: scores[candidate])
    states = [state]
    for pointers in reversed(backpointers):
        state = pointers[state]
        states.append(state)
    states.reverse()
    return states, increments


def vdot(seconds, meters):
    """Daniels-Gilbert VO2max equivalent of covering `meters` in `seconds`."""
    if seconds <= 0 or meters <= 0:
        return 0.0
    minutes = seconds / 60.0
    velocity = meters / minutes
    oxygen = -4.60 + 0.182258 * velocity + 0.000104 * velocity * velocity
    sustainable = (
        0.8
        + 0.1894393 * math.exp(-0.012778 * minutes)
        + 0.2989558 * math.exp(-0.1932605 * minutes)
    )
    return oxygen / sustainable


def effort_score(seconds, meters):
    """Performance score of an effort, comparable across durations."""
    return vdot(seconds, meters) + ENDURANCE_SLOPE * math.log(seconds / ENDURANCE_REFERENCE_SECONDS)


def equivalent_seconds(score, meters=5000.0):
    """Time over `meters` that earns `score`."""
    low, high = 60.0, 12 * 3600.0
    if effort_score(high, meters) >= score:
        return high
    for _ in range(64):
        middle = 0.5 * (low + high)
        if effort_score(middle, meters) > score:
            low = middle
        else:
            high = middle
    return 0.5 * (low + high)


def best_effort(increments, run_seconds):
    """Highest-scoring window spanning at least half the running time."""
    count = len(increments)
    shortest = max(EFFORT_MIN_SECONDS, min(EFFORT_SHARE_CAP_SECONDS, EFFORT_SHARE * run_seconds))
    if count < shortest:
        return None
    prefix = [0.0]
    for meters in increments:
        prefix.append(prefix[-1] + meters)
    best = None
    window = shortest
    while True:
        seconds = min(int(round(window)), count)
        meters = max(prefix[start + seconds] - prefix[start] for start in range(0, count - seconds + 1, 2))
        score = effort_score(seconds, meters)
        if best is None or score > best[0]:
            best = (score, seconds, meters)
        if seconds >= count:
            return best
        window *= EFFORT_GROWTH


def analyze_track(track):
    """Gait split and effort score for one workout's (epoch, meters, cadence) points."""
    distance, cadence, paused = resample(track)
    states, increments = gait_states(distance, cadence, paused)
    if len(states) < 30:
        return {}
    seconds = [0] * STATE_COUNT
    meters = [0.0] * STATE_COUNT
    for index, state in enumerate(states):
        if not paused[index]:
            seconds[state] += 1
            meters[state] += increments[index]

    runs = []
    start = None
    for index, state in enumerate(states + [None]):
        if state == RUNNING and start is None:
            start = index
        elif state != RUNNING and start is not None:
            if index - start >= SUSTAINED_RUN_SECONDS:
                runs.append((start, index - 1))
            start = None
    warmup = distance[runs[0][0]] - distance[0] if runs else 0.0
    cooldown = distance[-1] - distance[runs[-1][1]] if runs else 0.0

    summary = {
        "trackMeters": round(distance[-1] - distance[0], 1),
        "runSeconds": seconds[RUNNING],
        "runMeters": round(meters[RUNNING], 1),
        "walkSeconds": seconds[WALKING],
        "walkMeters": round(meters[WALKING], 1),
        "warmupMeters": round(warmup, 1),
        "cooldownMeters": round(cooldown, 1),
    }
    if seconds[RUNNING] >= MIN_SCORED_RUN_SECONDS and meters[RUNNING] >= MIN_SCORED_RUN_METERS:
        moving = [
            min(increments[index], MAX_STEP_METERS)
            if state in (RUNNING, WALKING) and not paused[index]
            else 0.0
            for index, state in enumerate(states)
        ]
        effort = best_effort(moving, seconds[RUNNING])
        if effort:
            summary.update(
                {
                    "score": round(effort[0], 2),
                    "scoreSeconds": effort[1],
                    "scoreMeters": round(effort[2], 1),
                }
            )
    return summary


class _Grid:
    def __init__(self, scores):
        self.low = math.floor(min(scores) - GRID_BELOW)
        high = math.ceil(max(scores) + GRID_ABOVE)
        self.size = int(round((high - self.low) / GRID_STEP)) + 1
        self.values = [self.low + index * GRID_STEP for index in range(self.size)]

    def likelihood(self, score):
        rate = 1.0 / EFFORT_GAP_MEAN
        spread = rate * OBSERVATION_SD * OBSERVATION_SD
        result = []
        for level in self.values:
            gap = level - score
            argument = (spread - gap) / (SQRT2 * OBSERVATION_SD)
            if argument > 25.0:
                log_effort = (
                    math.log(rate / 2.0)
                    + (rate / 2.0) * (spread - 2.0 * gap)
                    - argument * argument
                    - math.log(argument * math.sqrt(math.pi))
                )
            else:
                log_effort = math.log(rate / 2.0) + (rate / 2.0) * (spread - 2.0 * gap) + math.log(
                    max(math.erfc(argument), 1e-300)
                )
            easy = 0.5 * (1.0 + math.erf(gap / (SQRT2 * OBSERVATION_SD))) / EASY_SPAN if gap < EASY_SPAN else 0.0
            outlier = math.exp(_log_normal(score, level, OUTLIER_SD))
            result.append(
                (1.0 - OUTLIER_SHARE) * ((1.0 - EASY_SHARE) * math.exp(log_effort) + EASY_SHARE * easy)
                + OUTLIER_SHARE * outlier
            )
        return result


def _normalize(weights):
    total = sum(weights)
    return [weight / total for weight in weights] if total > 0 else weights


def _blur(weights, sd_steps):
    half = max(1, int(math.ceil(3.5 * sd_steps)))
    taps = [math.exp(-0.5 * (offset / sd_steps) ** 2) for offset in range(-half, half + 1)]
    total = sum(taps)
    taps = [tap / total for tap in taps]
    size = len(weights)
    result = [0.0] * size
    for index, weight in enumerate(weights):
        if weight == 0.0:
            continue
        for offset, tap in enumerate(taps):
            target = index + offset - half
            if 0 <= target < size:
                result[target] += weight * tap
    return result


def _box(weights, width):
    half = width // 2
    size = len(weights)
    prefix = [0.0]
    for weight in weights:
        prefix.append(prefix[-1] + weight)
    return [
        (prefix[min(size, index + half + 1)] - prefix[max(0, index - half)]) / (2 * half + 1)
        for index in range(size)
    ]


def _jump_blur(weights):
    width = int(round(math.sqrt(4.0 * (JUMP_SD / GRID_STEP) ** 2 + 1.0)))
    return _box(_box(_box(weights, width), width), width)


def _shift(weights, steps):
    if steps <= 0:
        return list(weights)
    return list(weights[steps:]) + [0.0] * steps


def _unshift(weights, steps):
    if steps <= 0:
        return list(weights)
    return [0.0] * steps + list(weights[:-steps])


def _detraining_steps(idle_days):
    loss = min(DETRAIN_CAP, DETRAIN_PER_DAY * (idle_days - DETRAIN_GRACE_DAYS))
    return int(round(loss / GRID_STEP)) if idle_days > DETRAIN_GRACE_DAYS else 0


def _transition(days, idle_before, idle_after):
    """Drift sd (grid steps), jump probability, and detraining shift for one step.

    Detraining depends on the time since the last run, so splitting a break
    into several steps loses the same fitness as one long step.
    """
    days = max(days, 0.0)
    drift_sd = math.sqrt(DRIFT_PER_DAY * days + 0.01) / GRID_STEP
    jump = 1.0 - (1.0 - JUMP_PER_WEEK) ** (days / 7.0)
    shift = 0
    if idle_before is not None:
        shift = _detraining_steps(idle_after) - _detraining_steps(idle_before)
    return drift_sd, jump, shift


def _predict(weights, transition):
    drift_sd, jump, shift = transition
    moved = _shift(weights, shift)
    steady, jumped = _blur(moved, drift_sd), _jump_blur(moved)
    return _normalize([(1.0 - jump) * a + jump * b for a, b in zip(steady, jumped)])


def _predict_adjoint(ratios, transition):
    drift_sd, jump, shift = transition
    steady, jumped = _blur(ratios, drift_sd), _jump_blur(ratios)
    return _unshift([(1.0 - jump) * a + jump * b for a, b in zip(steady, jumped)], shift)


def _moments(grid, weights):
    mean = sum(value * weight for value, weight in zip(grid.values, weights))
    variance = sum((value - mean) ** 2 * weight for value, weight in zip(grid.values, weights))
    return mean, math.sqrt(max(variance, 1e-9))


def fitness_trend(samples, now, window_days=28.0):
    """Smoothed fitness level at each (epoch, score-or-None) sample and its change over the window.

    The latent level drifts slowly, occasionally jumps, and decays during long
    breaks. A run usually scores a little below the level, sometimes far below
    (an easy day), and rarely above it (a GPS or sensor outlier). Samples
    without a score get a level but contribute no evidence; samples after
    `now` get None. Levels keep the input order. `probability` is the chance
    the level now exceeds the level `window_days` ago, treating the two
    estimates as independent, which understates confidence.
    """
    steps = [(stamp, score, index) for index, (stamp, score) in enumerate(samples) if stamp <= now]
    scores = [score for _, score, _ in steps if score is not None]
    if not scores:
        return None
    grid = _Grid(scores)
    then = now - window_days * 86400.0
    steps += [(then, None, "then"), (now, None, "now")]
    steps.sort(key=lambda step: (step[0], isinstance(step[2], str)))

    weights = [1.0 / grid.size] * grid.size
    filtered, predicted, transitions = [], [], [None]
    previous = last_run = None
    for stamp, score, key in steps:
        if previous is not None:
            idle_before = (previous - last_run) / 86400.0 if last_run is not None else None
            idle_after = (stamp - last_run) / 86400.0 if last_run is not None else None
            transitions.append(_transition((stamp - previous) / 86400.0, idle_before, idle_after))
            weights = _predict(weights, transitions[-1])
        predicted.append(weights)
        if score is not None:
            weights = _normalize([a * b for a, b in zip(weights, grid.likelihood(score))])
        if not isinstance(key, str):
            last_run = stamp
        filtered.append(weights)
        previous = stamp

    smoothed = [None] * len(steps)
    smoothed[-1] = filtered[-1]
    for index in range(len(steps) - 2, -1, -1):
        ratios = [
            later / estimate if estimate > 1e-300 else 0.0
            for later, estimate in zip(smoothed[index + 1], predicted[index + 1])
        ]
        backward = _predict_adjoint(ratios, transitions[index + 1])
        smoothed[index] = _normalize([a * b for a, b in zip(filtered[index], backward)])

    levels = [None] * len(samples)
    moments = {}
    for weights, (_, _, key) in zip(smoothed, steps):
        if isinstance(key, str):
            moments[key] = _moments(grid, weights)
        else:
            levels[key] = _moments(grid, weights)[0]
    then_moments, now_moments = moments["then"], moments["now"]
    difference = now_moments[0] - then_moments[0]
    spread = math.hypot(now_moments[1], then_moments[1])
    return {
        "levels": levels,
        "now": now_moments[0],
        "nowSd": now_moments[1],
        "then": then_moments[0],
        "thenSd": then_moments[1],
        "probability": 0.5 * (1.0 + math.erf(difference / (SQRT2 * spread))),
    }

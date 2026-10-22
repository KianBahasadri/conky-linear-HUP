#!/usr/bin/env python3
"""Summarize an openScale 3 backup for the weather, running, and weight panel."""

import json
import math
import os
import sqlite3
import tempfile
import zipfile
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fetch_common as common


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "cache"
STATUS_PATH = CACHE_DIR / "weight-status.json"
LOG_PATH = CACHE_DIR / "conky-weight.log"
DEFAULT_WORKOUTS_DIR = CACHE_DIR / "workouts"
DATABASE_NAME = "openScale.db"
MAX_BACKUP_BYTES = 64 * 1024 * 1024
UNIT_SYMBOLS = {"KG": "kg", "LB": "lb", "ST": "st"}

log_event = common.make_logger(LOG_PATH, "fetch_weight")
atomic_write_json = common.atomic_write_json


def read_backup(path, user_id=None):
    """Read a private copy, including SQLite's WAL, without changing the upload.

    openScale 3 stores weights in MeasurementType.unit, including conversions
    of historical values when that unit changes. Do not convert pounds again.
    """
    with tempfile.TemporaryDirectory(prefix="conky-weight-") as temporary_dir:
        directory = Path(temporary_dir)
        with zipfile.ZipFile(path) as archive:
            names = {DATABASE_NAME, DATABASE_NAME + "-wal", DATABASE_NAME + "-shm"}
            members = [member for member in archive.infolist() if member.filename in names]
            if not any(member.filename == DATABASE_NAME for member in members):
                raise ValueError("Backup does not contain openScale.db")
            if sum(member.file_size for member in members) > MAX_BACKUP_BYTES:
                raise ValueError("openScale backup exceeds 64 MiB")
            for member in members:
                # Only exact, known filenames are written inside the private directory.
                (directory / member.filename).write_bytes(archive.read(member))

        database = directory / DATABASE_NAME
        connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
        try:
            connection.execute("PRAGMA query_only=ON")
            type_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(MeasurementType)").fetchall()
            }
            if "key" in type_columns and "identity" in type_columns:
                where_clause = "UPPER(COALESCE(t.key, '')) = 'WEIGHT' OR LOWER(COALESCE(t.identity, '')) IN ('builtin.weight', 'weight')"
            elif "identity" in type_columns:
                where_clause = "LOWER(COALESCE(t.identity, '')) IN ('builtin.weight', 'weight')"
            else:
                where_clause = "t.key = 'WEIGHT'"
            rows = connection.execute(
                f"""SELECT m.userId, m.timestamp, COALESCE(v.floatValue, v.intValue), t.unit, t.id
                   FROM Measurement m
                   JOIN MeasurementValue v ON v.measurementId = m.id
                   JOIN MeasurementType t ON t.id = v.typeId
                   WHERE {where_clause}
                   ORDER BY m.timestamp, m.id"""
            ).fetchall()
            goal_rows = []
            has_goals = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_goals'"
            ).fetchone()
            if has_goals:
                goal_rows = connection.execute(
                    "SELECT userId, measurementTypeId, goalValue FROM user_goals"
                ).fetchall()
        finally:
            connection.close()

    readings = []
    for owner, timestamp, value, unit, type_id in rows:
        try:
            value = float(value)
            timestamp = float(timestamp)
            if not math.isfinite(value) or value <= 0 or timestamp <= 0:
                continue
            stamp = datetime.fromtimestamp(timestamp / 1000, timezone.utc)
        except (TypeError, ValueError, OverflowError, OSError):
            continue
        readings.append({"userId": owner, "timestamp": stamp, "value": value, "unit": unit, "typeId": type_id})

    owners = {reading["userId"] for reading in readings}
    if user_id is None:
        if len(owners) > 1:
            raise ValueError("Multiple openScale users; set WEIGHT_USER_ID")
        user_id = next(iter(owners), None)
    readings = [reading for reading in readings if reading["userId"] == user_id]
    if not readings:
        raise ValueError("No weight measurements in the openScale backup for this user")
    units = {reading["unit"] for reading in readings}
    if len(units) != 1 or readings[0]["unit"] not in UNIT_SYMBOLS:
        raise ValueError("Unsupported or inconsistent openScale weight units")

    weight_type_ids = {reading["typeId"] for reading in readings}
    goal_value = None
    for goal_user_id, goal_type_id, raw_goal in goal_rows:
        if goal_user_id == user_id and goal_type_id in weight_type_ids:
            try:
                candidate = float(raw_goal)
                if math.isfinite(candidate) and candidate > 0:
                    goal_value = candidate
            except (TypeError, ValueError):
                pass
    if goal_value is not None:
        # openScale converts MeasurementValue rows when the unit changes from KG to LB,
        # but leaves user_goals.goalValue in KG.
        if readings[0]["unit"] == "LB" and goal_value < 115 and readings[-1]["value"] > 130:
            goal_value = goal_value * 2.20462262
        for reading in readings:
            reading["goal"] = goal_value
    return readings


def date_text(stamp, now):
    local_date = stamp.astimezone().date()
    if local_date == now.date():
        return "Today"
    if local_date == now.date() - timedelta(days=1):
        return "Yesterday"
    return local_date.strftime("%b %-d" if local_date.year == now.year else "%b %-d, %Y")


def format_signed(delta, unit):
    if delta is None:
        return "--"
    delta = 0.0 if round(delta, 1) == 0 else round(delta, 1)
    sign = "+" if delta > 0 else "−" if delta < 0 else ""
    return f"{sign}{abs(delta):.1f} {unit}"


def build_status(readings, now=None):
    now = now or datetime.now().astimezone()
    last = readings[-1]
    previous = readings[-2] if len(readings) > 1 else None
    unit = UNIT_SYMBOLS[last["unit"]]
    change = round(last["value"] - previous["value"], 1) if previous else None
    # Rounding a tiny negative difference must not display a misleading "-0.0".
    change = 0.0 if change == 0 else change
    change_text = format_signed(change, unit)
    age_days = (now.date() - last["timestamp"].astimezone().date()).days

    # Progress over time: compare latest against recent ~30d baseline (or previous reading)
    # and evaluate movement toward goal (or downward when no explicit goal is stored).
    cutoff_recent = last["timestamp"] - timedelta(days=35)
    window_prior = [r["value"] for r in readings[:-1] if r["timestamp"] >= cutoff_recent]
    if len(window_prior) >= 2:
        baseline_val = sum(window_prior) / len(window_prior)
        baseline_label = "vs 30d avg"
    elif len(readings) > 1:
        prior_slice = [r["value"] for r in readings[:-1][-5:]]
        baseline_val = sum(prior_slice) / len(prior_slice)
        baseline_label = f"since {date_text(previous['timestamp'], now)}" if len(prior_slice) == 1 else "vs recent avg"
    else:
        baseline_val = None
        baseline_label = "First weigh-in"

    trend_delta = round(last["value"] - baseline_val, 1) if baseline_val is not None else None
    trend_delta = 0.0 if trend_delta == 0 else trend_delta
    trend_delta_text = format_signed(trend_delta, unit)
    trend_detail_text = (
        f"{trend_delta_text} {baseline_label}" if trend_delta is not None else baseline_label
    )

    goal = last.get("goal")
    if goal is not None:
        goal_rounded = round(goal, 1)
        to_goal = round(last["value"] - goal, 1)
        to_goal = 0.0 if to_goal == 0 else to_goal
        if abs(to_goal) <= 0.5:
            goal_text = f"At {goal_rounded:.0f} {unit} goal"
        elif to_goal > 0:
            goal_text = f"{abs(to_goal):.1f} {unit} above {goal_rounded:.0f} {unit} goal"
        else:
            goal_text = f"{abs(to_goal):.1f} {unit} below {goal_rounded:.0f} {unit} goal"
    else:
        goal_rounded = None
        goal_text = f"prev {previous['value']:.1f} {unit} · {date_text(previous['timestamp'], now)}" if previous else ""

    if baseline_val is None:
        verdict, kind = "Steady", "neutral"
    else:
        if goal is not None:
            dist_now = abs(last["value"] - goal)
            dist_before = abs(baseline_val - goal)
            improvement = dist_before - dist_now  # positive = closer to goal
        else:
            improvement = baseline_val - last["value"]  # positive = weight down
        if improvement >= 0.5:
            verdict, kind = "Better", "good"
        elif improvement <= -0.5:
            verdict, kind = "Worse", "danger"
        else:
            verdict, kind = "Steady", "neutral"

    recent_series = [
        {
            "value": round(r["value"], 1),
            "dateText": date_text(r["timestamp"], now),
            "isLast": r is last,
        }
        for r in readings[-12:]
    ]

    status = {
        "ok": True,
        "stale": False,
        "updatedAt": now.astimezone(timezone.utc).isoformat(),
        "userId": last["userId"],
        "measurementCount": len(readings),
        "unit": unit,
        "lastWeight": round(last["value"], 1),
        "lastWeightText": f"{last['value']:.1f} {unit}",
        "lastMeasuredAt": last["timestamp"].isoformat(),
        "lastDateText": date_text(last["timestamp"], now),
        "ageDays": age_days,
        "ageText": f"{age_days}d ago" if age_days > 1 else "",
        "previousWeightText": f"{previous['value']:.1f} {unit}" if previous else "",
        "previousDateText": date_text(previous["timestamp"], now) if previous else "",
        "change": change,
        "changeText": change_text,
        "trendDelta": trend_delta,
        "trendDeltaText": trend_delta_text,
        "trendDetailText": trend_detail_text,
        "progressVerdict": verdict,
        "progressKind": kind,
        "goalText": goal_text,
        " recent": recent_series,
    }
    status["recent"] = status.pop(" recent")
    if goal_rounded is not None:
        status["goalWeight"] = goal_rounded
        status["goalWeightText"] = f"{goal_rounded:.1f} {unit}"
    return status


def write_error(message):
    try:
        previous = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None
    if isinstance(previous, dict) and previous.get("ok"):
        previous.update(stale=True, error=message)
        status = previous
    else:
        status = {
            "ok": False,
            "stale": False,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "error": message,
        }
    atomic_write_json(STATUS_PATH, status)
    log_event(f"error: {message}")


def main():
    common.load_env()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        workouts_dir = Path(os.environ.get("WORKOUTS_DIR", "") or DEFAULT_WORKOUTS_DIR)
        weight_dir = Path(os.environ.get("WEIGHT_DIR", "") or workouts_dir / "weight")
        raw_user_id = os.environ.get("WEIGHT_USER_ID", "").strip()
        user_id = int(raw_user_id) if raw_user_id else None
        backups = list(weight_dir.glob("*.zip"))
        if not backups:
            raise ValueError("No openScale backup uploaded yet")
        path = max(backups, key=lambda item: (item.stat().st_mtime_ns, item.name))
        readings = read_backup(path, user_id)
        status = build_status(readings)
        status["sourceFile"] = path.name
    except (OSError, ValueError, sqlite3.Error, zipfile.BadZipFile, zlib.error, EOFError, RuntimeError) as error:
        write_error(str(error))
        return 1

    atomic_write_json(STATUS_PATH, status)
    log_event(f"summarized weight measurements={len(readings)} source={path.name}")
    print(json.dumps(status, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

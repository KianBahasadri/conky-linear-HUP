import json
import os
import sqlite3
import zipfile
from datetime import datetime, timedelta

import pytest

import fetch_weight as weight


def stamp(day):
    return datetime(2026, 8, day, 12).astimezone()


def write_backup(path, rows=None, unit="LB"):
    """Make a real committed WAL backup; recent readings are absent from the DB alone."""
    database = path.parent / (path.stem + ".sqlite")
    database.unlink(missing_ok=True)
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript("""
        CREATE TABLE Measurement (id INTEGER PRIMARY KEY, userId INTEGER, timestamp INTEGER);
        CREATE TABLE MeasurementType (id INTEGER PRIMARY KEY, key TEXT, unit TEXT);
        CREATE TABLE MeasurementValue (measurementId INTEGER, typeId INTEGER, floatValue REAL, intValue INTEGER);
        INSERT INTO MeasurementType VALUES (1, 'BODY_FAT', 'PERCENT');
    """)
    connection.execute("INSERT INTO MeasurementType VALUES (7, 'WEIGHT', ?)", (unit,))
    connection.commit()
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    if rows is None:
        rows = [(1, 1, stamp(13), 201.4), (2, 1, stamp(19), 199.1)]
    for measurement_id, user_id, timestamp, value in rows:
        connection.execute("INSERT INTO Measurement VALUES (?, ?, ?)",
                           (measurement_id, user_id, int(timestamp.timestamp() * 1000)))
        connection.execute("INSERT INTO MeasurementValue VALUES (?, 7, ?, NULL)",
                           (measurement_id, value))
        connection.execute("INSERT INTO MeasurementValue VALUES (?, 1, 22.5, NULL)", (measurement_id,))
    connection.commit()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for suffix in ("", "-wal", "-shm"):
            archive.write(str(database) + suffix, "openScale.db" + suffix)
    connection.close()
    return path


def test_reads_committed_wal_and_preserves_uploaded_archive_and_pounds(tmp_path):
    archive = write_backup(tmp_path / "backup.zip")
    original = archive.read_bytes()

    readings = weight.read_backup(archive)
    status = weight.build_status(readings, stamp(20))

    assert archive.read_bytes() == original
    assert status["measurementCount"] == 2  # No BODY_FAT values mixed in.
    assert status["lastWeightText"] == "199.1 lb"
    assert status["changeText"] == "−2.3 lb"
    assert status["lastDateText"] == "Yesterday"
    assert status["previousDateText"] == "Aug 13"
    assert status["lastMeasuredAt"] == stamp(19).astimezone(weight.timezone.utc).isoformat()


def test_selects_one_user_without_cross_user_comparisons(tmp_path):
    archive = write_backup(tmp_path / "backup.zip", rows=[
        (1, 1, stamp(10), 201.4),
        (2, 2, stamp(11), 160.0),
        (3, 1, stamp(12), 199.1),
    ])
    with pytest.raises(ValueError, match="WEIGHT_USER_ID"):
        weight.read_backup(archive)

    readings = weight.read_backup(archive, user_id=2)
    status = weight.build_status(readings, stamp(20))
    assert status["userId"] == 2
    assert status["lastWeightText"] == "160.0 lb"
    assert status["measurementCount"] == 1
    assert status["change"] is None
    assert status["changeText"] == "--"
    assert status["previousDateText"] == ""
    with pytest.raises(ValueError, match="No weight measurements"):
        weight.read_backup(archive, user_id=3)


@pytest.mark.parametrize("unit,value,symbol", [("KG", 90.3, "kg"), ("ST", 14.2, "st")])
def test_preserves_other_openscale_units(tmp_path, unit, value, symbol):
    archive = write_backup(tmp_path / "backup.zip", [(1, 1, stamp(19), value)], unit)
    status = weight.build_status(weight.read_backup(archive), stamp(20))
    assert status["lastWeightText"] == f"{value:.1f} {symbol}"


def test_invalid_readings_do_not_replace_real_weight(tmp_path):
    archive = write_backup(tmp_path / "backup.zip", rows=[
        (1, 1, stamp(10), 199.100014),
        (2, 1, stamp(11), 199.100006),
        (3, 1, stamp(12), None),
        (4, 1, stamp(13), 0),
        (5, 1, stamp(14), -1),
        (6, 1, stamp(15), float("inf")),
    ])
    status = weight.build_status(weight.read_backup(archive), stamp(20))
    assert status["measurementCount"] == 2
    assert status["lastDateText"] == "Aug 11"
    assert status["ageText"] == "9d ago"
    assert status["changeText"] == "0.0 lb"


@pytest.fixture
def configured_fetcher(tmp_path, monkeypatch):
    directory = tmp_path / "workouts" / "weight"
    directory.mkdir(parents=True)
    monkeypatch.setattr(weight.common, "load_env", lambda: None)
    monkeypatch.setattr(weight, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(weight, "STATUS_PATH", tmp_path / "weight-status.json")
    monkeypatch.setenv("WORKOUTS_DIR", str(directory.parent))
    monkeypatch.delenv("WEIGHT_DIR", raising=False)
    monkeypatch.delenv("WEIGHT_USER_ID", raising=False)
    return directory


def test_refresh_uses_newest_upload_and_survives_partial_replacement(configured_fetcher):
    directory = configured_fetcher
    old = write_backup(directory / "z-old.zip", [(1, 1, stamp(10), 205.0)])
    newest = write_backup(directory / "a-new.zip")
    os.utime(old, (100, 100))
    os.utime(newest, (200, 200))

    assert weight.main() == 0
    first = json.loads(weight.STATUS_PATH.read_text())
    assert first["sourceFile"] == "a-new.zip"
    assert first["lastWeight"] == 199.1

    newest.write_bytes(b"An upload is still in progress")
    assert weight.main() == 1
    stale = json.loads(weight.STATUS_PATH.read_text())
    assert stale["ok"] is True
    assert stale["stale"] is True
    assert stale["lastWeight"] == first["lastWeight"]
    assert stale["updatedAt"] == first["updatedAt"]

    write_backup(newest, [(3, 1, stamp(20), 200.0)])
    assert weight.main() == 0
    refreshed = json.loads(weight.STATUS_PATH.read_text())
    assert refreshed["lastWeight"] == 200.0
    assert refreshed["stale"] is False
    assert "error" not in refreshed


def test_missing_or_invalid_backup_reports_unavailable_without_zero_weight(configured_fetcher):
    assert weight.main() == 1
    missing = json.loads(weight.STATUS_PATH.read_text())
    assert missing["ok"] is False
    assert "No openScale backup" in missing["error"]
    assert "lastWeight" not in missing

    with zipfile.ZipFile(configured_fetcher / "wrong.zip", "w") as archive:
        archive.writestr("../../openScale.db", b"not an openScale database")
    assert weight.main() == 1
    invalid = json.loads(weight.STATUS_PATH.read_text())
    assert invalid["ok"] is False
    assert "does not contain openScale.db" in invalid["error"]


def test_old_readings_keep_the_year_in_the_date(tmp_path):
    archive = write_backup(tmp_path / "backup.zip")
    status = weight.build_status(weight.read_backup(archive), stamp(20) + timedelta(days=365))
    assert status["lastDateText"] == "Aug 19, 2026"
    assert status["previousDateText"] == "Aug 13, 2026"

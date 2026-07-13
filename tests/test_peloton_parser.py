"""Peloton CSV parser tests, driven by a synthetic workouts.csv export."""

from datetime import datetime
from pathlib import Path

from src.parsers.peloton_parser import map_peloton_discipline, parse_peloton_csv

FIXTURE = Path(__file__).parent / "fixtures" / "fixture_peloton.csv"


def load_workouts():
    return parse_peloton_csv(FIXTURE.read_text(encoding="utf-8"))


def test_row_count_skips_unusable_rows():
    # 5 data rows in the fixture; the blank 'Just Ride' row has no length and is skipped
    assert len(load_workouts()) == 4


def test_cycling_row():
    ride = load_workouts()[0]

    assert ride["workout_type"] == "bike"
    assert ride["start_time"] == datetime(2026, 1, 5, 6, 30)
    assert ride["duration_seconds"] == 30 * 60
    assert ride["title"] == "30 min Power Zone Ride"
    assert ride["instructor"] == "Test Instructor"
    assert ride["total_output"] == 412
    assert ride["avg_watts"] == 229
    assert ride["avg_resistance"] == 52  # '52%' in the export
    assert ride["avg_cadence_rpm"] == 88
    assert ride["distance_meters"] == int(9.61 * 1609.34)
    assert ride["calories"] == 438
    assert ride["avg_heart_rate"] == 151
    # Stable idempotency key
    assert ride["peloton_workout_id"] == "2026-01-05T06:30:00:cycling"


def test_running_row():
    run = load_workouts()[1]

    assert run["workout_type"] == "run"
    assert run["duration_seconds"] == 20 * 60
    assert run["distance_meters"] == int(2.05 * 1609.34)
    assert run["avg_heart_rate"] == 158
    assert run["avg_watts"] is None  # blank columns come back as None


def test_strength_and_yoga_rows():
    strength, yoga = load_workouts()[2], load_workouts()[3]

    assert strength["workout_type"] == "strength"
    assert strength["distance_meters"] is None
    assert yoga["workout_type"] == "yoga"
    assert yoga["calories"] == 56


def test_map_peloton_discipline():
    assert map_peloton_discipline("Cycling") == "bike"
    assert map_peloton_discipline("Running") == "run"
    assert map_peloton_discipline("Walking") == "walk"
    assert map_peloton_discipline("Stretching") == "flexibility"
    assert map_peloton_discipline("Bike Bootcamp") == "hiit"
    assert map_peloton_discipline("Meditation") == "other"
    assert map_peloton_discipline("Something New") == "other"

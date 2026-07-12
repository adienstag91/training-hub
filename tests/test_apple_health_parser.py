"""Apple Health parser tests, driven by a synthetic Health Auto Export JSON."""

from pathlib import Path

from src.parsers.apple_health_parser import map_apple_workout_type, parse_apple_health_json

FIXTURE = Path(__file__).parent / "fixtures" / "fixture_apple_health.json"


def test_parse_apple_health_json():
    workouts = parse_apple_health_json(FIXTURE.read_text(encoding="utf-8"))

    # Third entry has no start time and must be skipped
    assert len(workouts) == 2

    run, strength = workouts

    assert run["workout_type"] == "run"
    assert run["apple_workout_id"] == "FIXTURE-UUID-0001"
    assert run["duration_seconds"] == 1800
    assert run["distance_meters"] == 5000  # 2 x 2.5 km entries
    assert run["active_calories"] == 420
    assert run["avg_heart_rate"] == 152
    assert run["max_heart_rate"] == 178
    assert run["is_indoor"] is False

    assert strength["workout_type"] == "strength"
    # duration field is 0, so it falls back to end - start (45 min)
    assert strength["duration_seconds"] == 45 * 60
    assert strength["is_indoor"] is True


def test_map_apple_workout_type():
    assert map_apple_workout_type("Outdoor Run") == "run"
    assert map_apple_workout_type("Outdoor Walk") == "walk"
    assert map_apple_workout_type("Hiking") == "walk"
    assert map_apple_workout_type("Outdoor Cycling") == "bike"
    assert map_apple_workout_type("Traditional Strength Training") == "strength"
    assert map_apple_workout_type("HIIT") == "hiit"
    assert map_apple_workout_type("Yoga") == "yoga"
    assert map_apple_workout_type("Cooldown Stretch") == "flexibility"
    assert map_apple_workout_type("Table Tennis") == "other"


def test_stable_fallback_id_without_apple_id():
    """A workout without Apple's id must get a deterministic identifier."""
    from src.parsers.apple_health_parser import extract_workout_data

    workout = {
        "name": "Outdoor Run",
        "start": "2026-03-01 08:00:00 -0500",
        "end": "2026-03-01 08:30:00 -0500",
    }
    first = extract_workout_data(dict(workout))
    second = extract_workout_data(dict(workout))
    assert first["apple_workout_id"] == second["apple_workout_id"]
    assert first["apple_workout_id"] == "Outdoor Run:2026-03-01 08:00:00 -0500"

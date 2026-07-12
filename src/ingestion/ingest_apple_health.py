"""
Apple Health Ingestion
Ingests workouts from Health Auto Export JSON into the database
(raw JSON -> workout_session -> workout_component), idempotently.

Usage:
    python src/ingestion/ingest_apple_health.py path/to/HealthAutoExport.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import psycopg2.extras

# Add project root to path for imports when run as a script
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.apple_health_parser import parse_apple_health_json  # noqa: E402
from src.utils.db import get_db_connection  # noqa: E402


def ingest_apple_workout(workout_data):
    """
    Insert one parsed Apple Health workout (raw + session + component).

    Args:
        workout_data: standardized dict from apple_health_parser

    Returns:
        component id if inserted, None if skipped (duplicate)
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        apple_id = workout_data["apple_workout_id"]
        workout_date = workout_data["start_time"].date()

        # Step 1: Raw storage (idempotency anchor)
        cur.execute(
            """
            INSERT INTO apple_health_raw (apple_workout_id, fetched_at, raw_json)
            VALUES (%s, %s, %s)
            ON CONFLICT (apple_workout_id) DO NOTHING
            RETURNING id
            """,
            (
                apple_id,
                datetime.now(),
                psycopg2.extras.Json(workout_data.get("raw_data") or {}),
            ),
        )
        result = cur.fetchone()
        if not result:
            print(f"⚠️  Apple workout already ingested: {apple_id}")
            return None
        apple_health_raw_id = result[0]

        # Step 2: Workout session
        entity_key = f"workout:{workout_date.isoformat()}:apple:{apple_id}"
        source_metadata = {
            "name": workout_data["name"],
            "is_indoor": workout_data.get("is_indoor", False),
            "location": workout_data.get("location"),
            "avg_heart_rate": workout_data.get("avg_heart_rate"),
            "max_heart_rate": workout_data.get("max_heart_rate"),
            "distance_meters": workout_data.get("distance_meters"),
        }

        cur.execute(
            """
            INSERT INTO workout_session (
                apple_health_id, source_type, entity_key, workout_date,
                start_time, total_duration_seconds, total_calories, source_metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (entity_key) DO NOTHING
            RETURNING id
            """,
            (
                apple_health_raw_id,
                "apple_health",
                entity_key,
                workout_date,
                workout_data["start_time"],
                workout_data["duration_seconds"],
                workout_data.get("active_calories"),
                psycopg2.extras.Json(source_metadata),
            ),
        )
        result = cur.fetchone()
        if not result:
            print(f"⚠️  Session already exists: {entity_key}")
            conn.commit()  # keep the raw row
            return None
        session_id = result[0]

        # Step 3: Component
        workout_type = workout_data["workout_type"]
        component_entity_key = (
            f"workout:{workout_date.isoformat()}:apple_{workout_type}:{session_id}"
        )
        cur.execute(
            """
            INSERT INTO workout_component (
                workout_session_id, entity_key, component_type,
                duration_seconds, is_derived, sequence_order
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                session_id,
                component_entity_key,
                workout_type,
                workout_data["duration_seconds"],
                False,
                1,
            ),
        )
        component_id = cur.fetchone()[0]

        # Run detail when there's a distance to record
        if workout_type == "run" and workout_data.get("distance_meters", 0) > 0:
            cur.execute(
                """
                INSERT INTO run_component (
                    component_id, distance_meters, avg_heart_rate_bpm, max_heart_rate_bpm
                )
                VALUES (%s, %s, %s, %s)
                """,
                (
                    component_id,
                    workout_data["distance_meters"],
                    workout_data.get("avg_heart_rate"),
                    workout_data.get("max_heart_rate"),
                ),
            )

        conn.commit()
        print(
            f"✅ Ingested Apple workout: {workout_data['name']} "
            f"({workout_type}, {workout_data['duration_seconds']}s, session {session_id})"
        )
        return component_id

    except Exception as e:
        conn.rollback()
        print(f"❌ Error ingesting Apple workout: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def ingest_apple_health_file(filepath):
    """Parse a Health Auto Export JSON file and ingest every workout in it."""
    with open(filepath, "r", encoding="utf-8") as f:
        json_content = f.read()

    workouts = parse_apple_health_json(json_content)

    print("\n" + "=" * 70)
    print(f"APPLE HEALTH INGESTION — {len(workouts)} workout(s) in {Path(filepath).name}")
    print("=" * 70 + "\n")

    ingested = 0
    skipped = 0
    for workout_data in workouts:
        if ingest_apple_workout(workout_data):
            ingested += 1
        else:
            skipped += 1

    print("\n" + "=" * 70)
    print(f"SUMMARY: {ingested} ingested, {skipped} skipped")
    print("=" * 70 + "\n")
    return ingested, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Ingest Apple Health workouts (Health Auto Export JSON)"
    )
    parser.add_argument("json_file", help="Path to a Health Auto Export JSON file")
    args = parser.parse_args()
    ingest_apple_health_file(args.json_file)


if __name__ == "__main__":
    main()

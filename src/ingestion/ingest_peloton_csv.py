"""
Peloton CSV Ingestion
Ingests a Peloton workouts.csv export into the database
(raw row -> workout_session -> workout_component [+ detail]), idempotently.

Usage:
    python src/ingestion/ingest_peloton_csv.py path/to/workouts.csv
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import psycopg2.extras

# Add project root to path for imports when run as a script
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.peloton_parser import parse_peloton_csv  # noqa: E402
from src.utils.db import get_db_connection  # noqa: E402


def ingest_peloton_workout(workout):
    """
    Insert one parsed Peloton workout (raw + session + component + detail).

    Returns:
        session id if inserted, None if skipped (duplicate)
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        workout_id = workout["peloton_workout_id"]
        workout_date = workout["start_time"].date()

        # Step 1: Raw storage (idempotency anchor)
        cur.execute(
            """
            INSERT INTO peloton_workout_raw (peloton_workout_id, fetched_at, raw_json)
            VALUES (%s, %s, %s)
            ON CONFLICT (peloton_workout_id) DO NOTHING
            RETURNING id
            """,
            (workout_id, datetime.now(), psycopg2.extras.Json(workout["raw_row"])),
        )
        result = cur.fetchone()
        if not result:
            print(f"⚠️  Peloton workout already ingested: {workout_id}")
            return None
        peloton_raw_id = result[0]

        # Step 2: Workout session
        entity_key = f"workout:{workout_date.isoformat()}:peloton:{workout_id}"
        source_metadata = {
            "title": workout["title"],
            "instructor": workout["instructor"],
            "discipline": workout["discipline"],
            "live_or_ondemand": workout["live_or_ondemand"],
            "total_output": workout["total_output"],
            "avg_speed_mph": workout["avg_speed_mph"],
            "avg_heart_rate": workout["avg_heart_rate"],
            "distance_meters": workout["distance_meters"],
        }

        cur.execute(
            """
            INSERT INTO workout_session (
                peloton_workout_id, source_type, entity_key, workout_date,
                start_time, total_duration_seconds, total_calories, source_metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                peloton_raw_id,
                "peloton",
                entity_key,
                workout_date,
                workout["start_time"],
                workout["duration_seconds"],
                workout["calories"],
                psycopg2.extras.Json(source_metadata),
            ),
        )
        session_id = cur.fetchone()[0]

        # Step 3: Component (+ type-specific detail)
        workout_type = workout["workout_type"]
        component_entity_key = (
            f"workout:{workout_date.isoformat()}:peloton_{workout_type}:{session_id}"
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
            (session_id, component_entity_key, workout_type, workout["duration_seconds"], False, 1),
        )
        component_id = cur.fetchone()[0]

        if workout_type == "bike":
            cur.execute(
                """
                INSERT INTO bike_component (
                    component_id, distance_meters, avg_cadence_rpm,
                    avg_power_watts, avg_resistance, avg_heart_rate_bpm, instructor_name
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    component_id,
                    workout["distance_meters"],
                    workout["avg_cadence_rpm"],
                    workout["avg_watts"],
                    workout["avg_resistance"],
                    workout["avg_heart_rate"],
                    workout["instructor"],
                ),
            )
        elif workout_type == "run" and (workout["distance_meters"] or 0) > 0:
            cur.execute(
                """
                INSERT INTO run_component (component_id, distance_meters, avg_heart_rate_bpm)
                VALUES (%s, %s, %s)
                """,
                (component_id, workout["distance_meters"], workout["avg_heart_rate"]),
            )
        elif workout_type == "row" and (workout["distance_meters"] or 0) > 0:
            cur.execute(
                """
                INSERT INTO row_component (component_id, distance_meters, avg_watts)
                VALUES (%s, %s, %s)
                """,
                (component_id, workout["distance_meters"], workout["avg_watts"]),
            )

        conn.commit()
        title = workout["title"] or workout["discipline"]
        print(
            f"✅ Ingested Peloton workout: {title} "
            f"({workout_type}, {workout['duration_seconds']}s, session {session_id})"
        )
        return session_id

    except Exception as e:
        conn.rollback()
        print(f"❌ Error ingesting Peloton workout: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def ingest_peloton_csv_file(filepath):
    """Parse a Peloton workouts.csv export and ingest every workout in it."""
    with open(filepath, "r", encoding="utf-8-sig") as f:  # exports carry a BOM
        csv_content = f.read()

    workouts = parse_peloton_csv(csv_content)

    print("\n" + "=" * 70)
    print(f"PELOTON CSV INGESTION — {len(workouts)} workout(s) in {Path(filepath).name}")
    print("=" * 70 + "\n")

    ingested = 0
    skipped = 0
    for workout in workouts:
        if ingest_peloton_workout(workout):
            ingested += 1
        else:
            skipped += 1

    print("\n" + "=" * 70)
    print(f"SUMMARY: {ingested} ingested, {skipped} skipped")
    print("=" * 70 + "\n")
    return ingested, skipped


def main():
    parser = argparse.ArgumentParser(description="Ingest a Peloton workouts.csv export")
    parser.add_argument("csv_file", help="Path to workouts.csv (Profile -> Download Workouts)")
    args = parser.parse_args()
    ingest_peloton_csv_file(args.csv_file)


if __name__ == "__main__":
    main()

"""
OTF Email Ingestion Script v2
Parses OTF emails (parser v3: Message-ID + workout datetime from the email
itself) and inserts into component-specific tables with idempotency.

Usage:
    # Ingest a single email file
    python src/ingestion/ingest_otf_emails.py path/to/email.html

    # Ingest all emails from data/sample_data/otf/
    python src/ingestion/ingest_otf_emails.py
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import psycopg2.extras

# Add project root to path for imports when run as a script
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.parsers.otf_parser_v3 import parse_otf_email  # noqa: E402
from src.utils.db import get_db_connection  # noqa: E402

SAMPLE_DIR = PROJECT_ROOT / "data" / "sample_data" / "otf"


def ingest_otf_email(filepath):
    """
    Ingest an OTF email into the database (component-specific tables).

    The workout date/time and Message-ID come from the email itself
    (parser v3), so only the file path is needed.

    Returns:
        Dict with inserted IDs, or None if skipped (duplicate / unparseable)
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Read and parse email
        with open(filepath, "r", encoding="utf-8") as f:
            html_content = f.read()

        parsed = parse_otf_email(html_content)
        classification = parsed["classification"]

        # Extract message_id and workout_datetime from parsed email
        message_id = parsed["message_id"]
        workout_datetime = parsed["workout_datetime"]

        if not message_id:
            print("⚠️  Could not extract Message-ID from email")
            return None

        if not workout_datetime:
            print("⚠️  Could not extract workout date/time from email body")
            return None

        # Use parsed datetime (has both date and time)
        workout_date = workout_datetime.date()
        start_time = workout_datetime

        # ====================================================================
        # Step 1: Insert raw email (with idempotency check)
        # ====================================================================
        cur.execute(
            """
            INSERT INTO otf_email_raw (
                message_id, workout_date, received_at, subject,
                raw_html, parsed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (message_id, workout_date) DO NOTHING
            RETURNING id
            """,
            (
                message_id,
                workout_date,
                datetime.now(),
                "OTF Workout Summary",  # Generic subject
                html_content,
                datetime.now(),
            ),
        )

        result = cur.fetchone()
        if not result:
            print(f"⚠️  Email already ingested: {message_id} on {workout_date}")
            return None

        otf_email_id = result[0]
        print(f"✅ Inserted raw email (ID {otf_email_id})")

        # ====================================================================
        # Step 2: Insert workout session
        # ====================================================================
        entity_key = f"workout:{workout_date.isoformat()}:otf:default"

        source_metadata = {
            "splat_points": parsed.get("splat_points"),
            "evidence": classification["evidence"],
        }

        cur.execute(
            """
            INSERT INTO workout_session (
                otf_email_id, source_type, entity_key,
                workout_date, start_time, otf_class_type,
                total_duration_seconds, total_calories,
                source_metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                otf_email_id,
                "otf",
                entity_key,
                workout_date,
                start_time,
                classification["class_type"],
                classification["class_minutes"] * 60,
                parsed.get("total_calories"),
                psycopg2.extras.Json(source_metadata),
            ),
        )

        session_id = cur.fetchone()[0]
        print(
            f"✅ Inserted session: {classification['class_type']} "
            f"at {start_time.strftime('%I:%M %p')} (ID {session_id})"
        )

        # ====================================================================
        # Step 3: Insert workout components with type-specific details
        # ====================================================================
        components_inserted = []

        # Tread component
        if classification["tread_seconds"] > 0:
            tread_entity_key = f"workout:{workout_date.isoformat()}:otf_run:{session_id}"
            cur.execute(
                """
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, is_derived, sequence_order
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (session_id, tread_entity_key, "run", classification["tread_seconds"], False, 1),
            )
            run_component_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO run_component (component_id, distance_meters) VALUES (%s, %s)",
                (run_component_id, parsed["tread"]["distance_meters"]),
            )
            components_inserted.append(
                f"run (ID {run_component_id}, {parsed['tread']['distance_meters']}m)"
            )

        # Row component
        if classification["row_seconds"] > 0:
            row_entity_key = f"workout:{workout_date.isoformat()}:otf_row:{session_id}"
            cur.execute(
                """
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, is_derived, sequence_order
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (session_id, row_entity_key, "row", classification["row_seconds"], False, 2),
            )
            row_component_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO row_component (component_id, distance_meters) VALUES (%s, %s)",
                (row_component_id, parsed["row"]["total_distance_meters"]),
            )
            components_inserted.append(
                f"row (ID {row_component_id}, {parsed['row']['total_distance_meters']}m)"
            )

        # Strength component
        if classification["strength_seconds"] > 0:
            strength_entity_key = (
                f"workout:{workout_date.isoformat()}:otf_strength:{session_id}"
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
                    strength_entity_key,
                    "strength",
                    classification["strength_seconds"],
                    True,  # Strength time is derived (residual)
                    3,
                ),
            )
            strength_component_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO strength_component (component_id) VALUES (%s)",
                (strength_component_id,),
            )
            components_inserted.append(
                f"strength (ID {strength_component_id}, {classification['strength_seconds']}s)"
            )

        print(f"✅ Inserted components: {', '.join(components_inserted)}")

        conn.commit()

        return {
            "otf_email_id": otf_email_id,
            "session_id": session_id,
            "component_count": len(components_inserted),
        }

    except Exception as e:
        conn.rollback()
        print(f"❌ Error ingesting email: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def ingest_sample_emails():
    """Ingest all OTF emails from data/sample_data/otf/"""
    html_files = sorted(SAMPLE_DIR.glob("*.html")) if SAMPLE_DIR.exists() else []

    print("\n" + "=" * 70)
    print("OTF EMAIL INGESTION (Component-Specific Schema)")
    print("=" * 70 + "\n")

    if not html_files:
        print(
            f"No emails found in {SAMPLE_DIR}.\n"
            "Real emails are gitignored (personal data) — drop your own OTF\n"
            "emails there, or ingest a single file directly:\n"
            "  python src/ingestion/ingest_otf_emails.py <email.html>"
        )
        return

    total_success = 0
    total_skipped = 0

    for filepath in html_files:
        print(f"\n📧 Processing: {filepath.name}")
        result = ingest_otf_email(filepath)

        if result:
            print(
                f"   ✅ Success! Session ID: {result['session_id']}, "
                f"Components: {result['component_count']}\n"
            )
            total_success += 1
        else:
            total_skipped += 1

    print("\n" + "=" * 70)
    print(f"SUMMARY: {total_success} ingested, {total_skipped} skipped")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Ingest OTF emails into PostgreSQL")
    parser.add_argument("email_file", nargs="?", help="Path to an OTF email HTML file")
    args = parser.parse_args()

    if args.email_file:
        result = ingest_otf_email(args.email_file)
        if result:
            print(
                f"\n✅ Success! Session ID: {result['session_id']}, "
                f"Components: {result['component_count']}"
            )
    else:
        ingest_sample_emails()


if __name__ == "__main__":
    main()

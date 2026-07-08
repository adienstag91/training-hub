"""
OTF Email Ingestion Script
Parses OTF emails and inserts into PostgreSQL database with idempotency.

Usage:
    # Ingest a single email file
    python src/ingestion/ingest_otf_emails.py path/to/email.html 2026-07-01

    # Ingest all sample emails from data/sample_data/otf/
    python src/ingestion/ingest_otf_emails.py
"""

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg2
import psycopg2.extras

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # dotenv is a convenience, not a requirement

# Add src/ to path so the parser package imports when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from parsers.otf_parser import parse_otf_email  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DIR = REPO_ROOT / "data" / "sample_data" / "otf"


def get_db_connection():
    """Create a PostgreSQL connection from DATABASE_URL or DB_* env vars.

    Defaults match docker-compose.yml (localhost:5434 / training_hub).
    """
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)

    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5434")),
        database=os.environ.get("DB_NAME", "training_hub"),
        user=os.environ.get("DB_USER", "training_user"),
        password=os.environ.get("DB_PASSWORD", "training_pass"),
    )


def extract_message_id_from_file(filepath):
    """
    Extract Message-ID from email file.
    For now, use filename as a simple message_id.
    TODO: Parse actual email headers when using real emails.
    """
    filename = Path(filepath).stem
    return f"file:{filename}"


def ingest_otf_email(filepath, workout_date):
    """
    Ingest a single OTF email into the database.

    Args:
        filepath: Path to HTML email file
        workout_date: Date of workout (datetime.date)

    Returns:
        Dict with inserted IDs, or None if the email was already ingested
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Read email HTML
        with open(filepath, "r", encoding="utf-8") as f:
            html_content = f.read()

        # Extract message ID
        message_id = extract_message_id_from_file(filepath)

        # Parse email
        parsed = parse_otf_email(html_content, message_id)
        classification = parsed["classification"]

        # Step 1: Insert raw email (with idempotency check)
        cur.execute(
            """
            INSERT INTO otf_email_raw (message_id, workout_date, received_at, subject, raw_html, parsed_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (message_id, workout_date) DO NOTHING
            RETURNING id
            """,
            (
                message_id,
                workout_date,
                datetime.now(),
                parsed.get("subject") or "OTF Workout",
                html_content,
                datetime.now(),
            ),
        )

        result = cur.fetchone()
        if not result:
            print(f"⚠️  Email already ingested: {message_id} on {workout_date}")
            return None

        otf_email_id = result[0]
        print(f"✅ Inserted raw email: ID {otf_email_id}")

        # Step 2: Insert workout session
        entity_key = f"workout:{workout_date.isoformat()}:otf:default"

        cur.execute(
            """
            INSERT INTO workout_session (
                otf_email_id, source_type, entity_key, workout_date,
                class_type, class_minutes, total_calories, splat_points,
                classification_evidence
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                otf_email_id,
                "otf",
                entity_key,
                workout_date,
                classification["class_type"],
                classification["class_minutes"],
                parsed.get("total_calories"),
                parsed.get("splat_points"),
                psycopg2.extras.Json(classification["evidence"]),
            ),
        )

        session_id = cur.fetchone()[0]
        print(f"✅ Inserted session: {classification['class_type']} (ID {session_id})")

        # Step 3: Insert workout components
        components_inserted = []

        # Insert tread component (if exists)
        if classification["tread_seconds"] > 0:
            tread_entity_key = f"workout:{workout_date.isoformat()}:otf_run:{session_id}"
            cur.execute(
                """
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, distance_meters, is_derived
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    session_id,
                    tread_entity_key,
                    "run",
                    classification["tread_seconds"],
                    parsed["tread"].get("distance_meters"),
                    False,
                ),
            )
            comp_id = cur.fetchone()[0]
            components_inserted.append(f"run (ID {comp_id})")

        # Insert row component (if exists)
        if classification["row_seconds"] > 0:
            row_entity_key = f"workout:{workout_date.isoformat()}:otf_row:{session_id}"
            cur.execute(
                """
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, distance_meters, is_derived
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    session_id,
                    row_entity_key,
                    "row",
                    classification["row_seconds"],
                    parsed["row"].get("total_distance_meters"),
                    False,
                ),
            )
            comp_id = cur.fetchone()[0]
            components_inserted.append(f"row (ID {comp_id})")

        # Insert strength component (if exists)
        if classification["strength_seconds"] > 0:
            strength_entity_key = f"workout:{workout_date.isoformat()}:otf_strength:{session_id}"
            cur.execute(
                """
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, distance_meters, is_derived
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    session_id,
                    strength_entity_key,
                    "strength",
                    classification["strength_seconds"],
                    None,  # No distance for strength
                    True,  # Strength time is derived
                ),
            )
            comp_id = cur.fetchone()[0]
            components_inserted.append(f"strength (ID {comp_id})")

        print(f"✅ Inserted components: {', '.join(components_inserted)}")

        # Commit transaction
        conn.commit()

        return {
            "otf_email_id": otf_email_id,
            "session_id": session_id,
            "components": len(components_inserted),
        }

    except Exception as e:
        conn.rollback()
        print(f"❌ Error ingesting email: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def ingest_sample_emails():
    """Ingest all sample emails from data/sample_data/otf/"""
    # Map filenames to dates (in real life, parse from email headers)
    emails = [
        ("sample_90_min.html", date(2025, 12, 6)),
        ("sample_60_min.html", date(2025, 12, 5)),
        ("sample_tread50.html", date(2025, 12, 4)),
    ]

    print("\n" + "=" * 60)
    print("OTF EMAIL INGESTION")
    print("=" * 60 + "\n")

    found_any = False
    for filename, workout_date in emails:
        filepath = SAMPLE_DIR / filename
        if not filepath.exists():
            print(f"⚠️  File not found: {filepath}")
            continue

        found_any = True
        print(f"\n📧 Processing: {filename}")
        print(f"   Date: {workout_date}")
        result = ingest_otf_email(filepath, workout_date)

        if result:
            print(
                f"   ✅ Success! Session ID: {result['session_id']}, "
                f"Components: {result['components']}\n"
            )

    if not found_any:
        print(
            f"\nNo sample emails found in {SAMPLE_DIR}.\n"
            "Sample emails are gitignored (personal data) — drop your own OTF\n"
            "emails there, or ingest a single file directly:\n"
            "  python src/ingestion/ingest_otf_emails.py <email.html> <YYYY-MM-DD>"
        )


def main():
    parser = argparse.ArgumentParser(description="Ingest OTF emails into PostgreSQL")
    parser.add_argument("email_file", nargs="?", help="Path to an OTF email HTML file")
    parser.add_argument("workout_date", nargs="?", help="Workout date (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.email_file:
        if not args.workout_date:
            parser.error("workout_date (YYYY-MM-DD) is required when ingesting a file")
        workout_date = date.fromisoformat(args.workout_date)
        ingest_otf_email(args.email_file, workout_date)
    else:
        ingest_sample_emails()


if __name__ == "__main__":
    main()

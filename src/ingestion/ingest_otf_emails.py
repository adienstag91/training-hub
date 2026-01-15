"""
OTF Email Ingestion Script
Parses OTF emails and inserts into PostgreSQL database with idempotency.
"""

import sys
import os
import psycopg2
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from parsers.otf_parser import parse_otf_email


def get_db_connection():
    """Create PostgreSQL database connection."""
    return psycopg2.connect(
        host="localhost",
        database="training_hub",
        user=os.environ.get('USER'),  # Your Mac username
        password=""  # No password for local Postgres
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
        Dict with inserted IDs
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Read email HTML
        with open(filepath, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Extract message ID
        message_id = extract_message_id_from_file(filepath)
        
        # Parse email
        parsed = parse_otf_email(html_content, message_id)
        classification = parsed['classification']
        
        # Step 1: Insert raw email (with idempotency check)
        cur.execute("""
            INSERT INTO otf_email_raw (message_id, workout_date, received_at, subject, raw_html, parsed_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (message_id, workout_date) DO NOTHING
            RETURNING id
        """, (
            message_id,
            workout_date,
            datetime.now(),
            parsed.get('subject', 'OTF Workout'),
            html_content,
            datetime.now()
        ))
        
        result = cur.fetchone()
        if not result:
            print(f"⚠️  Email already ingested: {message_id} on {workout_date}")
            conn.close()
            return None
        
        otf_email_id = result[0]
        print(f"✅ Inserted raw email: ID {otf_email_id}")
        
        # Step 2: Insert workout session
        entity_key = f"workout:{workout_date.isoformat()}:otf:default"
        
        cur.execute("""
            INSERT INTO workout_session (
                otf_email_id, source_type, entity_key, workout_date,
                class_type, class_minutes, total_calories, splat_points,
                classification_evidence
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            otf_email_id,
            'otf',
            entity_key,
            workout_date,
            classification['class_type'],
            classification['class_minutes'],
            parsed.get('total_calories'),
            parsed.get('splat_points'),
            psycopg2.extras.Json(classification['evidence'])
        ))
        
        session_id = cur.fetchone()[0]
        print(f"✅ Inserted session: {classification['class_type']} (ID {session_id})")
        
        # Step 3: Insert workout components
        components_inserted = []
        
        # Insert tread component (if exists)
        if classification['tread_seconds'] > 0:
            tread_entity_key = f"workout:{workout_date.isoformat()}:otf_run:{session_id}"
            cur.execute("""
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, distance_meters, is_derived
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                session_id,
                tread_entity_key,
                'run',
                classification['tread_seconds'],
                parsed['tread'].get('distance_meters'),
                False
            ))
            comp_id = cur.fetchone()[0]
            components_inserted.append(f"run (ID {comp_id})")
        
        # Insert row component (if exists)
        if classification['row_seconds'] > 0:
            row_entity_key = f"workout:{workout_date.isoformat()}:otf_row:{session_id}"
            cur.execute("""
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, distance_meters, is_derived
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                session_id,
                row_entity_key,
                'row',
                classification['row_seconds'],
                parsed['row'].get('total_distance_meters'),
                False
            ))
            comp_id = cur.fetchone()[0]
            components_inserted.append(f"row (ID {comp_id})")
        
        # Insert strength component (if exists)
        if classification['strength_seconds'] > 0:
            strength_entity_key = f"workout:{workout_date.isoformat()}:otf_strength:{session_id}"
            cur.execute("""
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, distance_meters, is_derived
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                session_id,
                strength_entity_key,
                'strength',
                classification['strength_seconds'],
                None,  # No distance for strength
                True   # Strength time is derived
            ))
            comp_id = cur.fetchone()[0]
            components_inserted.append(f"strength (ID {comp_id})")
        
        print(f"✅ Inserted components: {', '.join(components_inserted)}")
        
        # Commit transaction
        conn.commit()
        
        return {
            'otf_email_id': otf_email_id,
            'session_id': session_id,
            'components': len(components_inserted)
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
    sample_dir = Path(__file__).parent.parent / 'data' / 'sample_emails'
    
    # Map filenames to dates (in real life, parse from email headers)
    emails = [
        ('sample_90_min.html', datetime(2025, 12, 6).date()),
        ('sample_60_min.html', datetime(2025, 12, 5).date()),
        ('sample_tread50.html', datetime(2025, 12, 4).date()),
    ]
    
    print("\n" + "="*60)
    print("OTF EMAIL INGESTION")
    print("="*60 + "\n")
    
    for filename, workout_date in emails:
        filepath = sample_dir / filename
        if not filepath.exists():
            print(f"⚠️  File not found: {filepath}")
            continue
        
        print(f"\n📧 Processing: {filename}")
        print(f"   Date: {workout_date}")
        result = ingest_otf_email(filepath, workout_date)
        
        if result:
            print(f"   ✅ Success! Session ID: {result['session_id']}, "
                  f"Components: {result['components']}\n")


if __name__ == '__main__':
    ingest_sample_emails()

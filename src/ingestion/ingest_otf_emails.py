"""
OTF Email Ingestion Script v2
Inserts parsed OTF data into component-specific tables.
"""

import sys
import os
import psycopg2
import psycopg2.extras
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Get project root (training-hub directory)
PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_PATH = PROJECT_ROOT / '.env'

# Load environment variables from project root
load_dotenv(ENV_PATH)

# Add parent directory to path for imports
sys.path.insert(0, str(PROJECT_ROOT))
from src.parsers.otf_parser_v3 import parse_otf_email


def get_db_connection():
    """Create PostgreSQL database connection."""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        database=os.getenv('POSTGRES_DB', 'training_hub'),
        user=os.getenv('POSTGRES_USER', os.environ.get('USER')),
        password=os.getenv('POSTGRES_PASSWORD')
    )


def ingest_otf_email(filepath, workout_date=None):
    """
    Ingest OTF email into database with component-specific tables.
    
    Args:
        filepath: Path to HTML email file
        workout_date: Optional - if None, will use date from email body
    
    Returns:
        Dict with inserted IDs
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Read and parse email
        with open(filepath, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        parsed = parse_otf_email(html_content)
        classification = parsed['classification']
        
        # Extract message_id and workout_datetime from parsed email
        message_id = parsed['message_id']
        workout_datetime = parsed['workout_datetime']
        
        if not message_id:
            print(f"⚠️  Could not extract Message-ID from email")
            return None
        
        if not workout_datetime:
            print(f"⚠️  Could not extract workout date/time from email body")
            return None
        
        # Use parsed datetime (has both date and time)
        workout_date = workout_datetime.date()
        start_time = workout_datetime
        
        # ====================================================================
        # Step 1: Insert raw email (with idempotency check)
        # ====================================================================
        cur.execute("""
            INSERT INTO otf_email_raw (
                message_id, workout_date, received_at, subject, 
                raw_html, parsed_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (message_id, workout_date) DO NOTHING
            RETURNING id
        """, (
            message_id,
            workout_date,
            datetime.now(),
            'OTF Workout Summary',  # Generic subject
            html_content,
            datetime.now()
        ))
        
        result = cur.fetchone()
        if not result:
            print(f"⚠️  Email already ingested: {message_id} on {workout_date}")
            conn.close()
            return None
        
        otf_email_id = result[0]
        print(f"✅ Inserted raw email (ID {otf_email_id})")
        
        # ====================================================================
        # Step 2: Insert workout session
        # ====================================================================
        entity_key = f"workout:{workout_date.isoformat()}:otf:default"
        
        # Build source_metadata JSON
        source_metadata = {
            'splat_points': parsed.get('splat_points'),
            'evidence': classification['evidence']
        }
        
        cur.execute("""
            INSERT INTO workout_session (
                otf_email_id, source_type, entity_key, 
                workout_date, start_time, otf_class_type, 
                total_duration_seconds, total_calories,
                source_metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            otf_email_id,
            'otf',
            entity_key,
            workout_date,
            start_time,  # Now populated with actual class start time!
            classification['class_type'],
            classification['class_minutes'] * 60,  # Convert to seconds
            parsed.get('total_calories'),
            psycopg2.extras.Json(source_metadata)
        ))
        
        session_id = cur.fetchone()[0]
        print(f"✅ Inserted session: {classification['class_type']} at {start_time.strftime('%I:%M %p')} (ID {session_id})")
        
        # ====================================================================
        # Step 3: Insert workout components with type-specific details
        # ====================================================================
        components_inserted = []
        
        # -------------------------------------------------------------------
        # TREAD COMPONENT (if exists)
        # -------------------------------------------------------------------
        if classification['tread_seconds'] > 0:
            # Insert base component
            tread_entity_key = f"workout:{workout_date.isoformat()}:otf_run:{session_id}"
            cur.execute("""
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, is_derived, sequence_order
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                session_id,
                tread_entity_key,
                'run',
                classification['tread_seconds'],
                False,
                1  # First component in OTF session
            ))
            run_component_id = cur.fetchone()[0]
            
            # Insert run-specific details
            cur.execute("""
                INSERT INTO run_component (
                    component_id, distance_meters
                )
                VALUES (%s, %s)
            """, (
                run_component_id,
                parsed['tread']['distance_meters']
            ))
            
            components_inserted.append(f"run (ID {run_component_id}, {parsed['tread']['distance_meters']}m)")
        
        # -------------------------------------------------------------------
        # ROW COMPONENT (if exists)
        # -------------------------------------------------------------------
        if classification['row_seconds'] > 0:
            # Insert base component
            row_entity_key = f"workout:{workout_date.isoformat()}:otf_row:{session_id}"
            cur.execute("""
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, is_derived, sequence_order
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                session_id,
                row_entity_key,
                'row',
                classification['row_seconds'],
                False,
                2  # Second component
            ))
            row_component_id = cur.fetchone()[0]
            
            # Insert row-specific details
            cur.execute("""
                INSERT INTO row_component (
                    component_id, distance_meters
                )
                VALUES (%s, %s)
            """, (
                row_component_id,
                parsed['row']['total_distance_meters']
            ))
            
            components_inserted.append(f"row (ID {row_component_id}, {parsed['row']['total_distance_meters']}m)")
        
        # -------------------------------------------------------------------
        # STRENGTH COMPONENT (if exists)
        # -------------------------------------------------------------------
        if classification['strength_seconds'] > 0:
            # Insert base component
            strength_entity_key = f"workout:{workout_date.isoformat()}:otf_strength:{session_id}"
            cur.execute("""
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, is_derived, sequence_order
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                session_id,
                strength_entity_key,
                'strength',
                classification['strength_seconds'],
                True,  # Strength time is derived (residual)
                3  # Third component
            ))
            strength_component_id = cur.fetchone()[0]
            
            # Insert strength-specific details (minimal for now)
            cur.execute("""
                INSERT INTO strength_component (
                    component_id
                )
                VALUES (%s)
            """, (
                strength_component_id,
            ))
            
            components_inserted.append(f"strength (ID {strength_component_id}, {classification['strength_seconds']}s)")
        
        print(f"✅ Inserted components: {', '.join(components_inserted)}")
        
        # Commit transaction
        conn.commit()
        
        return {
            'otf_email_id': otf_email_id,
            'session_id': session_id,
            'component_count': len(components_inserted)
        }
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error ingesting email: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        cur.close()
        conn.close()


def ingest_sample_emails():
    """Ingest all sample OTF emails."""
    sample_dir = PROJECT_ROOT / 'data' / 'sample_otf_emails'
    
    # Just list the files - dates will be extracted from email body
    emails = [
        'sample_90_min.html',
        'sample_60_min.html',
        'sample_tread50.html',
    ]
    
    print("\n" + "="*70)
    print("OTF EMAIL INGESTION (Component-Specific Schema)")
    print("="*70 + "\n")
    
    total_success = 0
    total_skipped = 0
    
    for filename in emails:
        filepath = sample_dir / filename
        if not filepath.exists():
            print(f"⚠️  File not found: {filepath}")
            continue
        
        print(f"\n📧 Processing: {filename}")
        
        result = ingest_otf_email(filepath)
        
        if result:
            print(f"   ✅ Success! Session ID: {result['session_id']}, "
                  f"Components: {result['component_count']}\n")
            total_success += 1
        else:
            total_skipped += 1
    
    print("\n" + "="*70)
    print(f"SUMMARY: {total_success} ingested, {total_skipped} skipped")
    print("="*70 + "\n")


if __name__ == '__main__':
    ingest_sample_emails()

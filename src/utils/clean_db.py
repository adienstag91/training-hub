"""
Database Cleanup Utility
Wipes data from training_hub tables for testing.
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

# Get project root (training-hub directory)
PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_PATH = PROJECT_ROOT / '.env'

# Load environment variables from project root
load_dotenv(ENV_PATH)


def get_db_connection():
    """Create PostgreSQL database connection."""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        database=os.getenv('POSTGRES_DB', 'training_hub'),
        user=os.getenv('POSTGRES_USER', os.environ.get('USER')),
        password=os.getenv('POSTGRES_PASSWORD')
    )


def truncate_all_tables():
    """
    Truncate all data tables (keeps schema).
    Uses CASCADE to handle foreign key constraints.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        print("\n" + "="*70)
        print("DATABASE CLEANUP - TRUNCATE ALL TABLES")
        print("="*70 + "\n")
        
        # Truncate in correct order (or use CASCADE)
        # CASCADE automatically handles dependencies
        tables = [
            'strava_activity_publish',
            'strength_component',
            'bike_component',
            'row_component',
            'run_component',
            'workout_component',
            'workout_session',
            'otf_email_raw',
            'strava_activity_raw',
            'peloton_workout_raw'
        ]
        
        for table in tables:
            cur.execute(f"TRUNCATE TABLE {table} CASCADE")
            print(f"✅ Truncated: {table}")
        
        conn.commit()
        
        print("\n" + "="*70)
        print("✅ All tables cleaned successfully!")
        print("="*70 + "\n")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error truncating tables: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def reset_sequences():
    """
    Reset all ID sequences back to 1.
    Useful after truncating to start IDs fresh.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        print("\n" + "="*70)
        print("RESETTING ID SEQUENCES")
        print("="*70 + "\n")
        
        sequences = [
            'otf_email_raw_id_seq',
            'strava_activity_raw_id_seq',
            'peloton_workout_raw_id_seq',
            'workout_session_id_seq',
            'workout_component_id_seq',
            'run_component_id_seq',
            'row_component_id_seq',
            'bike_component_id_seq',
            'strength_component_id_seq',
            'strava_activity_publish_id_seq'
        ]
        
        for seq in sequences:
            cur.execute(f"ALTER SEQUENCE {seq} RESTART WITH 1")
            print(f"✅ Reset: {seq}")
        
        conn.commit()
        
        print("\n" + "="*70)
        print("✅ All sequences reset to 1!")
        print("="*70 + "\n")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error resetting sequences: {e}")
        raise
    finally:
        cur.close()
        conn.close()


def show_table_counts():
    """Display row counts for all tables."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        print("\n" + "="*70)
        print("TABLE ROW COUNTS")
        print("="*70 + "\n")
        
        tables = [
            'otf_email_raw',
            'workout_session',
            'workout_component',
            'run_component',
            'row_component',
            'bike_component',
            'strength_component',
            'strava_activity_publish'
        ]
        
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"  {table:30s} {count:5d} rows")
        
        print("\n" + "="*70 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error getting counts: {e}")
    finally:
        cur.close()
        conn.close()


def clean_database(reset_ids=True):
    """
    Complete database cleanup: truncate tables and optionally reset IDs.
    
    Args:
        reset_ids: If True, reset ID sequences to 1
    """
    print("\n⚠️  WARNING: This will delete ALL data from the database!")
    response = input("Continue? (yes/no): ").strip().lower()
    
    if response != 'yes':
        print("❌ Cancelled.")
        return
    
    # Show before counts
    print("\n📊 BEFORE:")
    show_table_counts()
    
    # Truncate tables
    truncate_all_tables()
    
    # Reset sequences if requested
    if reset_ids:
        reset_sequences()
    
    # Show after counts
    print("\n📊 AFTER:")
    show_table_counts()


if __name__ == '__main__':
    import sys
    
    # Allow command-line options
    if len(sys.argv) > 1:
        if sys.argv[1] == '--no-reset':
            # Truncate but keep ID sequence
            clean_database(reset_ids=False)
        elif sys.argv[1] == '--counts':
            # Just show counts
            show_table_counts()
        elif sys.argv[1] == '--force':
            # Skip confirmation
            show_table_counts()
            truncate_all_tables()
            reset_sequences()
            show_table_counts()
        else:
            print("Usage:")
            print("  python clean_db.py              # Clean with confirmation")
            print("  python clean_db.py --no-reset   # Keep ID sequences")
            print("  python clean_db.py --counts     # Just show counts")
            print("  python clean_db.py --force      # Skip confirmation")
    else:
        # Normal interactive mode
        clean_database(reset_ids=True)

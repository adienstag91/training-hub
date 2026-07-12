"""
Training Hub Webhook Server
Receives OTF emails from Zapier and auto-ingests to DB + Strava.
"""

import os
import sys
import json
from pathlib import Path
from flask import Flask, request, jsonify
from datetime import datetime
from dotenv import load_dotenv

# Get project root and load environment
PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_PATH = PROJECT_ROOT / '.env'
load_dotenv(ENV_PATH)

# Add project to path
sys.path.insert(0, str(PROJECT_ROOT))

# Import our existing functions
from src.parsers.otf_parser_v3 import parse_otf_email
from src.strava.publish_to_strava import get_strava_client, publish_component_to_strava
import psycopg2
import psycopg2.extras

# Initialize Flask app
app = Flask(__name__)

# Configure logging
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Create PostgreSQL database connection."""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        database=os.getenv('POSTGRES_DB', 'training_hub'),
        user=os.getenv('POSTGRES_USER', os.environ.get('USER')),
        password=os.getenv('POSTGRES_PASSWORD')
    )


def ingest_email_to_db(html_content):
    """
    Ingest OTF email into database.
    Returns list of component IDs created.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Parse email
        parsed = parse_otf_email(html_content)
        classification = parsed['classification']
        
        message_id = parsed['message_id']
        workout_datetime = parsed['workout_datetime']
        
        if not message_id or not workout_datetime:
            raise Exception("Could not parse message_id or workout_datetime")
        
        workout_date = workout_datetime.date()
        start_time = workout_datetime
        
        # Insert raw email
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
            'OTF Workout Summary',
            html_content,
            datetime.now()
        ))
        
        result = cur.fetchone()
        if not result:
            logger.info(f"Email already ingested: {message_id} on {workout_date}")
            conn.close()
            return []  # Already exists, skip
        
        otf_email_id = result[0]
        logger.info(f"Inserted raw email (ID {otf_email_id})")
        
        # Insert workout session
        entity_key = f"workout:{workout_date.isoformat()}:otf:default"
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
            start_time,
            classification['class_type'],
            classification['class_minutes'] * 60,
            parsed.get('total_calories'),
            psycopg2.extras.Json(source_metadata)
        ))
        
        session_id = cur.fetchone()[0]
        logger.info(f"Inserted session: {classification['class_type']} at {start_time.strftime('%I:%M %p')} (ID {session_id})")
        
        # Insert components
        component_ids = []
        
        # Tread component
        if classification['tread_seconds'] > 0:
            tread_entity_key = f"workout:{workout_date.isoformat()}:otf_run:{session_id}"
            cur.execute("""
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, is_derived, sequence_order
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                session_id, tread_entity_key, 'run',
                classification['tread_seconds'], False, 1
            ))
            run_component_id = cur.fetchone()[0]
            
            cur.execute("""
                INSERT INTO run_component (component_id, distance_meters)
                VALUES (%s, %s)
            """, (run_component_id, parsed['tread']['distance_meters']))
            
            component_ids.append(run_component_id)
            logger.info(f"Inserted run component (ID {run_component_id})")
        
        # Row component
        if classification['row_seconds'] > 0:
            row_entity_key = f"workout:{workout_date.isoformat()}:otf_row:{session_id}"
            cur.execute("""
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, is_derived, sequence_order
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                session_id, row_entity_key, 'row',
                classification['row_seconds'], False, 2
            ))
            row_component_id = cur.fetchone()[0]
            
            cur.execute("""
                INSERT INTO row_component (component_id, distance_meters)
                VALUES (%s, %s)
            """, (row_component_id, parsed['row']['total_distance_meters']))
            
            component_ids.append(row_component_id)
            logger.info(f"Inserted row component (ID {row_component_id})")
        
        # Strength component
        if classification['strength_seconds'] > 0:
            strength_entity_key = f"workout:{workout_date.isoformat()}:otf_strength:{session_id}"
            cur.execute("""
                INSERT INTO workout_component (
                    workout_session_id, entity_key, component_type,
                    duration_seconds, is_derived, sequence_order
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                session_id, strength_entity_key, 'strength',
                classification['strength_seconds'], True, 3
            ))
            strength_component_id = cur.fetchone()[0]
            
            cur.execute("""
                INSERT INTO strength_component (component_id)
                VALUES (%s)
            """, (strength_component_id,))
            
            component_ids.append(strength_component_id)
            logger.info(f"Inserted strength component (ID {strength_component_id})")
        
        conn.commit()
        return component_ids
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error ingesting email: {e}")
        raise
    finally:
        cur.close()
        conn.close()


@app.route('/')
def home():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'service': 'Training Hub Webhook',
        'version': '1.0'
    })


@app.route('/ingest/apple', methods=['POST'])
def ingest_apple_workout():
    """
    Webhook endpoint for Apple Health JSON files.
    Does NOT auto-publish to Strava (Apple Fitness syncs separately).
    
    Expected JSON payload - either:
    1. Direct workout data from iPhone Shortcuts
    2. Health Auto Export JSON file content
    """
    try:
        # Get JSON payload
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        logger.info("Received Apple Health data")
        
        # Check if this is Health Auto Export format or direct workout data
        if 'data' in data and 'workouts' in data['data']:
            # Health Auto Export format
            from src.parsers.apple_health_parser import parse_apple_health_json
            workouts = parse_apple_health_json(json.dumps(data))
            
            component_ids = []
            for workout_data in workouts:
                comp_id = ingest_apple_workout_to_db(workout_data)
                if comp_id:
                    component_ids.append(comp_id)
            
            return jsonify({
                'success': True,
                'message': f'Ingested {len(workouts)} Apple workouts (no Strava sync)',
                'components_created': len(component_ids)
            })
            
        else:
            # Direct workout data format (future iPhone Shortcuts)
            comp_id = ingest_apple_workout_to_db(data)
            
            return jsonify({
                'success': True,
                'message': 'Apple workout ingested (no Strava sync)',
                'components_created': 1 if comp_id else 0
            })
        
    except Exception as e:
        logger.error(f"Error processing Apple workout: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


def ingest_apple_workout_to_db(workout_data):
    """
    Insert Apple workout into database.
    Returns component ID if successful, None if failed/duplicate.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Create entity key for idempotency
        workout_date = workout_data['start_time'].date()
        apple_id = workout_data.get('apple_workout_id', 'unknown')
        entity_key = f"workout:{workout_date.isoformat()}:apple:{apple_id}"
        
        # Insert workout session
        cur.execute("""
            INSERT INTO workout_session (
                source_type, entity_key, workout_date, start_time,
                total_duration_seconds, total_calories, source_metadata, apple_health_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (entity_key) DO NOTHING
            RETURNING id
        """, (
            'apple_health',
            entity_key,
            workout_date,
            workout_data['start_time'],
            workout_data['duration_seconds'],
            workout_data.get('active_calories'),
            psycopg2.extras.Json({
                'apple_workout_id': apple_id,
                'name': workout_data['name'],
                'is_indoor': workout_data.get('is_indoor', False),
                'location': workout_data.get('location'),
                'avg_heart_rate': workout_data.get('avg_heart_rate'),
                'max_heart_rate': workout_data.get('max_heart_rate')
            }),
            apple_id  # Set apple_health_id for the constraint
        ))
        
        result = cur.fetchone()
        if not result:
            logger.info(f"Apple workout already exists: {entity_key}")
            return None
            
        session_id = result[0]
        logger.info(f"Created Apple workout session (ID {session_id}): {workout_data['name']}")
        
        # Insert component based on workout type
        component_entity_key = f"workout:{workout_date.isoformat()}:apple_{workout_data['workout_type']}:{session_id}"
        
        cur.execute("""
            INSERT INTO workout_component (
                workout_session_id, entity_key, component_type,
                duration_seconds, is_derived, sequence_order
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            session_id, component_entity_key, workout_data['workout_type'],
            workout_data['duration_seconds'], False, 1
        ))
        
        component_id = cur.fetchone()[0]
        
        # Insert type-specific data if applicable
        if workout_data['workout_type'] == 'run' and workout_data.get('distance_meters', 0) > 0:
            cur.execute("""
                INSERT INTO run_component (component_id, distance_meters)
                VALUES (%s, %s)
            """, (component_id, workout_data['distance_meters']))
        
        conn.commit()
        logger.info(f"Created Apple {workout_data['workout_type']} component (ID {component_id})")
        
        return component_id
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error ingesting Apple workout: {e}")
        raise
    finally:
        cur.close()
        conn.close()


@app.route('/ingest', methods=['POST'])
def ingest_otf_email():
    """
    Webhook endpoint for Zapier to send OTF emails.
    
    Accepts both JSON and form data.
    Expected fields:
    {
        "html": "<full email html content>",
        "subject": "Optional email subject",
        "from": "Optional sender email",
        "date": "Optional email date"
    }
    """
    try:
        # Get data from either JSON or form
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form.to_dict()
        
        if not data or 'html' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing "html" field in request'
            }), 400
        
        html_content = data['html']
        
        # Generate a synthetic message_id if Gmail body doesn't have headers
        # Use combination of date + sender to create unique ID
        email_date = data.get('date', '')
        email_from = data.get('from', '')
        
        # Add synthetic headers to HTML if not present
        if 'Message-ID:' not in html_content:
            # Generate unique message_id from date/sender
            import hashlib
            unique_str = f"{email_date}:{email_from}:{html_content[:100]}"
            synthetic_id = hashlib.md5(unique_str.encode()).hexdigest()
            
            # Prepend headers
            synthetic_headers = f"""Message-ID: <{synthetic_id}@zapier.traininghub>
Date: {email_date}
From: {email_from}

"""
            html_content = synthetic_headers + html_content
        
        logger.info("Received OTF email from Zapier")
        
        # Ingest to database
        component_ids = ingest_email_to_db(html_content)
        
        if not component_ids:
            return jsonify({
                'success': True,
                'message': 'Email already ingested (duplicate)',
                'components_created': 0
            })
        
        logger.info(f"Created {len(component_ids)} components: {component_ids}")
        
        # Auto-publish to Strava
        strava_client = get_strava_client()
        strava_activities = []
        
        for comp_id in component_ids:
            try:
                strava_id = publish_component_to_strava(comp_id, strava_client)
                if strava_id:
                    strava_activities.append(strava_id)
                    logger.info(f"Published component {comp_id} to Strava (activity {strava_id})")
            except Exception as e:
                logger.error(f"Failed to publish component {comp_id}: {e}")
        
        return jsonify({
            'success': True,
            'message': 'Email ingested and published to Strava',
            'components_created': len(component_ids),
            'strava_activities': strava_activities
        })
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/debug', methods=['POST'])
def debug_webhook():
    """Debug endpoint to see exactly what Zapier sends."""
    try:
        # Log everything
        logger.info("=" * 70)
        logger.info("DEBUG WEBHOOK CALLED")
        logger.info(f"Content-Type: {request.content_type}")
        logger.info(f"Headers: {dict(request.headers)}")
        
        if request.is_json:
            data = request.get_json()
            logger.info("Received JSON data")
        else:
            data = request.form.to_dict()
            logger.info("Received form data")
        
        logger.info(f"Data keys: {list(data.keys())}")
        
        for key, value in data.items():
            if key == 'html':
                logger.info(f"{key}: {value[:200]}... (truncated)")
            else:
                logger.info(f"{key}: {value}")
        
        logger.info("=" * 70)
        
        return jsonify({
            'success': True,
            'received_keys': list(data.keys()),
            'html_length': len(data.get('html', ''))
        })
        
    except Exception as e:
        logger.error(f"Debug error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/test', methods=['GET'])
def test():
    """Test endpoint to verify webhook is working."""
    return jsonify({
        'status': 'ok',
        'message': 'Webhook is running!',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    # Run Flask app
    # For development: runs on http://localhost:5000
    # Use ngrok to expose to internet for Zapier
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

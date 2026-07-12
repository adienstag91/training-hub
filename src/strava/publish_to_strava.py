"""
Strava Activity Publisher
Publishes workout components from database to Strava.
"""

import os
import sys
import psycopg2
from datetime import datetime, timezone
from pathlib import Path
from stravalib.client import Client
from dotenv import load_dotenv

# Get project root (training-hub directory)
PROJECT_ROOT = Path(__file__).parent.parent.parent
ENV_PATH = PROJECT_ROOT / '.env'

# Load environment variables from project root
load_dotenv(ENV_PATH)

# Add parent directory to path
sys.path.insert(0, str(PROJECT_ROOT))


def get_db_connection():
    """Create PostgreSQL database connection."""
    return psycopg2.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=os.getenv('POSTGRES_PORT', '5432'),
        database=os.getenv('POSTGRES_DB', 'training_hub'),
        user=os.getenv('POSTGRES_USER', os.environ.get('USER')),
        password=os.getenv('POSTGRES_PASSWORD')
    )


def get_strava_client():
    """
    Create authenticated Strava client.
    Handles token refresh if needed.
    """
    client = Client()
    
    access_token = os.getenv('STRAVA_ACCESS_TOKEN')
    refresh_token = os.getenv('STRAVA_REFRESH_TOKEN')
    expires_at = int(os.getenv('STRAVA_EXPIRES_AT', 0))
    
    # Check if token is expired
    current_time = datetime.now(timezone.utc).timestamp()
    
    if current_time > expires_at:
        print("⚠️  Access token expired, refreshing...")
        
        # Refresh the token
        refresh_response = client.refresh_access_token(
            client_id=os.getenv('STRAVA_CLIENT_ID'),
            client_secret=os.getenv('STRAVA_CLIENT_SECRET'),
            refresh_token=refresh_token
        )
        
        # Update tokens
        access_token = refresh_response['access_token']
        refresh_token = refresh_response['refresh_token']
        expires_at = refresh_response['expires_at']
        
        # Save to .env
        update_env_tokens(access_token, refresh_token, expires_at)
        
        print("✅ Token refreshed")
    
    client.access_token = access_token
    return client


def update_env_tokens(access_token, refresh_token, expires_at):
    """Update tokens in .env file."""
    with open(ENV_PATH, 'r') as f:
        lines = f.readlines()
    
    with open(ENV_PATH, 'w') as f:
        for line in lines:
            if line.startswith('STRAVA_ACCESS_TOKEN='):
                f.write(f'STRAVA_ACCESS_TOKEN={access_token}\n')
            elif line.startswith('STRAVA_REFRESH_TOKEN='):
                f.write(f'STRAVA_REFRESH_TOKEN={refresh_token}\n')
            elif line.startswith('STRAVA_EXPIRES_AT='):
                f.write(f'STRAVA_EXPIRES_AT={expires_at}\n')
            else:
                f.write(line)


def get_activity_name(component_type, class_type, source_type):
    """
    Generate Strava activity name.
    
    Format: "Component Type (OTF Class Type)"
    Examples:
        - "Treadmill (OTF Orange 60)"
        - "Rowing (OTF Orange 60)"
        - "Strength (OTF Tread 50)"
    """
    component_names = {
        'run': 'Treadmill',
        'row': 'Rowing',
        'bike': 'Cycling',
        'strength': 'Strength'
    }
    
    component_name = component_names.get(component_type, component_type.title())
    
    if source_type == 'otf':
        return f"{component_name} (Orange Theory)"
    else:
        return f"{component_name} ({source_type.title()})"


def get_activity_type(component_type):
    """
    Map component type to Strava activity type.
    
    Strava activity types: Run, Ride, Swim, Workout, etc.
    """
    mapping = {
        'run': 'Run',
        'row': 'Rowing',
        'bike': 'Ride',
        'strength': 'WeightTraining'
    }
    return mapping.get(component_type, 'Workout')


def create_activity_via_stravalib(client, activity_data):
    """
    Create Strava activity using stravalib (recommended for production).
    
    Pros: Handles token refresh, Pythonic, abstracts HTTP details
    """
    return client.create_activity(**activity_data)


def create_activity_via_requests(activity_data):
    """
    Create Strava activity using direct API calls (for learning/debugging).
    
    This is the raw HTTP method - useful for understanding what's happening.
    Postman equivalent:
        POST https://www.strava.com/api/v3/activities
        Headers: Authorization: Bearer {access_token}
        Body: JSON activity_data
    """
    import requests
    
    access_token = os.getenv('STRAVA_ACCESS_TOKEN')
    
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    response = requests.post(
        'https://www.strava.com/api/v3/activities',
        headers=headers,
        json=activity_data
    )
    
    if response.status_code == 201:
        return response.json()
    else:
        raise Exception(f"Strava API error: {response.status_code} - {response.text}")


def publish_component_to_strava(component_id, client):
    """
    Publish a single workout component to Strava.
    
    Args:
        component_id: ID of workout_component to publish
        client: Authenticated Strava client
        
    Returns:
        Strava activity ID or None if failed
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Get component details with session info
        cur.execute("""
            SELECT 
                c.id,
                c.component_type,
                c.duration_seconds,
                c.sequence_order,
                s.id as session_id,
                s.workout_date,
                s.start_time,
                s.otf_class_type,
                s.source_type
            FROM workout_component c
            JOIN workout_session s ON c.workout_session_id = s.id
            WHERE c.id = %s
        """, (component_id,))
        
        row = cur.fetchone()
        if not row:
            print(f"❌ Component {component_id} not found")
            return None
        
        comp_id, comp_type, duration_sec, seq_order, session_id, workout_date, start_time, class_type, source_type = row
        
        # Stagger start time by 1 minute per component to avoid Strava conflicts
        # Sequence order: 1 (run) = +0 min, 2 (row) = +1 min, 3 (strength) = +2 min
        from datetime import timedelta
        offset_minutes = seq_order - 1  # 0-indexed
        component_start_time = start_time + timedelta(minutes=offset_minutes)
        
        # Get type-specific details
        distance_meters = None
        elevation_gain = None
        avg_cadence = None
        stroke_rate = None
        avg_watts = None

        if comp_type == 'run':
            cur.execute("""
                SELECT distance_meters, elevation_gain_meters, avg_cadence_spm
                FROM run_component WHERE component_id = %s
            """, (comp_id,))
            result = cur.fetchone()
            if result:
                distance_meters, elevation_gain, avg_cadence = result
        elif comp_type == 'row':
            cur.execute("""
                SELECT distance_meters, avg_stroke_rate_spm, avg_watts
                FROM row_component WHERE component_id = %s
            """, (comp_id,))
            result = cur.fetchone()
            if result:
                distance_meters, stroke_rate, avg_watts = result
        elif comp_type == 'bike':
            cur.execute("SELECT distance_meters FROM bike_component WHERE component_id = %s", (comp_id,))
            result = cur.fetchone()
            distance_meters = result[0] if result else None
        
        # Build activity name using Option C format
        activity_name = get_activity_name(comp_type, class_type, source_type)

        # Format class type for description (ORANGE_60 → Orange Theory 60 Minute)
        def format_class_type(ct):
            if not ct:
                return "Orange Theory"
            class_map = {
                'ORANGE_60': 'Orange Theory 60 Minute',
                'ORANGE_90': 'Orange Theory 90 Minute',
                'TREAD_50': 'Orange Theory Tread 50',
                'STRENGTH_50': 'Orange Theory Strength 50'
            }
            return class_map.get(ct, f"Orange Theory {ct.replace('_', ' ').title()}")

        # Build description
        desc_lines = [format_class_type(class_type)]

        # Add duration
        desc_lines.append(f"Duration: {duration_sec // 60} min {duration_sec % 60} sec")

        # Add distance if present
        if distance_meters:
            desc_lines.append(f"Distance: {distance_meters}m ({distance_meters / 1609.34:.2f} miles)")

        # Add run-specific metrics
        if comp_type == 'run':
            if elevation_gain:
                desc_lines.append(f"Elevation Gain: {elevation_gain}m ({elevation_gain * 3.281:.0f} ft)")
            if avg_cadence:
                desc_lines.append(f"Avg Cadence: {avg_cadence} spm")

        # Add row-specific metrics
        if comp_type == 'row':
            if stroke_rate:
                desc_lines.append(f"Avg Stroke Rate: {stroke_rate} spm")
            if avg_watts:
                desc_lines.append(f"Avg Power: {avg_watts} watts")

        description = "\n".join(desc_lines)
        
        # Prepare activity data for stravalib
        activity_data = {
            'name': activity_name,
            'activity_type': get_activity_type(comp_type),
            'start_date_local': component_start_time,
            'elapsed_time': duration_sec,
            'description': description,
        }
        
        # Add distance if present
        if distance_meters:
            activity_data['distance'] = distance_meters
        
        # Create activity on Strava
        print(f"📤 Uploading: {activity_name} (starts {component_start_time.strftime('%I:%M %p')}, {duration_sec}s, {distance_meters or 0}m)")
        
        # Method 1: Using stravalib (recommended for production)
        activity = create_activity_via_stravalib(client, activity_data)
        
        # Method 2: Direct API call (for learning - currently commented out)
        # Uncomment below to use direct API instead:
        # For direct API, change 'activity_type' to 'type' in activity_data
        # activity_data['type'] = activity_data.pop('activity_type')
        # activity_response = create_activity_via_requests(activity_data)
        # activity_id = activity_response['id']
        
        activity_id = activity.id
        
        print(f"✅ Created Strava activity: {activity_id}")
        
        # Record in database
        cur.execute("""
            INSERT INTO strava_activity_publish (
                workout_component_id, strava_activity_id, 
                published_at, sync_status
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (workout_component_id) 
            DO UPDATE SET 
                strava_activity_id = EXCLUDED.strava_activity_id,
                published_at = EXCLUDED.published_at,
                sync_status = EXCLUDED.sync_status
        """, (comp_id, activity_id, datetime.now(), 'published'))
        
        conn.commit()
        
        return activity_id
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error publishing component {component_id}: {e}")
        
        # Record failure
        try:
            cur.execute("""
                INSERT INTO strava_activity_publish (
                    workout_component_id, sync_status, sync_error
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (workout_component_id)
                DO UPDATE SET
                    sync_status = EXCLUDED.sync_status,
                    sync_error = EXCLUDED.sync_error
            """, (component_id, 'failed', str(e)))
            conn.commit()
        except:
            pass
        
        return None
        
    finally:
        cur.close()
        conn.close()


def publish_unpublished_components():
    """
    Find all components that haven't been published to Strava yet
    and publish them.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Find components without Strava activities
        cur.execute("""
            SELECT c.id, c.component_type, s.workout_date, s.otf_class_type
            FROM workout_component c
            JOIN workout_session s ON c.workout_session_id = s.id
            LEFT JOIN strava_activity_publish sap ON c.id = sap.workout_component_id
            WHERE sap.id IS NULL OR sap.sync_status = 'failed'
            ORDER BY s.workout_date, c.sequence_order
        """)
        
        components = cur.fetchall()
        
        if not components:
            print("\n✅ No unpublished components found. All synced!")
            return
        
        print(f"\n📊 Found {len(components)} components to publish")
        print("="*70 + "\n")
        
        # Get Strava client
        client = get_strava_client()
        
        # Publish each component
        success_count = 0
        fail_count = 0
        
        for comp_id, comp_type, workout_date, class_type in components:
            print(f"\n🔄 Processing component {comp_id} ({comp_type}, {workout_date})")
            
            strava_id = publish_component_to_strava(comp_id, client)
            
            if strava_id:
                success_count += 1
                print(f"   View on Strava: https://www.strava.com/activities/{strava_id}")
            else:
                fail_count += 1
        
        print("\n" + "="*70)
        print(f"SUMMARY: {success_count} published, {fail_count} failed")
        print("="*70 + "\n")
        
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        # Publish specific component by ID
        component_id = int(sys.argv[1])
        print(f"\nPublishing component {component_id}...")
        client = get_strava_client()
        strava_id = publish_component_to_strava(component_id, client)
        if strava_id:
            print(f"\n✅ Published: https://www.strava.com/activities/{strava_id}")
    else:
        # Publish all unpublished
        publish_unpublished_components()

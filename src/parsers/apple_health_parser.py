"""
Apple Health JSON Parser
Parses Health Auto Export JSON files and extracts workout data.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional
import uuid


def parse_apple_health_json(json_content: str) -> List[Dict]:
    """
    Parse Apple Health Auto Export JSON and return standardized workout data.
    
    Returns list of workouts in format suitable for database ingestion.
    """
    try:
        data = json.loads(json_content)
        workouts = data.get('data', {}).get('workouts', [])
        
        parsed_workouts = []
        
        for workout in workouts:
            parsed_workout = extract_workout_data(workout)
            if parsed_workout:
                parsed_workouts.append(parsed_workout)
        
        return parsed_workouts
        
    except Exception as e:
        raise Exception(f"Failed to parse Apple Health JSON: {e}")


def extract_workout_data(workout: Dict) -> Optional[Dict]:
    """Extract and standardize data from a single Apple Health workout."""
    
    # Skip if missing essential data
    if not workout.get('start') or not workout.get('name'):
        return None
    
    # Parse start and end times
    start_time = parse_apple_date(workout['start'])
    end_time = parse_apple_date(workout['end'])
    
    if not start_time or not end_time:
        return None
    
    # Calculate duration (Apple gives duration in seconds as float)
    duration_seconds = int(workout.get('duration', 0))
    if duration_seconds <= 0:
        duration_seconds = int((end_time - start_time).total_seconds())
    
    # Map Apple workout types to our standard types
    workout_type = map_apple_workout_type(workout['name'])
    
    # Extract metrics
    distance_km = 0
    if 'walkingAndRunningDistance' in workout:
        # Sum all distance measurements (they're in km)
        distance_km = sum(entry['qty'] for entry in workout['walkingAndRunningDistance'])
    
    active_calories = workout.get('activeEnergyBurned', {}).get('qty', 0)
    avg_heart_rate = workout.get('avgHeartRate', {}).get('qty')
    max_heart_rate = workout.get('maxHeartRate', {}).get('qty')
    
    # Generate unique identifier
    apple_workout_id = workout.get('id', str(uuid.uuid4()))
    
    return {
        'source': 'apple_health',
        'workout_type': workout_type,
        'apple_workout_id': apple_workout_id,
        'name': workout['name'],
        'start_time': start_time,
        'end_time': end_time,
        'duration_seconds': duration_seconds,
        'distance_meters': int(distance_km * 1000),  # Convert km to meters
        'active_calories': int(active_calories) if active_calories else None,
        'avg_heart_rate': int(avg_heart_rate) if avg_heart_rate else None,
        'max_heart_rate': int(max_heart_rate) if max_heart_rate else None,
        'is_indoor': workout.get('isIndoor', False),
        'location': workout.get('location', 'Unknown'),
        'raw_data': workout  # Store original for reference
    }


def parse_apple_date(date_string: str) -> Optional[datetime]:
    """Parse Apple Health date string to datetime object."""
    try:
        # Apple format: "2026-02-08 11:44:12 -0500"
        return datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S %z")
    except Exception:
        return None


def map_apple_workout_type(apple_name: str) -> str:
    """
    Map Apple workout names to our standardized types.
    
    Our types: run, strength, hiit, yoga, flexibility
    """
    apple_name_lower = apple_name.lower()
    
    if 'run' in apple_name_lower:
        return 'run'
    elif any(word in apple_name_lower for word in ['strength', 'weight', 'lifting']):
        return 'strength'
    elif any(word in apple_name_lower for word in ['hiit', 'interval', 'circuit']):
        return 'hiit'
    elif 'yoga' in apple_name_lower:
        return 'yoga'
    elif any(word in apple_name_lower for word in ['stretch', 'flexibility', 'cool']):
        return 'flexibility'
    else:
        # Default mapping for unknown types
        return 'other'


if __name__ == '__main__':
    # Test with sample file
    with open('sample_apple_health.json', 'r') as f:
        json_content = f.read()
    
    workouts = parse_apple_health_json(json_content)
    
    print(f"Found {len(workouts)} workouts:")
    for workout in workouts:
        print(f"- {workout['name']} ({workout['workout_type']}) - {workout['duration_seconds']}s")

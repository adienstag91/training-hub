"""
Peloton CSV Parser
Parses the official Peloton workout-history export (workouts.csv, downloaded
from Profile -> Workouts -> "Download Workouts") into standardized dicts.
"""

import csv
import io
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

MILES_TO_METERS = 1609.34

# Peloton "Fitness Discipline" -> our component types
DISCIPLINE_MAP = {
    "cycling": "bike",
    "bike bootcamp": "hiit",
    "running": "run",
    "tread bootcamp": "hiit",
    "walking": "walk",
    "rowing": "row",
    "row bootcamp": "hiit",
    "strength": "strength",
    "yoga": "yoga",
    "stretching": "flexibility",
    "cardio": "hiit",
    "meditation": "other",
}


def _parse_timestamp(value: str) -> Optional[datetime]:
    """Parse Peloton's 'Workout Timestamp', e.g. '2026-01-05 06:30 (EST)'.

    The timezone abbreviation is dropped; the local wall-clock time is kept.
    """
    if not value:
        return None
    clean = re.sub(r"\s*\([^)]*\)\s*$", "", value.strip())
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(clean, fmt)
        except ValueError:
            continue
    return None


def _parse_int(value: str) -> Optional[int]:
    """'42', '42%', '42.7' -> 42; blank/junk -> None."""
    if not value:
        return None
    match = re.search(r"[\d.]+", value.replace(",", ""))
    return int(float(match.group())) if match else None


def _parse_float(value: str) -> Optional[float]:
    if not value:
        return None
    match = re.search(r"[\d.]+", value.replace(",", ""))
    return float(match.group()) if match else None


def map_peloton_discipline(discipline: str) -> str:
    """Map a Peloton fitness discipline to our standardized component type."""
    return DISCIPLINE_MAP.get((discipline or "").strip().lower(), "other")


def parse_peloton_csv(csv_content: str) -> List[Dict[str, Any]]:
    """
    Parse a Peloton workouts.csv export.

    Returns a list of standardized workout dicts (rows without a parseable
    timestamp or duration are skipped — e.g. blank 'Just Ride' entries).
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    workouts = []

    for row in reader:
        # Header names occasionally gain/lose whitespace between export versions
        row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}

        start_time = _parse_timestamp(row.get("Workout Timestamp", ""))
        length_minutes = _parse_int(row.get("Length (minutes)", ""))

        if not start_time or not length_minutes:
            continue  # unusable row (e.g. freestyle entry with no length)

        discipline = row.get("Fitness Discipline", "")
        workout_type = map_peloton_discipline(discipline)

        distance_miles = _parse_float(row.get("Distance (mi)", ""))
        distance_meters = int(distance_miles * MILES_TO_METERS) if distance_miles else None

        # Stable idempotency key: a user cannot take two classes of the same
        # discipline starting the same minute.
        workout_id = f"{start_time.isoformat()}:{discipline.strip().lower()}"

        workouts.append(
            {
                "source": "peloton",
                "peloton_workout_id": workout_id,
                "workout_type": workout_type,
                "discipline": discipline,
                "title": row.get("Title") or None,
                "instructor": row.get("Instructor Name") or None,
                "start_time": start_time,
                "duration_seconds": length_minutes * 60,
                "distance_meters": distance_meters,
                "calories": _parse_int(row.get("Calories Burned", "")),
                "total_output": _parse_int(row.get("Total Output", "")),
                "avg_watts": _parse_int(row.get("Avg. Watts", "")),
                "avg_resistance": _parse_int(row.get("Avg. Resistance", "")),
                "avg_cadence_rpm": _parse_int(row.get("Avg. Cadence (RPM)", "")),
                "avg_speed_mph": _parse_float(row.get("Avg. Speed (mph)", "")),
                "avg_heart_rate": _parse_int(row.get("Avg. Heartrate", "")),
                "live_or_ondemand": row.get("Live/On-Demand") or None,
                "raw_row": row,
            }
        )

    return workouts

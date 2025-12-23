"""
OTF Email Parser
Extracts tread/row metrics and classifies workout type using rule-based logic.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup


def parse_time_to_minutes(time_str: str) -> Optional[float]:
    """
    Parse time string like '23:56' or '44:52' to minutes as float.
    
    Args:
        time_str: Time in format MM:SS or HH:MM:SS
        
    Returns:
        Total minutes as float, or None if parse fails
    """
    if not time_str:
        return None
    
    # Remove zero-width non-joiner and whitespace
    clean = time_str.replace('&zwnj;', '').strip()
    
    parts = clean.split(':')
    if len(parts) == 2:
        # MM:SS format
        minutes, seconds = int(parts[0]), int(parts[1])
        return minutes + (seconds / 60.0)
    elif len(parts) == 3:
        # HH:MM:SS format (rare but handle it)
        hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
        return (hours * 60) + minutes + (seconds / 60.0)
    
    return None


def extract_tread_metrics(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Extract treadmill metrics from email HTML.
    
    Returns:
        Dict with keys: total_time_minutes, distance_meters, present
    """
    # Look for "TREADMILL PERFORMANCE TOTALS" section
    tread_header = soup.find(string=re.compile(r'TREADMILL PERFORMANCE TOTALS', re.IGNORECASE))
    
    if not tread_header:
        return {
            'total_time_minutes': None,
            'distance_meters': None,
            'present': False
        }
    
    # Find "Total Time" - it's in the same TD as the time value
    # Strategy: Find all "Total Time" instances, check if they're near tread section
    all_total_times = soup.find_all(string=re.compile(r'Total Time', re.IGNORECASE))
    
    # Get the first "Total Time" after the tread header (should be tread time)
    tread_time_td = None
    for tt in all_total_times:
        # Simple heuristic: use the first one (tread comes before row in email)
        tread_time_td = tt.find_parent('td')
        break
    
    total_time_min = None
    distance_meters = None
    
    if tread_time_td:
        # The time is in the same TD, in a <p> tag before "Total Time"
        # Look for pattern like "23:56" or "23&zwnj;:56"
        td_text = tread_time_td.get_text()
        time_match = re.search(r'(\d+)[:\u200c]+(\d+)', td_text)
        if time_match:
            minutes, seconds = int(time_match.group(1)), int(time_match.group(2))
            total_time_min = minutes + (seconds / 60.0)
    
        # Extract Total Distance - same row, different TD
        parent_tr = tread_time_td.find_parent('tr')
        if parent_tr:
            all_tds = parent_tr.find_all('td')
            # Distance should be in first TD (index 0)
            if len(all_tds) >= 1:
                dist_td = all_tds[0]
                dist_text = dist_td.get_text()
                # Look for pattern like "3.21" followed by "miles"
                dist_match = re.search(r'([\d.]+)\s*miles', dist_text, re.IGNORECASE)
                if dist_match:
                    miles = float(dist_match.group(1))
                    # Convert miles to meters
                    distance_meters = int(miles * 1609.34)
    
    return {
        'total_time_minutes': total_time_min,
        'distance_meters': distance_meters,
        'present': True
    }


def extract_row_metrics(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Extract rower metrics from email HTML.
    
    Returns:
        Dict with keys: total_time_minutes, total_distance_meters, present
    """
    # Look for "ROWER PERFORMANCE TOTALS" section
    row_header = soup.find(string=re.compile(r'ROWER PERFORMANCE TOTALS', re.IGNORECASE))
    
    if not row_header:
        return {
            'total_time_minutes': None,
            'total_distance_meters': None,
            'present': False
        }
    
    # Find all "Total Time" instances - row time is the second one
    all_total_times = soup.find_all(string=re.compile(r'Total Time', re.IGNORECASE))
    
    row_time_td = None
    if len(all_total_times) >= 2:
        # Second instance should be row time
        row_time_td = all_total_times[1].find_parent('td')
    
    total_time_min = None
    total_distance_m = None
    
    if row_time_td:
        td_text = row_time_td.get_text()
        time_match = re.search(r'(\d+)[:\u200c]+(\d+)', td_text)
        if time_match:
            minutes, seconds = int(time_match.group(1)), int(time_match.group(2))
            total_time_min = minutes + (seconds / 60.0)
    
        # Extract Total Distance (meters for rowing)
        parent_tr = row_time_td.find_parent('tr')
        if parent_tr:
            all_tds = parent_tr.find_all('td')
            if len(all_tds) >= 1:
                dist_td = all_tds[0]
                dist_text = dist_td.get_text()
                # Look for pattern like "4189" followed by "m"
                dist_match = re.search(r'([\d,]+)\s*m(?:eters)?', dist_text, re.IGNORECASE)
                if dist_match:
                    total_distance_m = int(dist_match.group(1).replace(',', ''))
    
    return {
        'total_time_minutes': total_time_min,
        'total_distance_meters': total_distance_m,
        'present': True
    }


def classify_workout(tread: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify workout type using rule-based decision tree and calculate component times.
    
    Decision Tree:
    1. If tread_time >= 40 AND no row section → TREAD_50 (tread only, no strength)
    2. If no tread AND no row → STRENGTH_50 (strength only, no tread/row)
    3. If tread_time + row_time >= 40 → ORANGE_90
    4. Otherwise → ORANGE_60
    
    Args:
        tread: Dict with treadmill metrics
        row: Dict with rower metrics
        
    Returns:
        Dict with class_type, class_minutes, and component times in seconds
    """
    tread_time = tread['total_time_minutes'] or 0
    row_time = row['total_time_minutes'] or 0
    
    # Convert to seconds for component storage
    tread_seconds = int(tread_time * 60)
    row_seconds = int(row_time * 60)
    
    evidence = {
        'tread_present': tread['present'],
        'tread_time_min': tread_time,
        'row_present': row['present'],
        'row_time_min': row_time,
        'total_cardio_time': tread_time + row_time
    }
    
    # Determine class type and duration
    # Rule 1: TREAD_50 (tread only, no strength component)
    if tread_time >= 40 and not row['present']:
        return {
            'class_type': 'TREAD_50',
            'class_minutes': 50,
            'tread_seconds': tread_seconds,
            'row_seconds': 0,
            'strength_seconds': 0,  # No strength in TREAD_50
            'evidence': evidence
        }
    
    # Rule 2: STRENGTH_50 (strength only, no tread/row)
    if not tread['present'] and not row['present']:
        return {
            'class_type': 'STRENGTH_50',
            'class_minutes': 50,
            'tread_seconds': 0,
            'row_seconds': 0,
            'strength_seconds': 50 * 60,  # Full 50 minutes of strength
            'evidence': evidence
        }
    
    # Rule 3: ORANGE_90
    if (tread_time + row_time) >= 40:
        class_type = 'ORANGE_90'
        class_minutes = 90
    # Rule 4: ORANGE_60 (default)
    else:
        class_type = 'ORANGE_60'
        class_minutes = 60
    
    # Calculate strength time as residual for ORANGE classes
    total_class_seconds = class_minutes * 60
    strength_seconds = max(0, total_class_seconds - tread_seconds - row_seconds)
    
    return {
        'class_type': class_type,
        'class_minutes': class_minutes,
        'tread_seconds': tread_seconds,
        'row_seconds': row_seconds,
        'strength_seconds': strength_seconds,
        'evidence': evidence
    }


def parse_otf_email(html_content: str, message_id: str) -> Dict[str, Any]:
    """
    Parse complete OTF email and extract all metrics.
    
    Args:
        html_content: Raw HTML email content
        message_id: Email Message-ID from headers
        
    Returns:
        Dict with all extracted and classified data
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract date from email Date header (should be in the raw email)
    # For now, we'll need to pass this in separately or extract from headers
    # This is a simplified version - in production, parse from email headers
    workout_date = datetime.now()  # PLACEHOLDER - extract from Date header
    
    # Extract subject
    subject = ""  # PLACEHOLDER - extract from Subject header
    
    # Extract overall metrics
    # Look for CALORIES BURNED - value is in same column, above the label
    calories_text = soup.find(string=re.compile(r'CALORIES BURNED', re.IGNORECASE))
    total_calories = None
    if calories_text:
        # Get parent TD containing both value and label
        cal_td = calories_text.find_parent('td')
        if cal_td:
            # Find parent table of this TD to search within
            cal_table = cal_td.find_parent('table')
            if cal_table:
                # Look for <p> with h1 class containing the number
                cal_p = cal_table.find('p', class_='h1')
                if cal_p:
                    cal_match = re.search(r'(\d+)', cal_p.get_text())
                    if cal_match:
                        total_calories = int(cal_match.group(1))
    
    # Look for SPLAT POINTS - same pattern
    splat_text = soup.find(string=re.compile(r'SPLAT POINTS', re.IGNORECASE))
    splat_points = None
    if splat_text:
        splat_td = splat_text.find_parent('td')
        if splat_td:
            splat_table = splat_td.find_parent('table')
            if splat_table:
                splat_p = splat_table.find('p', class_='h1')
                if splat_p:
                    splat_match = re.search(r'(\d+)', splat_p.get_text())
                    if splat_match:
                        splat_points = int(splat_match.group(1))
    
    # Extract component metrics
    tread = extract_tread_metrics(soup)
    row = extract_row_metrics(soup)
    
    # Classify workout and calculate component times
    classification = classify_workout(tread, row)
    
    return {
        'message_id': message_id,
        'workout_date': workout_date,
        'subject': subject,
        'total_calories': total_calories,
        'splat_points': splat_points,
        'tread': tread,
        'row': row,
        'classification': classification
    }


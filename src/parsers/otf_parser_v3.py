"""
OTF Email Parser v3
Tag-based HTML navigation with workout datetime from email body.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup


def extract_workout_datetime(soup: BeautifulSoup) -> Optional[datetime]:
    """
    Extract workout date and time from email body.
    
    Looks for pattern like:
    12/24/2025
    10:45 AM
    
    Returns:
        datetime object or None
    """
    # Find STUDIO WORKOUT SUMMARY section
    summary_header = soup.find(string=re.compile(r'STUDIO WORKOUT SUMMARY', re.IGNORECASE))
    if not summary_header:
        return None
    
    # Get parent table containing the workout info
    info_table = summary_header.find_parent('table')
    if not info_table:
        return None
    
    # Find all <p class="text-white"> elements (contains date, time, instructor)
    white_text = info_table.find_all('p', class_=lambda x: x and 'text-white' in x)
    
    workout_date = None
    workout_time = None
    
    for p in white_text:
        text = p.get_text(strip=True)
        
        # Look for date pattern: MM/DD/YYYY
        date_match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', text)
        if date_match:
            month = int(date_match.group(1))
            day = int(date_match.group(2))
            year = int(date_match.group(3))
            workout_date = (year, month, day)
        
        # Look for time pattern: HH:MM AM/PM
        time_match = re.match(r'(\d{1,2})[:\u200c]+(\d{2})\s*(AM|PM)', text, re.IGNORECASE)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
            period = time_match.group(3).upper()
            
            # Convert to 24-hour format
            if period == 'PM' and hour != 12:
                hour += 12
            elif period == 'AM' and hour == 12:
                hour = 0
            
            workout_time = (hour, minute)
    
    # Combine date and time
    if workout_date and workout_time:
        year, month, day = workout_date
        hour, minute = workout_time
        return datetime(year, month, day, hour, minute)
    
    return None


def extract_message_id(html_content: str) -> Optional[str]:
    """
    Extract Message-ID from email headers.
    
    Args:
        html_content: Raw email with headers
        
    Returns:
        Message-ID string or None
    """
    lines = html_content.split('\n')
    
    for line in lines:
        # Stop at end of headers
        if line.strip() == '' or line.startswith('<'):
            break
        
        if line.startswith('Message-ID:'):
            match = re.search(r'<(.+?)>', line)
            if match:
                return match.group(1)
    
    return None


def extract_number_from_text(text: str) -> Optional[float]:
    """
    Extract first number from text string.
    
    Args:
        text: String like " 3.21 " or " 1090"
        
    Returns:
        Float or None
    """
    match = re.search(r'([\d,]+\.?\d*)', text.replace(',', ''))
    return float(match.group(1)) if match else None


def extract_time_from_text(text: str) -> Optional[float]:
    """
    Extract time in MM:SS format and convert to minutes.
    
    Args:
        text: String like " 23:56 " or " 17:53"
        
    Returns:
        Time in minutes as float, or None
    """
    # Handle zero-width non-joiner and regular colons
    clean_text = text.replace('\u200c', '').strip()
    match = re.search(r'(\d+):(\d+)', clean_text)
    
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        return minutes + (seconds / 60.0)
    
    return None


def extract_tread_metrics(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Extract treadmill metrics using tag-based navigation.
    
    Returns:
        Dict with total_time_minutes, distance_meters, present
    """
    # Look for TREADMILL PERFORMANCE TOTALS header
    tread_header = soup.find(string=re.compile(r'TREADMILL PERFORMANCE TOTALS', re.IGNORECASE))
    
    if not tread_header:
        return {
            'total_time_minutes': None,
            'distance_meters': None,
            'present': False
        }
    
    # Find all "Total Distance" and "Total Time" in the document
    # First occurrence after tread header should be tread metrics
    all_total_times = soup.find_all(string=re.compile(r'Total Time', re.IGNORECASE))
    all_total_distances = soup.find_all(string=re.compile(r'Total Distance', re.IGNORECASE))
    
    # Use first occurrence (tread comes before row in email)
    distance_meters = None
    if len(all_total_distances) >= 1:
        dist_label = all_total_distances[0]
        dist_td = dist_label.find_parent('td')
        if dist_td:
            for span in dist_td.find_all('span'):
                if span.get('class') and any('h1' in c for c in span.get('class')):
                    dist_text = span.get_text(strip=True)
                    miles = extract_number_from_text(dist_text)
                    if miles:
                        distance_meters = int(miles * 1609.34)
                    break
    
    total_time_min = None
    if len(all_total_times) >= 1:
        time_label = all_total_times[0]
        time_td = time_label.find_parent('td')
        if time_td:
            for p in time_td.find_all('p'):
                if p.get('class') and any('h1' in c for c in p.get('class')):
                    time_text = p.get_text(strip=True)
                    total_time_min = extract_time_from_text(time_text)
                    break
    
    return {
        'total_time_minutes': total_time_min,
        'distance_meters': distance_meters,
        'present': True
    }


def extract_row_metrics(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Extract rower metrics using tag-based navigation.
    
    Returns:
        Dict with total_time_minutes, total_distance_meters, present
    """
    # Look for ROWER PERFORMANCE TOTALS header
    row_header = soup.find(string=re.compile(r'ROWER PERFORMANCE TOTALS', re.IGNORECASE))
    
    if not row_header:
        return {
            'total_time_minutes': None,
            'total_distance_meters': None,
            'present': False
        }
    
    # Find all "Total Distance" and "Total Time" in the document
    # Second occurrence should be row metrics (after tread)
    all_total_times = soup.find_all(string=re.compile(r'Total Time', re.IGNORECASE))
    all_total_distances = soup.find_all(string=re.compile(r'Total Distance', re.IGNORECASE))
    
    total_distance_m = None
    if len(all_total_distances) >= 2:
        dist_label = all_total_distances[1]  # Second occurrence
        dist_td = dist_label.find_parent('td')
        if dist_td:
            for span in dist_td.find_all('span'):
                if span.get('class') and any('h1' in c for c in span.get('class')):
                    dist_text = span.get_text(strip=True)
                    meters = extract_number_from_text(dist_text)
                    if meters:
                        total_distance_m = int(meters)
                    break
    
    total_time_min = None
    if len(all_total_times) >= 2:
        time_label = all_total_times[1]  # Second occurrence
        time_td = time_label.find_parent('td')
        if time_td:
            for p in time_td.find_all('p'):
                if p.get('class') and any('h1' in c for c in p.get('class')):
                    time_text = p.get_text(strip=True)
                    total_time_min = extract_time_from_text(time_text)
                    break
    
    return {
        'total_time_minutes': total_time_min,
        'total_distance_meters': total_distance_m,
        'present': True
    }


def extract_overall_metrics(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Extract calories and splat points using tag-based navigation.
    
    Returns:
        Dict with total_calories, splat_points
    """
    total_calories = None
    splat_points = None
    
    # Find CALORIES BURNED
    cal_label = soup.find(string=re.compile(r'CALORIES BURNED', re.IGNORECASE))
    if cal_label:
        cal_table = cal_label.find_parent('table')
        if cal_table:
            for p in cal_table.find_all('p'):
                if p.get('class') and any('h1' in c for c in p.get('class')):
                    cal_text = p.get_text(strip=True)
                    total_calories = int(extract_number_from_text(cal_text) or 0)
                    break
    
    # Find SPLAT POINTS
    splat_label = soup.find(string=re.compile(r'SPLAT POINTS', re.IGNORECASE))
    if splat_label:
        splat_table = splat_label.find_parent('table')
        if splat_table:
            for p in splat_table.find_all('p'):
                if p.get('class') and any('h1' in c for c in p.get('class')):
                    splat_text = p.get_text(strip=True)
                    splat_points = int(extract_number_from_text(splat_text) or 0)
                    break
    
    return {
        'total_calories': total_calories,
        'splat_points': splat_points
    }


def classify_workout(tread: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify workout type and calculate component times in seconds.
    
    Decision Tree:
    1. If tread_time >= 40 AND no row → TREAD_50 (tread only)
    2. If no tread AND no row → STRENGTH_50 (strength only)
    3. If tread_time + row_time >= 40 → ORANGE_90
    4. Otherwise → ORANGE_60
    """
    tread_time = tread['total_time_minutes'] or 0
    row_time = row['total_time_minutes'] or 0
    
    # Convert to seconds
    tread_seconds = int(tread_time * 60)
    row_seconds = int(row_time * 60)
    
    evidence = {
        'tread_present': tread['present'],
        'tread_time_min': tread_time,
        'row_present': row['present'],
        'row_time_min': row_time,
        'total_cardio_time': tread_time + row_time
    }
    
    # Rule 1: TREAD_50 (no strength component)
    if tread_time >= 40 and not row['present']:
        return {
            'class_type': 'TREAD_50',
            'class_minutes': 50,
            'tread_seconds': tread_seconds,
            'row_seconds': 0,
            'strength_seconds': 0,
            'evidence': evidence
        }
    
    # Rule 2: STRENGTH_50
    if not tread['present'] and not row['present']:
        return {
            'class_type': 'STRENGTH_50',
            'class_minutes': 50,
            'tread_seconds': 0,
            'row_seconds': 0,
            'strength_seconds': 50 * 60,
            'evidence': evidence
        }
    
    # Rule 3: ORANGE_90
    if (tread_time + row_time) >= 40:
        class_type = 'ORANGE_90'
        class_minutes = 90
    # Rule 4: ORANGE_60
    else:
        class_type = 'ORANGE_60'
        class_minutes = 60
    
    # Calculate strength as residual
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


def parse_otf_email(html_content: str) -> Dict[str, Any]:
    """
    Parse complete OTF email and extract all metrics.
    
    Args:
        html_content: Raw email with headers and HTML body
        
    Returns:
        Dict with all parsed data including workout datetime from body
    """
    # Extract message ID from headers
    message_id = extract_message_id(html_content)
    
    # Parse HTML body
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract workout date/time from body
    workout_datetime = extract_workout_datetime(soup)
    
    # Extract metrics
    overall = extract_overall_metrics(soup)
    tread = extract_tread_metrics(soup)
    row = extract_row_metrics(soup)
    
    # Classify workout
    classification = classify_workout(tread, row)
    
    return {
        'message_id': message_id,
        'workout_datetime': workout_datetime,  # Full datetime from body
        'total_calories': overall['total_calories'],
        'splat_points': overall['splat_points'],
        'tread': tread,
        'row': row,
        'classification': classification
    }

"""
Test OTF Parser against sample emails.
Validates classification rules and metric extraction.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.parsers.otf_parser_v3 import parse_otf_email
import json
from pathlib import Path


def test_email(filepath: str, expected_class: str, test_name: str):
    """Test a single email and print results."""
    print(f"\n{'='*60}")
    print(f"Testing: {test_name}")
    print(f"Expected: {expected_class}")
    print('='*60)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()
    
    parsed = parse_otf_email(html)
    
    classification = parsed['classification']
    tread = parsed['tread']
    row = parsed['row']
    
    print(f"\n📊 CLASSIFICATION")
    print(f"  Class Date & Time: {parsed['workout_datetime']}")
    #print(f"  message_id: {parsed['message_id']}")
    #print(f"  subject: {parsed['subject']}")



    print(f"  Type: {classification['class_type']}")
    print(f"  Duration: {classification['class_minutes']} min")
    
    print(f"\n⏱️  COMPONENT TIMES")
    print(f"  Tread: {classification['tread_seconds']/60:.2f} min ({classification['tread_seconds']}s)")
    print(f"  Row: {classification['row_seconds']/60:.2f} min ({classification['row_seconds']}s)")
    print(f"  Strength: {classification['strength_seconds']/60:.2f} min ({classification['strength_seconds']}s)")
    
    print(f"\n🏃 TREAD METRICS")
    print(f"  Present: {tread['present']}")
    if tread['total_time_minutes']:
        print(f"  Time: {tread['total_time_minutes']:.2f} min")
        print(f"  Distance: {tread['distance_meters']}m ({tread['distance_meters']/1609.34:.2f} miles)")
    
    print(f"\n🚣 ROW METRICS")
    print(f"  Present: {row['present']}")
    if row['total_time_minutes']:
        print(f"  Time: {row['total_time_minutes']:.2f} min")
        print(f"  Distance: {row['total_distance_meters']}m")
    
    print(f"\n💪 OVERALL METRICS")
    print(f"  Calories: {parsed['total_calories']}")
    print(f"  Splat Points: {parsed['splat_points']}")
    
    print(f"\n🔍 CLASSIFICATION EVIDENCE")
    print(json.dumps(classification['evidence'], indent=2))
    
    # Validation
    success = classification['class_type'] == expected_class
    print(f"\n{'✅ PASS' if success else '❌ FAIL'}: Classification matches expected")
    
    return success


def infer_expected_class(filename: str) -> str:
    """Infer expected class type from filename."""
    filename_lower = filename.lower()

    if 'tread50' in filename_lower or 'tread_50' in filename_lower:
        return 'TREAD_50'
    elif '90_min' in filename_lower or '90min' in filename_lower:
        return 'ORANGE_90'
    elif '60_min' in filename_lower or '60min' in filename_lower:
        return 'ORANGE_60'
    else:
        # Default to 60-minute Orange class if can't determine
        return 'ORANGE_60'


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("OTF EMAIL PARSER VALIDATION")
    print("="*60)

    # Use relative paths from script location
    emails_dir = Path(__file__).parent.parent / 'data' / 'sample_emails'

    # Discover all HTML files in the directory
    html_files = sorted(emails_dir.glob('*.html'))

    if not html_files:
        print("\n⚠️  No HTML files found in", emails_dir)
        return

    print(f"\nFound {len(html_files)} HTML file(s) to test")

    results = []

    # Test each HTML file
    for html_file in html_files:
        expected_class = infer_expected_class(html_file.name)
        results.append(
            test_email(
                str(html_file),
                expected_class,
                html_file.name
            )
        )

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    total = len(results)
    passed = sum(results)
    print(f"Tests passed: {passed}/{total}")
    print(f"Success rate: {passed/total*100:.0f}%")

    if passed == total:
        print("\n🎉 All tests passed!")
    else:
        print("\n⚠️  Some tests failed - review parser logic")


if __name__ == '__main__':
    main()

"""
Test OTF Parser against sample emails.
Validates classification rules and metric extraction.
"""

from otf_parser import parse_otf_email
import json


def test_email(filepath: str, expected_class: str, test_name: str):
    """Test a single email and print results."""
    print(f"\n{'='*60}")
    print(f"Testing: {test_name}")
    print(f"Expected: {expected_class}")
    print('='*60)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        html = f.read()
    
    parsed = parse_otf_email(html, f'test-{test_name}')
    
    classification = parsed['classification']
    tread = parsed['tread']
    row = parsed['row']
    
    print(f"\n📊 CLASSIFICATION")
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


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("OTF EMAIL PARSER VALIDATION")
    print("="*60)
    
    # Use relative paths from script location
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    emails_dir = os.path.join(script_dir, 'emails')
    
    results = []
    
    # Test 1: 90-minute class
    results.append(
        test_email(
            os.path.join(emails_dir, 'sample_90_min.html'),
            'ORANGE_90',
            '90-min Orange class'
        )
    )
    
    # Test 2: 60-minute class
    results.append(
        test_email(
            os.path.join(emails_dir, 'sample_60_min.html'),
            'ORANGE_60',
            '60-min Orange class'
        )
    )
    
    # Test 3: Tread 50
    results.append(
        test_email(
            os.path.join(emails_dir, 'sample_tread50.html'),
            'TREAD_50',
            'Tread 50 class'
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

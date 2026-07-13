"""
OTF parser (v3) tests.

Run against synthetic fixture emails in tests/fixtures/ — these mirror the
structure of real OTF performance-summary emails (headers + HTML body) but
contain no personal data, so they are safe to commit and the suite runs in
any clone.
"""

from datetime import datetime
from pathlib import Path

import pytest

from src.parsers.otf_parser_v3 import (
    classify_workout,
    extract_time_from_text,
    parse_otf_email,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# extract_time_from_text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "time_str, expected",
    [
        ("23:45", 23.75),
        (" 3:45 ", 3.75),
        ("0:30", 0.5),
        ("23‌:45", 23.75),  # zero-width non-joiner, as seen in real emails
    ],
)
def test_extract_time_from_text(time_str, expected):
    assert extract_time_from_text(time_str) == pytest.approx(expected)


@pytest.mark.parametrize("bad_input", ["", "not a time", "45 minutes"])
def test_extract_time_from_text_invalid(bad_input):
    assert extract_time_from_text(bad_input) is None


# ---------------------------------------------------------------------------
# classify_workout (pure rule logic, no HTML)
# ---------------------------------------------------------------------------


def _metrics(minutes, present=True, distance=None):
    return {
        "total_time_minutes": minutes,
        "distance_meters": distance,
        "total_distance_meters": distance,
        "present": present,
    }


def test_classify_orange_90_boundary():
    """Combined cardio of exactly 40 minutes tips into ORANGE_90."""
    result = classify_workout(_metrics(25.0), _metrics(15.0))
    assert result["class_type"] == "ORANGE_90"
    assert result["class_minutes"] == 90


def test_classify_orange_60_below_boundary():
    result = classify_workout(_metrics(25.0), _metrics(14.9))
    assert result["class_type"] == "ORANGE_60"
    assert result["class_minutes"] == 60


def test_classify_strength_residual_never_negative():
    """Cardio longer than the class time must not produce negative strength."""
    result = classify_workout(_metrics(60.0), _metrics(35.0))
    assert result["strength_seconds"] == 0


# ---------------------------------------------------------------------------
# Full email parsing (fixture-driven)
# ---------------------------------------------------------------------------


def test_parse_orange_90():
    parsed = parse_otf_email(load_fixture("fixture_orange_90.html"))
    c = parsed["classification"]

    assert parsed["message_id"] == "fixture-orange-90@fixtures.traininghub"
    assert parsed["workout_datetime"] == datetime(2025, 12, 6, 10, 45)

    assert c["class_type"] == "ORANGE_90"
    assert c["class_minutes"] == 90
    assert c["tread_seconds"] == 1425  # 23:45
    assert c["row_seconds"] == 1050  # 17:30
    assert c["strength_seconds"] == 5400 - 1425 - 1050  # residual

    assert parsed["tread"]["present"] is True
    assert parsed["tread"]["distance_meters"] == 5165  # 3.21 miles
    assert parsed["row"]["present"] is True
    assert parsed["row"]["total_distance_meters"] == 4189  # comma-formatted in email

    assert parsed["total_calories"] == 1090
    assert parsed["splat_points"] == 17


def test_parse_orange_60():
    parsed = parse_otf_email(load_fixture("fixture_orange_60.html"))
    c = parsed["classification"]

    assert parsed["message_id"] == "fixture-orange-60@fixtures.traininghub"
    assert parsed["workout_datetime"] == datetime(2025, 12, 5, 9, 30)

    assert c["class_type"] == "ORANGE_60"
    assert c["class_minutes"] == 60
    assert c["tread_seconds"] == 1515  # 25:15
    assert c["row_seconds"] == 225  # 3:45
    assert c["strength_seconds"] == 3600 - 1515 - 225

    assert parsed["tread"]["distance_meters"] == 5149  # 3.20 miles
    assert parsed["row"]["total_distance_meters"] == 932
    assert parsed["total_calories"] == 604
    assert parsed["splat_points"] == 12


def test_parse_tread_50():
    parsed = parse_otf_email(load_fixture("fixture_tread_50.html"))
    c = parsed["classification"]

    assert parsed["workout_datetime"] == datetime(2025, 12, 4, 18, 0)  # 6:00 PM

    assert c["class_type"] == "TREAD_50"
    assert c["class_minutes"] == 50
    assert c["tread_seconds"] == 2670  # 44:30
    assert c["row_seconds"] == 0
    assert c["strength_seconds"] == 0  # no strength component in Tread 50

    assert parsed["tread"]["distance_meters"] == 9253  # 5.75 miles
    assert parsed["row"]["present"] is False


def test_parse_strength_50():
    parsed = parse_otf_email(load_fixture("fixture_strength_50.html"))
    c = parsed["classification"]

    assert parsed["workout_datetime"] == datetime(2025, 12, 3, 7, 15)

    assert c["class_type"] == "STRENGTH_50"
    assert c["class_minutes"] == 50
    assert c["tread_seconds"] == 0
    assert c["row_seconds"] == 0
    assert c["strength_seconds"] == 50 * 60

    assert parsed["tread"]["present"] is False
    assert parsed["row"]["present"] is False
    assert parsed["total_calories"] == 350
    assert parsed["splat_points"] == 3


def test_missing_headers_yield_none_message_id():
    """An email body without header lines must not crash the parser."""
    html_only = load_fixture("fixture_orange_60.html").split("\n\n", 1)[1]
    parsed = parse_otf_email(html_only)
    assert parsed["message_id"] is None
    # Body-derived fields still work
    assert parsed["classification"]["class_type"] == "ORANGE_60"

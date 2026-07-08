"""
OTF parser tests.

Run against synthetic fixture emails in tests/fixtures/ — these mirror the
table structure of real OTF performance-summary emails but contain no
personal data, so they are safe to commit and the suite runs in any clone.
"""

from pathlib import Path

import pytest

from parsers.otf_parser import classify_workout, parse_otf_email, parse_time_to_minutes

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# parse_time_to_minutes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "time_str, expected",
    [
        ("23:45", 23.75),
        ("3:45", 3.75),
        ("1:05:30", 65.5),  # HH:MM:SS
        ("0:30", 0.5),
    ],
)
def test_parse_time_to_minutes(time_str, expected):
    assert parse_time_to_minutes(time_str) == pytest.approx(expected)


@pytest.mark.parametrize("bad_input", [None, "", "not a time"])
def test_parse_time_to_minutes_invalid(bad_input):
    assert parse_time_to_minutes(bad_input) is None


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
    parsed = parse_otf_email(load_fixture("fixture_orange_90.html"), "test-orange-90")
    c = parsed["classification"]

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
    parsed = parse_otf_email(load_fixture("fixture_orange_60.html"), "test-orange-60")
    c = parsed["classification"]

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
    parsed = parse_otf_email(load_fixture("fixture_tread_50.html"), "test-tread-50")
    c = parsed["classification"]

    assert c["class_type"] == "TREAD_50"
    assert c["class_minutes"] == 50
    assert c["tread_seconds"] == 2670  # 44:30
    assert c["row_seconds"] == 0
    assert c["strength_seconds"] == 0  # no strength component in Tread 50

    assert parsed["tread"]["distance_meters"] == 9253  # 5.75 miles
    assert parsed["row"]["present"] is False


def test_parse_strength_50():
    parsed = parse_otf_email(load_fixture("fixture_strength_50.html"), "test-strength-50")
    c = parsed["classification"]

    assert c["class_type"] == "STRENGTH_50"
    assert c["class_minutes"] == 50
    assert c["tread_seconds"] == 0
    assert c["row_seconds"] == 0
    assert c["strength_seconds"] == 50 * 60

    assert parsed["tread"]["present"] is False
    assert parsed["row"]["present"] is False
    assert parsed["total_calories"] == 350
    assert parsed["splat_points"] == 3


def test_message_id_passthrough():
    parsed = parse_otf_email(load_fixture("fixture_orange_60.html"), "msg-abc-123")
    assert parsed["message_id"] == "msg-abc-123"

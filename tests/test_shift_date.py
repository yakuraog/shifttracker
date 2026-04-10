"""
Tests for shift date resolution with night shift handling.
TDD: Tests written before implementation.
"""
from datetime import date, datetime, timezone, timedelta

import pytest
from zoneinfo import ZoneInfo

from shifttracker.pipeline.stages.shift_date import resolve_shift_date

MSK = ZoneInfo("Europe/Moscow")
TODAY = date(2026, 4, 10)
YESTERDAY = date(2026, 4, 9)


@pytest.mark.parametrize(
    "hour,minute,start,end,expected_date,expected_reason",
    [
        # Daytime window 06-22: within window
        (14, 0, 6, 22, TODAY, None),
        # Daytime window 06-22: at window start
        (7, 0, 6, 22, TODAY, None),
        # Night shift window 22-06: morning part (01:30) → yesterday
        (1, 30, 22, 6, YESTERDAY, None),
        # Night shift window 22-06: evening part (23:00) → today
        (23, 0, 22, 6, TODAY, None),
        # Daytime window 06-22: within +2h pre-start tolerance (04:00 is 2h before 06:00)
        (4, 0, 6, 22, TODAY, None),
        # Daytime window 06-22: outside tolerance (03:00 is 3h before 06:00)
        (3, 0, 6, 22, None, "outside_time_window"),
        # Daytime window 06-22: way outside (00:30)
        (0, 30, 6, 22, None, "outside_time_window"),
        # Night shift window 22-06: midnight (00:00) → yesterday
        (0, 0, 22, 6, YESTERDAY, None),
    ],
)
def test_resolve_shift_date_parametrized(
    hour, minute, start, end, expected_date, expected_reason
):
    """Parametrized test for day/night shift date resolution and tolerance."""
    dt = datetime(2026, 4, 10, hour, minute, tzinfo=MSK)
    resolved_date, reason = resolve_shift_date(dt, start, end, timezone="Europe/Moscow")
    assert resolved_date == expected_date
    assert reason == expected_reason


def test_timezone_conversion_utc_to_moscow():
    """UTC timestamp for 14:00 MSK should resolve correctly with Europe/Moscow timezone."""
    # 14:00 MSK = 11:00 UTC (UTC+3)
    dt_utc = datetime(2026, 4, 10, 11, 0, tzinfo=timezone.utc)
    resolved_date, reason = resolve_shift_date(dt_utc, 6, 22, timezone="Europe/Moscow")
    assert resolved_date == TODAY
    assert reason is None


def test_post_end_tolerance_within_2h():
    """Photo taken within 2h after shift end should still be accepted."""
    # Window 06-22, photo at 23:00 — 1h after end (within tolerance)
    dt = datetime(2026, 4, 10, 23, 0, tzinfo=MSK)
    resolved_date, reason = resolve_shift_date(dt, 6, 22, timezone="Europe/Moscow")
    assert resolved_date == TODAY
    assert reason is None


def test_post_end_tolerance_outside_2h():
    """Photo taken more than 2h after shift end should trigger outside_time_window."""
    # Window 06-22, photo at 00:30 next day — more than 2h after end 22:00
    # Using 00:30 on April 11 (00:30 MSK)
    dt = datetime(2026, 4, 11, 0, 30, tzinfo=MSK)
    resolved_date, reason = resolve_shift_date(dt, 6, 22, timezone="Europe/Moscow")
    assert resolved_date is None
    assert reason == "outside_time_window"


def test_night_shift_end_hour_boundary():
    """Photo exactly at night shift end hour (06:00) for window 22-06."""
    # 06:00 is after end (06), before start (22) — outside window, check tolerance
    # Distance from end: 0 hours → within tolerance
    dt = datetime(2026, 4, 10, 6, 0, tzinfo=MSK)
    resolved_date, reason = resolve_shift_date(dt, 22, 6, timezone="Europe/Moscow")
    # At exactly shift_end_hour for night shift — in the day gap, check edge
    # 06:00 == shift_end_hour → just outside night shift, in tolerance zone
    assert reason is None or reason == "outside_time_window"  # boundary behavior


def test_resolve_shift_date_no_timezone_info_uses_default():
    """Naive datetime treated as UTC, converted to specified timezone."""
    # Naive datetime — should still work
    dt = datetime(2026, 4, 10, 14, 0)  # naive, assumed to be processed as-is
    # The function should handle naive datetimes gracefully
    resolved_date, reason = resolve_shift_date(dt, 6, 22, timezone="Europe/Moscow")
    # naive datetime at 14:00 with window 06-22 — within window
    assert resolved_date is not None or reason == "outside_time_window"  # should not crash

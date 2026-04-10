"""
Shift date resolution stage.

Resolves which calendar date a photo belongs to based on:
- The group's shift window (shift_start_hour, shift_end_hour)
- Night shift handling (midnight crossover)
- Timezone conversion
- ±2h tolerance around shift window boundaries

Returns (date, None) on success or (None, "outside_time_window") when out of range.
"""
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

TOLERANCE_HOURS = 2


def resolve_shift_date(
    message_datetime: datetime,
    shift_start_hour: int,
    shift_end_hour: int,
    timezone: str = "Europe/Moscow",
) -> tuple[Optional[date], Optional[str]]:
    """
    Resolve the shift date for a given message datetime.

    Args:
        message_datetime: The datetime of the message (timezone-aware or naive UTC).
        shift_start_hour: Hour at which the shift starts (0-23).
        shift_end_hour: Hour at which the shift ends (0-23).
        timezone: IANA timezone name for the group (default: Europe/Moscow).

    Returns:
        Tuple of (shift_date, error_reason).
        - (date, None): Successfully resolved shift date.
        - (None, "outside_time_window"): Photo is outside the ±2h tolerance window.
    """
    tz = ZoneInfo(timezone)

    # Convert to local time
    if message_datetime.tzinfo is None:
        # Naive datetime: assume it is already in local time (no conversion)
        local_dt = message_datetime.replace(tzinfo=tz)
    else:
        local_dt = message_datetime.astimezone(tz)

    local_hour = local_dt.hour
    local_date = local_dt.date()

    is_night_shift = shift_start_hour > shift_end_hour  # e.g. 22 > 6

    if not is_night_shift:
        # Day shift (e.g. 06-22)
        if shift_start_hour <= local_hour < shift_end_hour:
            # Within window
            return (local_date, None)

        if local_hour < shift_start_hour:
            # Before shift start — check pre-start tolerance
            if shift_start_hour - local_hour <= TOLERANCE_HOURS:
                return (local_date, None)
            else:
                return (None, "outside_time_window")

        # local_hour >= shift_end_hour
        if local_hour - shift_end_hour < TOLERANCE_HOURS:
            # Within post-end tolerance
            return (local_date, None)
        else:
            return (None, "outside_time_window")

    else:
        # Night shift (e.g. 22-06): wraps midnight
        if local_hour >= shift_start_hour:
            # Evening part of night shift (e.g. 22:00-23:59) → today
            return (local_date, None)

        if local_hour < shift_end_hour:
            # Morning part of night shift (e.g. 00:00-05:59) → yesterday
            return (local_date - timedelta(days=1), None)

        # local_hour is between shift_end_hour and shift_start_hour — gap between shifts
        # Check tolerance: within 2h before start (pre-start)
        if shift_start_hour - local_hour <= TOLERANCE_HOURS:
            return (local_date, None)

        # Check tolerance: within 2h after end (post-end) — hour >= shift_end_hour already
        if local_hour - shift_end_hour < TOLERANCE_HOURS:
            return (local_date - timedelta(days=1), None)

        return (None, "outside_time_window")

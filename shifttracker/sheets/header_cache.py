"""In-process header row cache with TTL for Google Sheets header rows.

Key: (spreadsheet_id, sheet_name)
Value: (headers, monotonic timestamp)

Uses time.monotonic() to avoid sensitivity to system clock changes.
"""
import time
from typing import Optional

# Cache: (spreadsheet_id, sheet_name) -> (headers, fetched_at monotonic)
_cache: dict[tuple[str, str], tuple[list[str], float]] = {}

CACHE_TTL = 300  # seconds (5 minutes)


def get_cached(spreadsheet_id: str, sheet_name: str) -> Optional[list[str]]:
    """Return cached headers if present and not expired, else None."""
    key = (spreadsheet_id, sheet_name)
    if key in _cache:
        headers, fetched_at = _cache[key]
        if time.monotonic() - fetched_at < CACHE_TTL:
            return headers
    return None


def set_cached(spreadsheet_id: str, sheet_name: str, headers: list[str]) -> None:
    """Store headers in cache with current monotonic timestamp."""
    _cache[(spreadsheet_id, sheet_name)] = (headers, time.monotonic())


def invalidate(spreadsheet_id: str, sheet_name: str) -> None:
    """Remove a specific cache entry."""
    _cache.pop((spreadsheet_id, sheet_name), None)


def clear_all() -> None:
    """Clear all cache entries. Useful for testing."""
    _cache.clear()

"""Unit tests for shifttracker/sheets/header_cache.py"""
from unittest.mock import patch

import pytest

from shifttracker.sheets import header_cache
from shifttracker.sheets.header_cache import (
    CACHE_TTL,
    clear_all,
    get_cached,
    invalidate,
    set_cached,
)

SPREADSHEET_ID = "spreadsheet_123"
SHEET_NAME = "Sheet1"
HEADERS = ["Name", "01.04", "02.04", "03.04"]


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear cache before and after each test to avoid state leakage."""
    clear_all()
    yield
    clear_all()


def test_cache_miss_returns_none():
    result = get_cached(SPREADSHEET_ID, SHEET_NAME)
    assert result is None


def test_set_and_get():
    set_cached(SPREADSHEET_ID, SHEET_NAME, HEADERS)
    result = get_cached(SPREADSHEET_ID, SHEET_NAME)
    assert result == HEADERS


def test_cache_expiry():
    """Cache entry is expired after CACHE_TTL seconds have elapsed."""
    base_time = 1000.0
    with patch.object(header_cache.time, "monotonic", return_value=base_time):
        set_cached(SPREADSHEET_ID, SHEET_NAME, HEADERS)
    # Advance the clock past CACHE_TTL
    with patch.object(header_cache.time, "monotonic", return_value=base_time + CACHE_TTL + 1):
        result = get_cached(SPREADSHEET_ID, SHEET_NAME)
    assert result is None


def test_cache_not_expired_within_ttl():
    """Cache entry is still valid immediately after being set (within TTL)."""
    base_time = 1000.0
    with patch.object(header_cache.time, "monotonic", return_value=base_time):
        set_cached(SPREADSHEET_ID, SHEET_NAME, HEADERS)
    # Advance by less than CACHE_TTL
    with patch.object(header_cache.time, "monotonic", return_value=base_time + CACHE_TTL - 1):
        result = get_cached(SPREADSHEET_ID, SHEET_NAME)
    assert result == HEADERS


def test_invalidate():
    set_cached(SPREADSHEET_ID, SHEET_NAME, HEADERS)
    assert get_cached(SPREADSHEET_ID, SHEET_NAME) == HEADERS
    invalidate(SPREADSHEET_ID, SHEET_NAME)
    assert get_cached(SPREADSHEET_ID, SHEET_NAME) is None


def test_clear_all():
    set_cached("id1", "Sheet1", ["A", "B"])
    set_cached("id2", "Sheet2", ["C", "D"])
    clear_all()
    assert get_cached("id1", "Sheet1") is None
    assert get_cached("id2", "Sheet2") is None


def test_invalidate_nonexistent_key_no_error():
    """Invalidating a key that doesn't exist should not raise."""
    invalidate("nonexistent", "Sheet1")  # Should not raise


def test_different_keys_independent():
    """Different (spreadsheet_id, sheet_name) pairs are independent cache entries."""
    headers_a = ["Name", "01.04"]
    headers_b = ["Employee", "02.04", "03.04"]
    set_cached("id_a", "Sheet1", headers_a)
    set_cached("id_b", "Sheet1", headers_b)
    assert get_cached("id_a", "Sheet1") == headers_a
    assert get_cached("id_b", "Sheet1") == headers_b
    invalidate("id_a", "Sheet1")
    assert get_cached("id_a", "Sheet1") is None
    assert get_cached("id_b", "Sheet1") == headers_b


def test_cache_ttl_constant_is_300():
    """CACHE_TTL must be exactly 300 seconds (5 minutes)."""
    assert CACHE_TTL == 300

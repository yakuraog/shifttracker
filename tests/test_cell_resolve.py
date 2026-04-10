"""Unit tests for shifttracker/sheets/cell_resolve.py"""
from datetime import date

import pytest

from shifttracker.sheets.cell_resolve import resolve_cell


HEADERS_PADDED = ["Name", "07.04", "08.04", "09.04", "10.04", "11.04"]
HEADERS_UNPADDED = ["Name", "7.4", "8.4", "9.4", "10.4", "11.4"]
HEADERS_WITH_YEAR = ["Name", "07.04.2026", "08.04.2026", "09.04.2026"]
HEADERS_UNPADDED_WITH_YEAR = ["Name", "7.4.2026", "8.4.2026", "9.4.2026"]


def test_resolve_padded_date():
    """Header with zero-padded date '09.04' is found for date(2026, 4, 9)."""
    result = resolve_cell(HEADERS_PADDED, sheet_row=5, shift_date=date(2026, 4, 9))
    assert result is not None
    value_cell, link_cell = result
    # "09.04" is at index 4 (col_idx=4), row=5
    assert value_cell == "D5"
    assert link_cell == "E5"


def test_resolve_unpadded_date():
    """Header with non-padded date '9.4' is found for date(2026, 4, 9)."""
    result = resolve_cell(HEADERS_UNPADDED, sheet_row=3, shift_date=date(2026, 4, 9))
    assert result is not None
    value_cell, link_cell = result
    # "9.4" is at index 4 (col_idx=4), row=3
    assert value_cell == "D3"
    assert link_cell == "E3"


def test_resolve_with_year():
    """Header with full date '09.04.2026' is found for date(2026, 4, 9)."""
    result = resolve_cell(HEADERS_WITH_YEAR, sheet_row=2, shift_date=date(2026, 4, 9))
    assert result is not None
    value_cell, link_cell = result
    # "09.04.2026" is at index 4 (col_idx=4), row=2
    assert value_cell == "D2"
    assert link_cell == "E2"


def test_resolve_unpadded_with_year():
    """Header with non-padded full date '9.4.2026' is found for date(2026, 4, 9)."""
    result = resolve_cell(HEADERS_UNPADDED_WITH_YEAR, sheet_row=7, shift_date=date(2026, 4, 9))
    assert result is not None
    value_cell, link_cell = result
    # "9.4.2026" is at index 4 (col_idx=4), row=7
    assert value_cell == "D7"
    assert link_cell == "E7"


def test_date_not_found_returns_none():
    """When no header matches the shift_date, resolve_cell returns None."""
    result = resolve_cell(HEADERS_PADDED, sheet_row=5, shift_date=date(2026, 4, 25))
    assert result is None


def test_sheet_row_zero_returns_none():
    """sheet_row=0 is invalid and should return None."""
    result = resolve_cell(HEADERS_PADDED, sheet_row=0, shift_date=date(2026, 4, 9))
    assert result is None


def test_sheet_row_none_returns_none():
    """sheet_row=None is invalid and should return None."""
    result = resolve_cell(HEADERS_PADDED, sheet_row=None, shift_date=date(2026, 4, 9))
    assert result is None


def test_link_cell_is_adjacent():
    """The link cell must be exactly one column to the right of the value cell."""
    result = resolve_cell(HEADERS_PADDED, sheet_row=10, shift_date=date(2026, 4, 9))
    assert result is not None
    value_cell, link_cell = result
    # Parse col letters from A1 notation
    import gspread.utils
    value_row, value_col = gspread.utils.a1_to_rowcol(value_cell)
    link_row, link_col = gspread.utils.a1_to_rowcol(link_cell)
    assert link_col == value_col + 1
    assert link_row == value_row


def test_header_with_whitespace_is_stripped():
    """Headers with surrounding whitespace should still match the date."""
    headers_with_spaces = ["Name", " 09.04 ", " 10.04 "]
    result = resolve_cell(headers_with_spaces, sheet_row=1, shift_date=date(2026, 4, 9))
    assert result is not None
    assert result[0] == "B1"


def test_empty_header_row_returns_none():
    """Empty header row returns None (no columns to match)."""
    result = resolve_cell([], sheet_row=5, shift_date=date(2026, 4, 9))
    assert result is None


def test_first_column_match():
    """Date in first column (col_idx=1) resolves correctly."""
    headers = ["09.04", "10.04", "11.04"]
    result = resolve_cell(headers, sheet_row=3, shift_date=date(2026, 4, 9))
    assert result is not None
    assert result[0] == "A3"
    assert result[1] == "B3"

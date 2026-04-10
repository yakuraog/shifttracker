"""Cell address resolution from sheet_row + shift_date against header row."""
from datetime import date
from typing import Optional

import gspread.utils


def resolve_cell(
    header_row: list[str],
    sheet_row: int,
    shift_date: date,
) -> Optional[tuple[str, str]]:
    """Resolve (value_cell_a1, link_cell_a1) or None if date column not found.

    Tries both zero-padded DD.MM and non-padded D.M formats against the header,
    as well as DD.MM.YYYY and D.M.YYYY for full-year headers.
    Returns A1 addresses for the value cell and the adjacent link cell (col+1).

    Args:
        header_row: List of header strings from row 1 of the worksheet.
        sheet_row: 1-indexed row number for the employee (from group_employees.sheet_row).
        shift_date: The date of the shift to resolve.

    Returns:
        Tuple of (value_cell_a1, link_cell_a1) or None if date not found or sheet_row invalid.
    """
    if not sheet_row or sheet_row < 1:
        return None

    # Try multiple date formats for header matching
    candidates = [
        shift_date.strftime("%d.%m"),                                # "09.04"
        f"{shift_date.day}.{shift_date.month}",                      # "9.4" (cross-platform)
        shift_date.strftime("%d.%m.%Y"),                             # "09.04.2026"
        f"{shift_date.day}.{shift_date.month}.{shift_date.year}",   # "9.4.2026"
    ]

    for col_idx, header in enumerate(header_row, start=1):
        stripped = header.strip()
        if stripped in candidates:
            value_cell = gspread.utils.rowcol_to_a1(sheet_row, col_idx)
            link_cell = gspread.utils.rowcol_to_a1(sheet_row, col_idx + 1)
            return value_cell, link_cell

    return None

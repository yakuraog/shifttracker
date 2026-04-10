"""Tests for SheetsWriter: flush loop, batching, retry, and duplicate detection."""
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shifttracker.config import Settings
from shifttracker.db.models import (
    Employee,
    GroupEmployee,
    ProcessingLog,
    ShiftRecord,
    TelegramGroup,
)
from shifttracker.sheets.header_cache import clear_all as clear_header_cache
from shifttracker.sheets.writer import SheetsWriter


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_header_cache():
    """Clear the in-process header cache before each test for isolation."""
    clear_header_cache()
    yield
    clear_header_cache()


def make_settings(**overrides) -> Settings:
    """Return a Settings instance with Sheets enabled (dummy path)."""
    defaults = {
        "bot_token": "test",
        "database_url": "sqlite+aiosqlite://",
        "google_sheets_credentials_file": "/fake/creds.json",
        "sheets_flush_interval": 5,
        "sheets_max_retries": 5,
    }
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture
async def seeded_session(async_session: AsyncSession):
    """Seed DB with one Employee, TelegramGroup, GroupEmployee, and PENDING ShiftRecord."""
    group = TelegramGroup(
        id=uuid.uuid4(),
        chat_id=1001,
        name="Test Group",
        sheet_id="spreadsheet-abc",
        sheet_name="Sheet1",
    )
    employee = Employee(id=uuid.uuid4(), name="Alice")
    ge = GroupEmployee(
        id=uuid.uuid4(),
        group_id=group.id,
        employee_id=employee.id,
        sheet_row=3,
    )
    shift_date = date(2026, 4, 9)
    record = ShiftRecord(
        id=uuid.uuid4(),
        employee_id=employee.id,
        shift_date=shift_date,
        status="CONFIRMED",
        source_message_id=42,
        source_link="https://t.me/c/1001/42",
        sheet_write_status="PENDING",
        retry_count=0,
    )
    # ProcessingLog so writer can resolve chat_id -> TelegramGroup
    plog = ProcessingLog(
        id=uuid.uuid4(),
        update_id=99,
        message_id=42,
        chat_id=1001,
        employee_id=employee.id,
        shift_date=shift_date,
        status="ACCEPTED",
        source_link="https://t.me/c/1001/42",
    )

    async_session.add_all([group, employee, ge, record, plog])
    await async_session.commit()

    return {
        "session": async_session,
        "group": group,
        "employee": employee,
        "ge": ge,
        "record": record,
        "shift_date": shift_date,
    }


def make_mock_gc(headers=None, cell_values=None):
    """Return a mocked gspread Client with controllable batch_get / batch_update / row_values."""
    if headers is None:
        headers = ["Name", "09.04", "09.04 link", "10.04", "10.04 link"]
    if cell_values is None:
        cell_values = [[""]]  # default: empty cells (no duplicate)

    mock_ws = MagicMock()
    mock_ws.row_values.return_value = headers
    # batch_get returns list of ValueRanges; each ValueRange is a list of lists
    mock_ws.batch_get.return_value = [cell_values]
    mock_ws.batch_update.return_value = None

    mock_spreadsheet = MagicMock()
    mock_spreadsheet.worksheet.return_value = mock_ws

    mock_gc = MagicMock()
    mock_gc.open_by_key.return_value = mock_spreadsheet

    return mock_gc, mock_ws


# ---------------------------------------------------------------------------
# TDD Test cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_one_cell(seeded_session):
    """A single PENDING ShiftRecord results in batch_update with '1' at correct A1 address
    and status updated to WRITTEN with written_at set."""
    data = seeded_session
    session: AsyncSession = data["session"]
    record: ShiftRecord = data["record"]

    mock_gc, mock_ws = make_mock_gc(
        headers=["Name", "09.04", "09.04 link"],
        cell_values=[[""]],
    )

    settings = make_settings()

    async def session_factory_fn():
        return session

    writer = SheetsWriter(settings=settings, session_factory=session_factory_fn)

    with patch("shifttracker.sheets.writer.build_client", return_value=mock_gc), \
         patch("shifttracker.sheets.writer.os.path.exists", return_value=True):
        writer._gc = mock_gc
        await writer._flush()

    mock_ws.batch_update.assert_called_once()
    call_args = mock_ws.batch_update.call_args
    ranges_data = call_args[0][0]  # first positional arg: list of dicts
    range_keys = [item["range"] for item in ranges_data]
    assert "B3" in range_keys  # 09.04 is col 2 -> B, row 3

    # Check value cells contain "1"
    value_updates = {item["range"]: item["values"] for item in ranges_data}
    assert value_updates["B3"] == [["1"]]

    # Refresh record from DB
    await session.refresh(record)
    assert record.sheet_write_status == "WRITTEN"
    assert record.written_at is not None


@pytest.mark.asyncio
async def test_source_link_written(seeded_session):
    """batch_update payload includes the source_link in the adjacent cell."""
    data = seeded_session
    session: AsyncSession = data["session"]
    record: ShiftRecord = data["record"]

    mock_gc, mock_ws = make_mock_gc(
        headers=["Name", "09.04", "09.04 link"],
        cell_values=[[""]],
    )

    settings = make_settings()

    async def session_factory_fn():
        return session

    writer = SheetsWriter(settings=settings, session_factory=session_factory_fn)
    writer._gc = mock_gc

    await writer._flush()

    call_args = mock_ws.batch_update.call_args
    ranges_data = call_args[0][0]
    value_updates = {item["range"]: item["values"] for item in ranges_data}

    # Link cell is col+1 = C3
    assert "C3" in value_updates
    assert value_updates["C3"] == [["https://t.me/c/1001/42"]]


@pytest.mark.asyncio
async def test_date_column_not_found(seeded_session):
    """PENDING record where shift_date does not match any header column -> status=ERROR."""
    data = seeded_session
    session: AsyncSession = data["session"]
    record: ShiftRecord = data["record"]

    # Headers without the shift date (09.04 is missing)
    mock_gc, mock_ws = make_mock_gc(
        headers=["Name", "01.04", "01.04 link"],
        cell_values=[[""]],
    )

    settings = make_settings()

    async def session_factory_fn():
        return session

    writer = SheetsWriter(settings=settings, session_factory=session_factory_fn)
    writer._gc = mock_gc

    await writer._flush()

    await session.refresh(record)
    assert record.sheet_write_status == "ERROR"
    # Find ProcessingLog reason
    result = await session.execute(
        select(ProcessingLog).where(
            ProcessingLog.employee_id == record.employee_id,
            ProcessingLog.shift_date == record.shift_date,
            ProcessingLog.status == "ERROR",
        )
    )
    log_entry = result.scalar_one_or_none()
    assert log_entry is not None
    assert "date_column_not_found" in log_entry.reason


@pytest.mark.asyncio
async def test_employee_row_not_configured(async_session: AsyncSession):
    """PENDING record where GroupEmployee.sheet_row is None -> status=ERROR."""
    group = TelegramGroup(
        id=uuid.uuid4(),
        chat_id=2001,
        name="Group B",
        sheet_id="spreadsheet-xyz",
        sheet_name="Sheet1",
    )
    employee = Employee(id=uuid.uuid4(), name="Bob")
    ge = GroupEmployee(
        id=uuid.uuid4(),
        group_id=group.id,
        employee_id=employee.id,
        sheet_row=None,  # Not configured
    )
    shift_date = date(2026, 4, 9)
    record = ShiftRecord(
        id=uuid.uuid4(),
        employee_id=employee.id,
        shift_date=shift_date,
        status="CONFIRMED",
        source_message_id=43,
        source_link="https://t.me/c/2001/43",
        sheet_write_status="PENDING",
        retry_count=0,
    )
    plog = ProcessingLog(
        id=uuid.uuid4(),
        update_id=100,
        message_id=43,
        chat_id=2001,
        employee_id=employee.id,
        shift_date=shift_date,
        status="ACCEPTED",
        source_link="https://t.me/c/2001/43",
    )

    async_session.add_all([group, employee, ge, record, plog])
    await async_session.commit()

    mock_gc, mock_ws = make_mock_gc()
    settings = make_settings()

    async def session_factory_fn():
        return async_session

    writer = SheetsWriter(settings=settings, session_factory=session_factory_fn)
    writer._gc = mock_gc

    await writer._flush()

    await async_session.refresh(record)
    assert record.sheet_write_status == "ERROR"

    result = await async_session.execute(
        select(ProcessingLog).where(
            ProcessingLog.employee_id == record.employee_id,
            ProcessingLog.shift_date == record.shift_date,
            ProcessingLog.status == "ERROR",
        )
    )
    log_entry = result.scalar_one_or_none()
    assert log_entry is not None
    assert "employee_row_not_configured" in log_entry.reason


@pytest.mark.asyncio
async def test_duplicate_sheet_skip(seeded_session):
    """When the cell already contains '1', write is skipped and DUPLICATE_SHEET_SKIP log created."""
    data = seeded_session
    session: AsyncSession = data["session"]
    record: ShiftRecord = data["record"]

    # batch_get returns "1" — cell already written
    mock_gc, mock_ws = make_mock_gc(
        headers=["Name", "09.04", "09.04 link"],
        cell_values=[["1"]],
    )

    settings = make_settings()

    async def session_factory_fn():
        return session

    writer = SheetsWriter(settings=settings, session_factory=session_factory_fn)
    writer._gc = mock_gc

    await writer._flush()

    # batch_update should NOT have been called
    mock_ws.batch_update.assert_not_called()

    # A DUPLICATE_SHEET_SKIP log entry should exist
    result = await session.execute(
        select(ProcessingLog).where(
            ProcessingLog.employee_id == record.employee_id,
            ProcessingLog.shift_date == record.shift_date,
            ProcessingLog.status == "DUPLICATE_SHEET_SKIP",
        )
    )
    log_entry = result.scalar_one_or_none()
    assert log_entry is not None


@pytest.mark.asyncio
async def test_batch_groups_by_spreadsheet(async_session: AsyncSession):
    """Two records for same spreadsheet result in one batch_update call.
    Two records for different spreadsheets result in two batch_update calls."""
    # --- Same spreadsheet: 2 employees, 1 spreadsheet ---
    group1 = TelegramGroup(
        id=uuid.uuid4(), chat_id=3001, name="Group1",
        sheet_id="same-sheet", sheet_name="Sheet1",
    )
    emp1 = Employee(id=uuid.uuid4(), name="Emp1")
    emp2 = Employee(id=uuid.uuid4(), name="Emp2")
    ge1 = GroupEmployee(id=uuid.uuid4(), group_id=group1.id, employee_id=emp1.id, sheet_row=2)
    ge2 = GroupEmployee(id=uuid.uuid4(), group_id=group1.id, employee_id=emp2.id, sheet_row=3)
    shift_date = date(2026, 4, 9)

    rec1 = ShiftRecord(
        id=uuid.uuid4(), employee_id=emp1.id, shift_date=shift_date,
        status="CONFIRMED", source_message_id=51, source_link="https://t.me/c/3001/51",
        sheet_write_status="PENDING", retry_count=0,
    )
    rec2 = ShiftRecord(
        id=uuid.uuid4(), employee_id=emp2.id, shift_date=shift_date,
        status="CONFIRMED", source_message_id=52, source_link="https://t.me/c/3001/52",
        sheet_write_status="PENDING", retry_count=0,
    )
    plog1 = ProcessingLog(
        id=uuid.uuid4(), update_id=201, message_id=51, chat_id=3001,
        employee_id=emp1.id, shift_date=shift_date, status="ACCEPTED",
        source_link="https://t.me/c/3001/51",
    )
    plog2 = ProcessingLog(
        id=uuid.uuid4(), update_id=202, message_id=52, chat_id=3001,
        employee_id=emp2.id, shift_date=shift_date, status="ACCEPTED",
        source_link="https://t.me/c/3001/52",
    )
    async_session.add_all([group1, emp1, emp2, ge1, ge2, rec1, rec2, plog1, plog2])
    await async_session.commit()

    mock_gc, mock_ws = make_mock_gc(
        headers=["Name", "09.04", "09.04 link"],
        cell_values=[[""]],
    )
    # batch_get for both records returns empty
    mock_ws.batch_get.return_value = [[[""]], [[""]]]

    settings = make_settings()

    async def session_factory_fn():
        return async_session

    writer = SheetsWriter(settings=settings, session_factory=session_factory_fn)
    writer._gc = mock_gc

    await writer._flush()

    # Only one batch_update call for one spreadsheet
    assert mock_ws.batch_update.call_count == 1

    # --- Different spreadsheets ---
    # Reset mock
    mock_ws.batch_update.reset_mock()
    mock_ws.batch_get.return_value = [[[""]]]

    group2 = TelegramGroup(
        id=uuid.uuid4(), chat_id=3002, name="Group2",
        sheet_id="other-sheet", sheet_name="Sheet1",
    )
    emp3 = Employee(id=uuid.uuid4(), name="Emp3")
    ge3 = GroupEmployee(id=uuid.uuid4(), group_id=group2.id, employee_id=emp3.id, sheet_row=2)

    rec3 = ShiftRecord(
        id=uuid.uuid4(), employee_id=emp3.id, shift_date=date(2026, 4, 10),
        status="CONFIRMED", source_message_id=53, source_link="https://t.me/c/3002/53",
        sheet_write_status="PENDING", retry_count=0,
    )
    plog3 = ProcessingLog(
        id=uuid.uuid4(), update_id=203, message_id=53, chat_id=3002,
        employee_id=emp3.id, shift_date=date(2026, 4, 10), status="ACCEPTED",
        source_link="https://t.me/c/3002/53",
    )
    async_session.add_all([group2, emp3, ge3, rec3, plog3])
    await async_session.commit()

    mock_gc2, mock_ws2 = make_mock_gc(
        headers=["Name", "10.04", "10.04 link"],
        cell_values=[[""]],
    )
    # Two different worksheets for two different spreadsheets
    mock_spreadsheet1 = MagicMock()
    mock_spreadsheet1.worksheet.return_value = mock_ws

    mock_spreadsheet2 = MagicMock()
    mock_spreadsheet2.worksheet.return_value = mock_ws2

    def open_by_key_side_effect(key):
        if key == "same-sheet":
            return mock_spreadsheet1
        elif key == "other-sheet":
            return mock_spreadsheet2
        raise ValueError(f"Unknown key: {key}")

    mock_gc.open_by_key.side_effect = open_by_key_side_effect

    await writer._flush()

    # rec1+rec2 are already WRITTEN (from first flush), so same-sheet gets 0 new calls
    # only rec3 (other-sheet) is still PENDING -> triggers 1 call on mock_ws2
    assert mock_ws.batch_update.call_count == 0   # same-sheet: emp1+emp2 already WRITTEN
    assert mock_ws2.batch_update.call_count == 1  # other-sheet: emp3 written now


@pytest.mark.asyncio
async def test_retry_on_api_error(seeded_session):
    """When batch_update raises APIError, retry_count is incremented and status stays PENDING."""
    import gspread.exceptions

    data = seeded_session
    session: AsyncSession = data["session"]
    record: ShiftRecord = data["record"]

    mock_gc, mock_ws = make_mock_gc(
        headers=["Name", "09.04", "09.04 link"],
        cell_values=[[""]],
    )
    mock_ws.batch_update.side_effect = gspread.exceptions.APIError(
        MagicMock(status_code=500, text="Internal Server Error")
    )

    settings = make_settings()

    async def session_factory_fn():
        return session

    writer = SheetsWriter(settings=settings, session_factory=session_factory_fn)
    writer._gc = mock_gc

    await writer._flush()

    await session.refresh(record)
    assert record.sheet_write_status == "PENDING"
    assert record.retry_count == 1


@pytest.mark.asyncio
async def test_max_retries_sets_error(seeded_session):
    """When retry_count reaches sheets_max_retries (5), status is set to ERROR."""
    import gspread.exceptions

    data = seeded_session
    session: AsyncSession = data["session"]
    record: ShiftRecord = data["record"]

    # Pre-set retry_count to max_retries - 1 so the next failure tips it over
    record.retry_count = 4
    await session.commit()

    mock_gc, mock_ws = make_mock_gc(
        headers=["Name", "09.04", "09.04 link"],
        cell_values=[[""]],
    )
    mock_ws.batch_update.side_effect = gspread.exceptions.APIError(
        MagicMock(status_code=500, text="Internal Server Error")
    )

    settings = make_settings()

    async def session_factory_fn():
        return session

    writer = SheetsWriter(settings=settings, session_factory=session_factory_fn)
    writer._gc = mock_gc

    await writer._flush()

    await session.refresh(record)
    assert record.sheet_write_status == "ERROR"


@pytest.mark.asyncio
async def test_records_with_no_sheet_id_skipped(async_session: AsyncSession):
    """PENDING records whose TelegramGroup has sheet_id=None are skipped."""
    group = TelegramGroup(
        id=uuid.uuid4(), chat_id=4001, name="No Sheet Group",
        sheet_id=None, sheet_name="Sheet1",
    )
    employee = Employee(id=uuid.uuid4(), name="Carol")
    ge = GroupEmployee(id=uuid.uuid4(), group_id=group.id, employee_id=employee.id, sheet_row=2)
    shift_date = date(2026, 4, 9)
    record = ShiftRecord(
        id=uuid.uuid4(), employee_id=employee.id, shift_date=shift_date,
        status="CONFIRMED", source_message_id=61, source_link="https://t.me/c/4001/61",
        sheet_write_status="PENDING", retry_count=0,
    )
    plog = ProcessingLog(
        id=uuid.uuid4(), update_id=301, message_id=61, chat_id=4001,
        employee_id=employee.id, shift_date=shift_date, status="ACCEPTED",
        source_link="https://t.me/c/4001/61",
    )
    async_session.add_all([group, employee, ge, record, plog])
    await async_session.commit()

    mock_gc, mock_ws = make_mock_gc()
    settings = make_settings()

    async def session_factory_fn():
        return async_session

    writer = SheetsWriter(settings=settings, session_factory=session_factory_fn)
    writer._gc = mock_gc

    await writer._flush()

    # batch_update must NOT have been called
    mock_ws.batch_update.assert_not_called()

    # Record should still be PENDING (just skipped, not errored)
    await async_session.refresh(record)
    assert record.sheet_write_status == "PENDING"


@pytest.mark.asyncio
async def test_flush_updates_written_at(seeded_session):
    """After successful write, written_at is set to a non-None datetime."""
    data = seeded_session
    session: AsyncSession = data["session"]
    record: ShiftRecord = data["record"]

    mock_gc, mock_ws = make_mock_gc(
        headers=["Name", "09.04", "09.04 link"],
        cell_values=[[""]],
    )

    settings = make_settings()

    async def session_factory_fn():
        return session

    writer = SheetsWriter(settings=settings, session_factory=session_factory_fn)
    writer._gc = mock_gc

    assert record.written_at is None  # precondition

    await writer._flush()

    await session.refresh(record)
    assert record.written_at is not None
    assert isinstance(record.written_at, datetime)

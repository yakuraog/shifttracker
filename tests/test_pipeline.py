"""End-to-end pipeline tests.

TDD RED phase — tests prove the full pipeline flow:
Dedup -> Identify -> Resolve Date -> Business Dedup -> Write ShiftRecord + ProcessingLog
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from shifttracker.db.models import Employee, GroupEmployee, ProcessingLog, ShiftRecord, TelegramGroup
from shifttracker.pipeline.models import ProcessingContext
from shifttracker.pipeline.worker import process_message


def _make_ctx(
    *,
    update_id: int = 1001,
    message_id: int = 1,
    chat_id: int = -1001234567890,
    sender_user_id=None,
    caption: str | None = None,
    group_id=None,
    shift_start_hour: int = 6,
    shift_end_hour: int = 22,
    message_datetime: datetime | None = None,
    source_link: str = "https://t.me/c/1234567890/1",
) -> ProcessingContext:
    if message_datetime is None:
        # 10:00 UTC — well within a 06-22 shift window (day shift)
        message_datetime = datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc)
    return ProcessingContext(
        update_id=update_id,
        message_id=message_id,
        chat_id=chat_id,
        sender_user_id=sender_user_id,
        caption=caption,
        message_datetime=message_datetime,
        group_id=group_id,
        shift_start_hour=shift_start_hour,
        shift_end_hour=shift_end_hour,
        source_link=source_link,
    )


async def _make_employee_in_group(session, name="Alice", telegram_user_id=None):
    """Helper: create Employee + TelegramGroup + GroupEmployee, return (employee, group)."""
    group = TelegramGroup(
        chat_id=-1001234567890,
        name="Test Group",
        shift_start_hour=6,
        shift_end_hour=22,
        timezone="UTC",
    )
    session.add(group)
    await session.flush()

    employee = Employee(name=name, telegram_user_id=telegram_user_id)
    session.add(employee)
    await session.flush()

    link = GroupEmployee(group_id=group.id, employee_id=employee.id)
    session.add(link)
    await session.flush()

    return employee, group


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline_accepted(self, async_session):
        """Valid photo + known employee + within shift window → CONFIRMED ShiftRecord + ACCEPTED log."""
        employee, group = await _make_employee_in_group(
            async_session, name="Alice", telegram_user_id=111
        )

        ctx = _make_ctx(
            update_id=2001,
            sender_user_id=111,
            group_id=group.id,
        )

        await process_message(ctx, async_session)

        shifts = (await async_session.execute(select(ShiftRecord))).scalars().all()
        assert len(shifts) == 1
        assert shifts[0].status == "CONFIRMED"
        assert shifts[0].employee_id == employee.id

        logs = (await async_session.execute(select(ProcessingLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].status == "ACCEPTED"
        assert logs[0].source_link is not None

    @pytest.mark.asyncio
    async def test_unknown_employee_needs_review(self, async_session):
        """Unknown employee → NEEDS_REVIEW log, no ShiftRecord."""
        # No employee created — identification will fail
        ctx = _make_ctx(
            update_id=2002,
            sender_user_id=999,  # unknown
        )

        await process_message(ctx, async_session)

        shifts = (await async_session.execute(select(ShiftRecord))).scalars().all()
        assert len(shifts) == 0

        logs = (await async_session.execute(select(ProcessingLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].status == "NEEDS_REVIEW"
        assert "no_employee_identified" in (logs[0].reason or "")

    @pytest.mark.asyncio
    async def test_outside_time_window_needs_review(self, async_session):
        """Known employee but photo sent outside shift window → NEEDS_REVIEW with outside_time_window."""
        employee, group = await _make_employee_in_group(
            async_session, name="Bob", telegram_user_id=222
        )

        # 02:00 UTC — outside 06-22 day shift (not within ±2h tolerance either)
        outside_dt = datetime(2026, 4, 10, 2, 0, 0, tzinfo=timezone.utc)
        ctx = _make_ctx(
            update_id=2003,
            sender_user_id=222,
            group_id=group.id,
            message_datetime=outside_dt,
        )

        await process_message(ctx, async_session)

        shifts = (await async_session.execute(select(ShiftRecord))).scalars().all()
        assert len(shifts) == 0

        logs = (await async_session.execute(select(ProcessingLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].status == "NEEDS_REVIEW"
        assert logs[0].reason == "outside_time_window"

    @pytest.mark.asyncio
    async def test_business_duplicate_same_shift(self, async_session):
        """Known employee, shift_record already exists for same date → DUPLICATE_SAME_SHIFT."""
        employee, group = await _make_employee_in_group(
            async_session, name="Charlie", telegram_user_id=333
        )
        from datetime import date

        # Pre-existing shift record for the same date
        existing_record = ShiftRecord(
            employee_id=employee.id,
            shift_date=date(2026, 4, 10),
            status="CONFIRMED",
            source_message_id=9000,
            source_link="https://t.me/c/123/9000",
        )
        async_session.add(existing_record)
        await async_session.flush()

        ctx = _make_ctx(
            update_id=2004,
            sender_user_id=333,
            group_id=group.id,
        )

        await process_message(ctx, async_session)

        # No new ShiftRecord added
        shifts = (await async_session.execute(select(ShiftRecord))).scalars().all()
        assert len(shifts) == 1  # only the pre-existing one

        logs = (await async_session.execute(select(ProcessingLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].status == "DUPLICATE_SAME_SHIFT"

    @pytest.mark.asyncio
    async def test_duplicate_update_id_no_records(self, async_session):
        """Duplicate update_id → no new processing, no new ShiftRecord or ProcessingLog."""
        employee, group = await _make_employee_in_group(
            async_session, name="Dave", telegram_user_id=444
        )

        ctx = _make_ctx(
            update_id=2005,
            sender_user_id=444,
            group_id=group.id,
        )

        # First call — should be processed normally
        await process_message(ctx, async_session)

        # Second call with same update_id — should be skipped
        ctx2 = _make_ctx(
            update_id=2005,  # same update_id
            sender_user_id=444,
            group_id=group.id,
        )
        await process_message(ctx2, async_session)

        # Only one ShiftRecord from the first call
        shifts = (await async_session.execute(select(ShiftRecord))).scalars().all()
        assert len(shifts) == 1

        # Only one ProcessingLog from the first call
        logs = (await async_session.execute(select(ProcessingLog))).scalars().all()
        assert len(logs) == 1

    @pytest.mark.asyncio
    async def test_multiple_employees_multiple_records(self, async_session):
        """Multiple employees identified → separate ShiftRecord and ProcessingLog for each."""
        group = TelegramGroup(
            chat_id=-1001234567891,
            name="Multi Group",
            shift_start_hour=6,
            shift_end_hour=22,
            timezone="UTC",
        )
        async_session.add(group)
        await async_session.flush()

        emp1 = Employee(name="Eve")
        emp2 = Employee(name="Frank")
        async_session.add_all([emp1, emp2])
        await async_session.flush()

        # Both employees in the group
        async_session.add_all([
            GroupEmployee(group_id=group.id, employee_id=emp1.id),
            GroupEmployee(group_id=group.id, employee_id=emp2.id),
        ])
        await async_session.flush()

        # Caption contains both names → caption_exact match for both
        ctx = _make_ctx(
            update_id=2006,
            chat_id=-1001234567891,
            group_id=group.id,
            caption="Eve и Frank пришли",
        )

        await process_message(ctx, async_session)

        shifts = (await async_session.execute(select(ShiftRecord))).scalars().all()
        assert len(shifts) == 2

        logs = (await async_session.execute(select(ProcessingLog))).scalars().all()
        assert len(logs) == 2
        statuses = {log.status for log in logs}
        assert statuses == {"ACCEPTED"}

    @pytest.mark.asyncio
    async def test_shift_record_sheet_write_status_pending(self, async_session):
        """Successful processing sets ShiftRecord.sheet_write_status = PENDING."""
        employee, group = await _make_employee_in_group(
            async_session, name="Grace", telegram_user_id=555
        )

        ctx = _make_ctx(
            update_id=2007,
            sender_user_id=555,
            group_id=group.id,
        )

        await process_message(ctx, async_session)

        shifts = (await async_session.execute(select(ShiftRecord))).scalars().all()
        assert len(shifts) == 1
        assert shifts[0].sheet_write_status == "PENDING"

    @pytest.mark.asyncio
    async def test_processing_log_source_link_populated(self, async_session):
        """ProcessingLog.source_link is populated for every log entry."""
        employee, group = await _make_employee_in_group(
            async_session, name="Heidi", telegram_user_id=666
        )

        expected_link = "https://t.me/c/1234567890/42"
        ctx = _make_ctx(
            update_id=2008,
            sender_user_id=666,
            group_id=group.id,
            source_link=expected_link,
        )

        await process_message(ctx, async_session)

        logs = (await async_session.execute(select(ProcessingLog))).scalars().all()
        assert len(logs) == 1
        assert logs[0].source_link == expected_link

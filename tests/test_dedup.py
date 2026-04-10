"""Tests for the deduplication pipeline stage.

TDD RED phase — tests are written before implementation.
"""
import uuid
from datetime import date

import pytest

from shifttracker.pipeline.stages.deduplicate import check_duplicate, check_business_duplicate


class TestCheckDuplicate:
    @pytest.mark.asyncio
    async def test_new_update_id_is_not_duplicate(self, async_session):
        """check_duplicate returns False for an update_id never seen before."""
        result = await check_duplicate(update_id=1001, session=async_session)
        assert result is False, "A new update_id should not be a duplicate"

    @pytest.mark.asyncio
    async def test_same_update_id_second_call_is_duplicate(self, async_session):
        """check_duplicate returns True on the second call with the same update_id."""
        update_id = 2001
        first = await check_duplicate(update_id=update_id, session=async_session)
        second = await check_duplicate(update_id=update_id, session=async_session)
        assert first is False, "First call should not be a duplicate"
        assert second is True, "Second call with same update_id should be a duplicate"

    @pytest.mark.asyncio
    async def test_inserts_into_processed_updates_on_first_call(self, async_session):
        """After check_duplicate for a new id, the record exists in processed_updates."""
        from sqlalchemy import select
        from shifttracker.db.models import ProcessedUpdate

        update_id = 3001
        await check_duplicate(update_id=update_id, session=async_session)

        result = await async_session.execute(
            select(ProcessedUpdate).where(ProcessedUpdate.update_id == update_id)
        )
        record = result.scalar_one_or_none()
        assert record is not None, "ProcessedUpdate record should be created on first call"
        assert record.update_id == update_id

    @pytest.mark.asyncio
    async def test_different_update_ids_are_independent(self, async_session):
        """Two different update_ids are both non-duplicate on first call."""
        first_result = await check_duplicate(update_id=4001, session=async_session)
        second_result = await check_duplicate(update_id=4002, session=async_session)
        assert first_result is False
        assert second_result is False


class TestCheckBusinessDuplicate:
    @pytest.mark.asyncio
    async def test_no_existing_shift_record_returns_false(self, async_session):
        """check_business_duplicate returns False when no record exists."""
        employee_id = uuid.uuid4()
        shift_date = date(2026, 4, 10)

        result = await check_business_duplicate(
            employee_id=employee_id,
            shift_date=shift_date,
            session=async_session,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_existing_shift_record_returns_true(self, async_session):
        """check_business_duplicate returns True when ShiftRecord exists for employee+date."""
        from shifttracker.db.models import Employee, ShiftRecord

        # Create an employee first
        employee = Employee(name="Test Worker")
        async_session.add(employee)
        await async_session.flush()

        shift_date = date(2026, 4, 10)
        shift_record = ShiftRecord(
            employee_id=employee.id,
            shift_date=shift_date,
            status="CONFIRMED",
            source_message_id=1234,
            source_link="https://t.me/c/123/1234",
        )
        async_session.add(shift_record)
        await async_session.flush()

        result = await check_business_duplicate(
            employee_id=employee.id,
            shift_date=shift_date,
            session=async_session,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_different_employee_same_date_not_duplicate(self, async_session):
        """Different employee with same date is not a duplicate."""
        from shifttracker.db.models import Employee, ShiftRecord

        employee1 = Employee(name="Worker One")
        employee2 = Employee(name="Worker Two")
        async_session.add_all([employee1, employee2])
        await async_session.flush()

        shift_date = date(2026, 4, 11)
        shift_record = ShiftRecord(
            employee_id=employee1.id,
            shift_date=shift_date,
            status="CONFIRMED",
            source_message_id=5678,
            source_link="https://t.me/c/123/5678",
        )
        async_session.add(shift_record)
        await async_session.flush()

        # employee2 does not have a record for this date
        result = await check_business_duplicate(
            employee_id=employee2.id,
            shift_date=shift_date,
            session=async_session,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_same_employee_different_date_not_duplicate(self, async_session):
        """Same employee but different date is not a duplicate."""
        from shifttracker.db.models import Employee, ShiftRecord

        employee = Employee(name="Worker Three")
        async_session.add(employee)
        await async_session.flush()

        shift_record = ShiftRecord(
            employee_id=employee.id,
            shift_date=date(2026, 4, 10),
            status="CONFIRMED",
            source_message_id=9999,
            source_link="https://t.me/c/123/9999",
        )
        async_session.add(shift_record)
        await async_session.flush()

        result = await check_business_duplicate(
            employee_id=employee.id,
            shift_date=date(2026, 4, 11),  # different date
            session=async_session,
        )
        assert result is False

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from shifttracker.db.models import (
    CaptionRule,
    Employee,
    GroupEmployee,
    ProcessedUpdate,
    ProcessingLog,
    ShiftRecord,
    TelegramGroup,
)


async def test_employee_fields(async_session):
    """Employee model has required fields and can be created and queried."""
    emp = Employee(name="Иванов Иван Иванович")
    async_session.add(emp)
    await async_session.commit()
    await async_session.refresh(emp)

    assert isinstance(emp.id, uuid.UUID)
    assert emp.name == "Иванов Иван Иванович"
    assert emp.telegram_user_id is None
    assert emp.employee_code is None
    assert emp.created_at is not None


async def test_employee_query_returns_correct_data(async_session):
    """Creating an Employee and querying it back returns correct data."""
    emp = Employee(
        name="Петров Петр",
        telegram_user_id=123456789,
        employee_code="EMP-001",
    )
    async_session.add(emp)
    await async_session.commit()

    result = await async_session.execute(select(Employee).where(Employee.employee_code == "EMP-001"))
    fetched = result.scalar_one()
    assert fetched.name == "Петров Петр"
    assert fetched.telegram_user_id == 123456789


async def test_telegram_group_fields(async_session):
    """TelegramGroup model has correct fields with defaults for shift hours."""
    group = TelegramGroup(chat_id=-100123456789, name="Test Group")
    async_session.add(group)
    await async_session.commit()
    await async_session.refresh(group)

    assert isinstance(group.id, uuid.UUID)
    assert group.chat_id == -100123456789
    assert group.name == "Test Group"
    assert group.shift_start_hour == 6
    assert group.shift_end_hour == 22
    assert group.timezone == "Europe/Moscow"
    assert group.is_active is True


async def test_group_employee_fields_and_unique_constraint(async_session):
    """GroupEmployee links group and employee, has unique constraint on (group_id, employee_id)."""
    emp = Employee(name="Сидоров Сидор")
    group = TelegramGroup(chat_id=-100111222333, name="Group A")
    async_session.add_all([emp, group])
    await async_session.commit()

    ge = GroupEmployee(group_id=group.id, employee_id=emp.id, sheet_row=5)
    async_session.add(ge)
    await async_session.commit()
    await async_session.refresh(ge)

    assert ge.sheet_row == 5

    # Duplicate should raise
    ge_dup = GroupEmployee(group_id=group.id, employee_id=emp.id)
    async_session.add(ge_dup)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_caption_rule_fields(async_session):
    """CaptionRule model has group_id, pattern, employee_id fields."""
    emp = Employee(name="Кузнецов Кузьма")
    group = TelegramGroup(chat_id=-100444555666, name="Group B")
    async_session.add_all([emp, group])
    await async_session.commit()

    rule = CaptionRule(group_id=group.id, pattern="кузнецов", employee_id=emp.id)
    async_session.add(rule)
    await async_session.commit()
    await async_session.refresh(rule)

    assert isinstance(rule.id, uuid.UUID)
    assert rule.pattern == "кузнецов"


async def test_shift_record_fields_and_unique_constraint(async_session):
    """ShiftRecord unique constraint on (employee_id, shift_date) raises IntegrityError on duplicate."""
    emp = Employee(name="Морозов Михаил")
    async_session.add(emp)
    await async_session.commit()

    shift = ShiftRecord(
        employee_id=emp.id,
        shift_date=date(2026, 4, 10),
        status="CONFIRMED",
        source_message_id=9999,
        source_link="https://t.me/c/123/456",
        sheet_write_status="PENDING",
    )
    async_session.add(shift)
    await async_session.commit()
    await async_session.refresh(shift)

    assert isinstance(shift.id, uuid.UUID)
    assert shift.status == "CONFIRMED"
    assert shift.sheet_write_status == "PENDING"
    assert shift.source_link == "https://t.me/c/123/456"

    # Duplicate (employee_id, shift_date) should raise IntegrityError
    shift_dup = ShiftRecord(
        employee_id=emp.id,
        shift_date=date(2026, 4, 10),
        status="NEEDS_REVIEW",
        source_message_id=10000,
        source_link="https://t.me/c/123/457",
    )
    async_session.add(shift_dup)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_processing_log_fields(async_session):
    """ProcessingLog stores status, reason, source_link, and timestamps for every message."""
    emp = Employee(name="Волков Владимир")
    async_session.add(emp)
    await async_session.commit()

    log_entry = ProcessingLog(
        update_id=111111,
        message_id=222222,
        chat_id=-100777888999,
        employee_id=emp.id,
        shift_date=date(2026, 4, 10),
        status="ACCEPTED",
        reason=None,
        source_link="https://t.me/c/777/222",
    )
    async_session.add(log_entry)
    await async_session.commit()
    await async_session.refresh(log_entry)

    assert isinstance(log_entry.id, uuid.UUID)
    assert log_entry.status == "ACCEPTED"
    assert log_entry.source_link == "https://t.me/c/777/222"
    assert log_entry.created_at is not None

    # Test without optional fields
    log_skipped = ProcessingLog(
        update_id=333333,
        message_id=444444,
        chat_id=-100777888999,
        status="SKIPPED",
        reason="no_photo",
    )
    async_session.add(log_skipped)
    await async_session.commit()
    await async_session.refresh(log_skipped)
    assert log_skipped.employee_id is None
    assert log_skipped.reason == "no_photo"


async def test_processed_update_unique_constraint(async_session):
    """Inserting duplicate update_id into ProcessedUpdate raises IntegrityError."""
    pu1 = ProcessedUpdate(update_id=555555)
    async_session.add(pu1)
    await async_session.commit()

    pu_dup = ProcessedUpdate(update_id=555555)
    async_session.add(pu_dup)
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()

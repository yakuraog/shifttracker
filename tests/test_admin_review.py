"""Integration tests for the admin review queue."""
import asyncio
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shifttracker.db.models import Base, Employee, ProcessingLog, ShiftRecord, TelegramGroup


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def login(client):
    """POST /admin/login with default credentials."""
    resp = client.post(
        "/admin/login",
        data={"username": "admin", "password": "changeme"},
        follow_redirects=False,
    )
    assert resp.status_code == 303, f"Login failed: {resp.text}"


def get_session_factory(client):
    """Return the async_session_factory that was patched into the test app."""
    from shifttracker.admin import deps
    return deps.async_session_factory


def insert_sync(session_factory, coro):
    """Run an async DB insert coroutine synchronously."""
    return asyncio.get_event_loop().run_until_complete(coro)


async def _seed_review_entry(session_factory, *, chat_id: int = 100, reason: str = "Unknown employee"):
    """Insert a NEEDS_REVIEW ProcessingLog and return it."""
    async with session_factory() as session:
        entry = ProcessingLog(
            id=uuid.uuid4(),
            update_id=1,
            message_id=42,
            chat_id=chat_id,
            status="NEEDS_REVIEW",
            reason=reason,
            source_link="https://t.me/c/100/42",
            created_at=datetime.now(tz=timezone.utc),
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        return entry.id


async def _seed_employee(session_factory, *, name: str = "Alice") -> uuid.UUID:
    async with session_factory() as session:
        emp = Employee(id=uuid.uuid4(), name=name)
        session.add(emp)
        await session.commit()
        await session.refresh(emp)
        return emp.id


async def _seed_group(session_factory, *, chat_id: int = 100, name: str = "Group A") -> uuid.UUID:
    async with session_factory() as session:
        grp = TelegramGroup(id=uuid.uuid4(), chat_id=chat_id, name=name)
        session.add(grp)
        await session.commit()
        await session.refresh(grp)
        return grp.id


async def _seed_shift_record(session_factory, *, employee_id: uuid.UUID, shift_date: date) -> uuid.UUID:
    async with session_factory() as session:
        sr = ShiftRecord(
            id=uuid.uuid4(),
            employee_id=employee_id,
            shift_date=shift_date,
            status="ACCEPTED",
            source_message_id=42,
            source_link="https://t.me/c/100/42",
            sheet_write_status="PENDING",
        )
        session.add(sr)
        await session.commit()
        await session.refresh(sr)
        return sr.id


async def _get_log(session_factory, log_id: uuid.UUID) -> ProcessingLog:
    async with session_factory() as session:
        from sqlalchemy import select
        row = await session.execute(select(ProcessingLog).where(ProcessingLog.id == log_id))
        return row.scalar_one()


async def _get_shift(session_factory, employee_id: uuid.UUID, shift_date: date):
    async with session_factory() as session:
        from sqlalchemy import select
        row = await session.execute(
            select(ShiftRecord).where(
                ShiftRecord.employee_id == employee_id,
                ShiftRecord.shift_date == shift_date,
            )
        )
        return row.scalar_one_or_none()


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_review_list(test_client):
    """GET /admin/review/ returns 200 and shows NEEDS_REVIEW entries."""
    sf = get_session_factory(test_client)
    log_id = run(_seed_review_entry(sf, reason="Unrecognised face"))

    login(test_client)
    resp = test_client.get("/admin/review/")
    assert resp.status_code == 200
    assert "NEEDS_REVIEW" in resp.text or "Unrecognised face" in resp.text


def test_approve_creates_shift_record(test_client):
    """POST /admin/review/{id}/approve creates ShiftRecord with PENDING sheet_write_status."""
    sf = get_session_factory(test_client)
    log_id = run(_seed_review_entry(sf))
    emp_id = run(_seed_employee(sf))
    today = date.today()

    login(test_client)
    resp = test_client.post(
        f"/admin/review/{log_id}/approve",
        data={"employee_id": str(emp_id), "shift_date": str(today)},
        follow_redirects=False,
    )
    assert resp.status_code == 200

    # ShiftRecord created with ACCEPTED + PENDING
    sr = run(_get_shift(sf, emp_id, today))
    assert sr is not None, "ShiftRecord must be created on approve"
    assert sr.status == "ACCEPTED"
    assert sr.sheet_write_status == "PENDING"

    # ProcessingLog updated to ACCEPTED
    log = run(_get_log(sf, log_id))
    assert log.status == "ACCEPTED"


def test_approve_duplicate_conflict(test_client):
    """POST approve with existing ShiftRecord for same employee+date returns 409."""
    sf = get_session_factory(test_client)
    log_id = run(_seed_review_entry(sf))
    emp_id = run(_seed_employee(sf))
    today = date.today()
    run(_seed_shift_record(sf, employee_id=emp_id, shift_date=today))

    login(test_client)
    resp = test_client.post(
        f"/admin/review/{log_id}/approve",
        data={"employee_id": str(emp_id), "shift_date": str(today)},
        follow_redirects=False,
    )
    assert resp.status_code == 409


def test_reject_stores_comment(test_client):
    """POST /admin/review/{id}/reject stores REJECTED status and operator comment."""
    sf = get_session_factory(test_client)
    log_id = run(_seed_review_entry(sf))

    login(test_client)
    resp = test_client.post(
        f"/admin/review/{log_id}/reject",
        data={"comment": "Not an employee photo"},
        follow_redirects=False,
    )
    assert resp.status_code == 200

    log = run(_get_log(sf, log_id))
    assert log.status == "REJECTED"
    assert "Not an employee photo" in (log.reason or "")


def test_review_filter_by_group(test_client):
    """GET /admin/review/?group_id=X returns only matching entries."""
    sf = get_session_factory(test_client)
    grp1_id = run(_seed_group(sf, chat_id=111, name="Group1"))
    grp2_id = run(_seed_group(sf, chat_id=222, name="Group2"))

    run(_seed_review_entry(sf, chat_id=111, reason="Entry from Group1"))
    run(_seed_review_entry(sf, chat_id=222, reason="Entry from Group2"))

    login(test_client)
    resp = test_client.get(f"/admin/review/?group_id={grp1_id}")
    assert resp.status_code == 200
    assert "Entry from Group1" in resp.text
    assert "Entry from Group2" not in resp.text

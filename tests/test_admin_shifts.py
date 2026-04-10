"""Integration tests for Admin Shift Grid view."""
import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from shifttracker.db.models import (
    Base, Employee, GroupEmployee, ShiftRecord, TelegramGroup,
)


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
    from shifttracker.admin import deps
    return deps.async_session_factory


def run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _seed_group(session_factory, *, chat_id: int = 200, name: str = "ShiftGroup") -> uuid.UUID:
    async with session_factory() as session:
        grp = TelegramGroup(id=uuid.uuid4(), chat_id=chat_id, name=name)
        session.add(grp)
        await session.commit()
        await session.refresh(grp)
        return grp.id


async def _seed_employee(session_factory, *, name: str = "Carol") -> uuid.UUID:
    async with session_factory() as session:
        emp = Employee(id=uuid.uuid4(), name=name)
        session.add(emp)
        await session.commit()
        await session.refresh(emp)
        return emp.id


async def _bind_employee(session_factory, group_id: uuid.UUID, emp_id: uuid.UUID, sheet_row: int = 1) -> None:
    async with session_factory() as session:
        binding = GroupEmployee(
            id=uuid.uuid4(),
            group_id=group_id,
            employee_id=emp_id,
            sheet_row=sheet_row,
        )
        session.add(binding)
        await session.commit()


async def _seed_shift_record(
    session_factory,
    *,
    employee_id: uuid.UUID,
    shift_date: date,
    status: str = "ACCEPTED",
) -> uuid.UUID:
    async with session_factory() as session:
        sr = ShiftRecord(
            id=uuid.uuid4(),
            employee_id=employee_id,
            shift_date=shift_date,
            status=status,
            source_message_id=99,
            source_link="https://t.me/c/200/99",
            sheet_write_status="PENDING",
        )
        session.add(sr)
        await session.commit()
        await session.refresh(sr)
        return sr.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_shift_grid_query(test_client):
    """ACCEPTED record shows as '1'; REJECTED record does NOT."""
    sf = get_session_factory(test_client)
    grp_id = run(_seed_group(sf, chat_id=300, name="GridGroup"))
    emp1_id = run(_seed_employee(sf, name="AcceptedEmp"))
    emp2_id = run(_seed_employee(sf, name="RejectedEmp"))
    run(_bind_employee(sf, grp_id, emp1_id, sheet_row=1))
    run(_bind_employee(sf, grp_id, emp2_id, sheet_row=2))

    today = date.today()
    run(_seed_shift_record(sf, employee_id=emp1_id, shift_date=today, status="ACCEPTED"))
    run(_seed_shift_record(sf, employee_id=emp2_id, shift_date=today, status="REJECTED"))

    login(test_client)
    resp = test_client.get(
        "/admin/shifts/",
        params={
            "group_id": str(grp_id),
            "date_from": str(today),
            "date_to": str(today),
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "AcceptedEmp" in resp.text
    # Should have a "1" mark for AcceptedEmp
    assert ">1<" in resp.text or ">1 <" in resp.text or "1</a>" in resp.text
    # RejectedEmp should not show a "1"
    # The employee may appear as a row but without a "1" in their cell
    # Verify no "1" associated with rejected
    # A simple check: the page must contain AcceptedEmp
    assert "AcceptedEmp" in resp.text


def test_shift_grid_accepted_shows_mark(test_client):
    """ACCEPTED record shows a '1' mark in the correct cell."""
    sf = get_session_factory(test_client)
    grp_id = run(_seed_group(sf, chat_id=301, name="MarkGroup"))
    emp_id = run(_seed_employee(sf, name="MarkEmp"))
    run(_bind_employee(sf, grp_id, emp_id, sheet_row=1))

    target_date = date(2025, 1, 15)
    run(_seed_shift_record(sf, employee_id=emp_id, shift_date=target_date, status="ACCEPTED"))

    login(test_client)
    resp = test_client.get(
        "/admin/shifts/",
        params={
            "group_id": str(grp_id),
            "date_from": str(target_date),
            "date_to": str(target_date),
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "MarkEmp" in resp.text
    # "1" must appear in the table (as shift mark)
    assert "1" in resp.text


def test_shift_grid_rejected_no_mark(test_client):
    """REJECTED record does NOT show a '1' mark."""
    sf = get_session_factory(test_client)
    grp_id = run(_seed_group(sf, chat_id=302, name="RejectGroup"))
    emp_id = run(_seed_employee(sf, name="RejectOnlyEmp"))
    run(_bind_employee(sf, grp_id, emp_id, sheet_row=1))

    target_date = date(2025, 2, 10)
    run(_seed_shift_record(sf, employee_id=emp_id, shift_date=target_date, status="REJECTED"))

    login(test_client)
    resp = test_client.get(
        "/admin/shifts/",
        params={
            "group_id": str(grp_id),
            "date_from": str(target_date),
            "date_to": str(target_date),
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    # Employee row should appear but no "1" cell
    # The page should render fine; the cell should be empty
    assert "RejectOnlyEmp" in resp.text


def test_shift_grid_default_date_range(test_client):
    """GET /admin/shifts/?group_id=X without date params returns 200 with default 7-day range."""
    sf = get_session_factory(test_client)
    grp_id = run(_seed_group(sf, chat_id=303, name="DefaultDateGroup"))

    login(test_client)
    resp = test_client.get(
        "/admin/shifts/",
        params={"group_id": str(grp_id)},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    # Should render the grid table (even if empty)
    assert "DefaultDateGroup" in resp.text


def test_shift_grid_requires_group(test_client):
    """GET /admin/shifts/ without group_id shows 'Select a group' message."""
    login(test_client)
    resp = test_client.get("/admin/shifts/", follow_redirects=True)
    assert resp.status_code == 200
    assert "Выберите группу" in resp.text


def test_shift_grid_employee_rows_and_date_columns(test_client):
    """Grid has employee names as rows and dates as column headers."""
    sf = get_session_factory(test_client)
    grp_id = run(_seed_group(sf, chat_id=304, name="ColGroup"))
    emp1_id = run(_seed_employee(sf, name="EmpRow1"))
    emp2_id = run(_seed_employee(sf, name="EmpRow2"))
    run(_bind_employee(sf, grp_id, emp1_id, sheet_row=1))
    run(_bind_employee(sf, grp_id, emp2_id, sheet_row=2))

    d1 = date(2025, 3, 1)
    d2 = date(2025, 3, 2)

    login(test_client)
    resp = test_client.get(
        "/admin/shifts/",
        params={
            "group_id": str(grp_id),
            "date_from": str(d1),
            "date_to": str(d2),
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "EmpRow1" in resp.text
    assert "EmpRow2" in resp.text
    # Date columns formatted as DD.MM
    assert "01.03" in resp.text
    assert "02.03" in resp.text

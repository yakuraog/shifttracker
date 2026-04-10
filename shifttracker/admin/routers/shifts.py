"""Admin shift attendance grid router."""
import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from shifttracker.admin.deps import get_db
from shifttracker.db.models import Employee, GroupEmployee, ProcessingLog, ShiftRecord, TelegramGroup

router = APIRouter(prefix="/shifts", tags=["shifts"])

MAX_DATE_RANGE_DAYS = 31


@router.get("/", response_class=HTMLResponse)
async def shift_grid(
    request: Request,
    group_id: Optional[uuid.UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    from shifttracker.admin.router import templates

    # Load all groups for dropdown
    groups_result = await db.execute(select(TelegramGroup).order_by(TelegramGroup.name))
    groups = groups_result.scalars().all()

    # Default date range: last 7 days
    today = date.today()
    if date_from is None:
        date_from = today - timedelta(days=6)
    if date_to is None:
        date_to = today

    # Clamp range to MAX_DATE_RANGE_DAYS
    if (date_to - date_from).days >= MAX_DATE_RANGE_DAYS:
        date_to = date_from + timedelta(days=MAX_DATE_RANGE_DAYS - 1)

    # Build date columns list
    date_columns = []
    d = date_from
    while d <= date_to:
        date_columns.append(d)
        d += timedelta(days=1)

    employees = []
    grid = {}

    if group_id is not None:
        # Load group employees ordered by sheet_row then name
        ge_result = await db.execute(
            select(GroupEmployee)
            .where(GroupEmployee.group_id == uuid.UUID(str(group_id)))
            .options(selectinload(GroupEmployee.employee))
            .order_by(GroupEmployee.sheet_row, GroupEmployee.id)
        )
        group_employees = ge_result.scalars().all()
        employees = [ge.employee for ge in group_employees]
        employee_ids = [emp.id for emp in employees]

        if employee_ids:
            # Query ShiftRecords for ACCEPTED/CONFIRMED in date range
            sr_result = await db.execute(
                select(ShiftRecord).where(
                    ShiftRecord.employee_id.in_(employee_ids),
                    ShiftRecord.shift_date >= date_from,
                    ShiftRecord.shift_date <= date_to,
                    ShiftRecord.status.in_(["ACCEPTED", "CONFIRMED"]),
                )
            )
            shift_records = sr_result.scalars().all()
            # Build grid: (employee_id, shift_date) -> ShiftRecord
            for sr in shift_records:
                grid[(sr.employee_id, sr.shift_date)] = sr

    return templates.TemplateResponse(
        request,
        "admin/shifts/grid.html",
        {
            "groups": groups,
            "group_id": group_id,
            "date_from": date_from,
            "date_to": date_to,
            "date_columns": date_columns,
            "employees": employees,
            "grid": grid,
        },
    )


@router.get("/{record_id}/detail", response_class=HTMLResponse)
async def shift_detail(
    request: Request,
    record_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return partial HTML fragment with shift record details for htmx drill-down."""
    from shifttracker.admin.router import templates

    sr_result = await db.execute(
        select(ShiftRecord).where(ShiftRecord.id == uuid.UUID(str(record_id)))
    )
    record = sr_result.scalar_one_or_none()
    if record is None:
        return HTMLResponse("<p>Record not found.</p>", status_code=404)

    # Load related processing logs
    logs_result = await db.execute(
        select(ProcessingLog)
        .where(
            ProcessingLog.employee_id == record.employee_id,
            ProcessingLog.shift_date == record.shift_date,
        )
        .order_by(ProcessingLog.created_at.desc())
    )
    logs = logs_result.scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/shifts/_detail.html",
        {
            "record": record,
            "logs": logs,
        },
    )

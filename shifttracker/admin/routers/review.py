"""Admin review queue: list NEEDS_REVIEW items, approve, reject."""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shifttracker.admin.deps import get_db
from shifttracker.db.models import Employee, ProcessingLog, ShiftRecord, TelegramGroup

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/")
async def review_list(
    request: Request,
    group_id: Optional[uuid.UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    from shifttracker.admin.router import templates

    # Build base query for NEEDS_REVIEW entries
    stmt = select(ProcessingLog).where(ProcessingLog.status == "NEEDS_REVIEW")

    # Filter by group: resolve chat_id from TelegramGroup
    if group_id is not None:
        grp_result = await db.execute(
            select(TelegramGroup.chat_id).where(TelegramGroup.id == group_id)
        )
        chat_id_val = grp_result.scalar_one_or_none()
        if chat_id_val is not None:
            stmt = stmt.where(ProcessingLog.chat_id == chat_id_val)

    if date_from is not None:
        stmt = stmt.where(ProcessingLog.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(ProcessingLog.created_at <= date_to)

    stmt = stmt.order_by(ProcessingLog.created_at.desc())
    result = await db.execute(stmt)
    raw_items = result.scalars().all()

    # Resolve employee names and group names for display
    items = []
    for log in raw_items:
        emp_name = None
        if log.employee_id is not None:
            emp_result = await db.execute(
                select(Employee.name).where(Employee.id == log.employee_id)
            )
            emp_name = emp_result.scalar_one_or_none()

        grp_name = None
        grp_result = await db.execute(
            select(TelegramGroup.name).where(TelegramGroup.chat_id == log.chat_id)
        )
        grp_name = grp_result.scalar_one_or_none()

        items.append({
            "log": log,
            "employee_name": emp_name or "Unknown",
            "group_name": grp_name or str(log.chat_id),
        })

    # Load all groups and employees for approve form dropdowns
    groups_result = await db.execute(select(TelegramGroup).order_by(TelegramGroup.name))
    groups = groups_result.scalars().all()

    employees_result = await db.execute(select(Employee).order_by(Employee.name))
    employees = employees_result.scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/review/list.html",
        {
            "items": items,
            "groups": groups,
            "employees": employees,
            "current_group_id": str(group_id) if group_id else "",
            "date_from": str(date_from) if date_from else "",
            "date_to": str(date_to) if date_to else "",
        },
    )


@router.post("/{log_id}/approve")
async def approve_item(
    log_id: uuid.UUID,
    employee_id: uuid.UUID = Form(...),
    shift_date: date = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Approve a NEEDS_REVIEW entry: create ShiftRecord with PENDING sheet_write_status."""
    # Load processing log
    result = await db.execute(select(ProcessingLog).where(ProcessingLog.id == log_id))
    log = result.scalar_one_or_none()
    if log is None or log.status != "NEEDS_REVIEW":
        raise HTTPException(status_code=404, detail="Review item not found")

    # Check for existing ShiftRecord with same employee+date (UniqueConstraint)
    existing = await db.execute(
        select(ShiftRecord).where(
            ShiftRecord.employee_id == employee_id,
            ShiftRecord.shift_date == shift_date,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Conflict: ShiftRecord already exists for this employee and date")

    # Create ShiftRecord with PENDING sheet_write_status
    shift_record = ShiftRecord(
        id=uuid.uuid4(),
        employee_id=employee_id,
        shift_date=shift_date,
        status="ACCEPTED",
        source_message_id=log.message_id,
        source_link=log.source_link or "",
        sheet_write_status="PENDING",
    )
    db.add(shift_record)

    # Update ProcessingLog
    log.status = "ACCEPTED"
    log.employee_id = employee_id
    log.shift_date = shift_date

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Conflict: duplicate ShiftRecord detected on commit")

    return Response(status_code=200)


@router.post("/{log_id}/reject")
async def reject_item(
    log_id: uuid.UUID,
    comment: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """Reject a NEEDS_REVIEW entry and store operator comment."""
    result = await db.execute(select(ProcessingLog).where(ProcessingLog.id == log_id))
    log = result.scalar_one_or_none()
    if log is None or log.status != "NEEDS_REVIEW":
        raise HTTPException(status_code=404, detail="Review item not found")

    log.status = "REJECTED"
    log.reason = comment
    await db.commit()

    return Response(status_code=200)

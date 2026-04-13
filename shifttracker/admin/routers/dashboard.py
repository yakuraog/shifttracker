import json
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from shifttracker.admin.deps import get_db
from shifttracker.db.models import ProcessingLog, ShiftRecord, Employee, TelegramGroup

router = APIRouter()


@router.get("/")
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from shifttracker.admin.router import templates

    today = date.today()
    today_start = datetime.combine(today, time.min)

    # Count accepted today
    accepted_result = await db.execute(
        select(func.count(ProcessingLog.id)).where(
            ProcessingLog.status == "ACCEPTED",
            ProcessingLog.created_at >= today_start,
        )
    )
    accepted_today = accepted_result.scalar() or 0

    # Count pending review
    pending_result = await db.execute(
        select(func.count(ProcessingLog.id)).where(
            ProcessingLog.status == "NEEDS_REVIEW",
        )
    )
    pending_review = pending_result.scalar() or 0

    # Count errors today
    errors_result = await db.execute(
        select(func.count(ProcessingLog.id)).where(
            ProcessingLog.status == "ERROR",
            ProcessingLog.created_at >= today_start,
        )
    )
    errors_today = errors_result.scalar() or 0

    # Total employees
    emp_result = await db.execute(select(func.count(Employee.id)))
    total_employees = emp_result.scalar() or 0

    # Total groups
    grp_result = await db.execute(select(func.count(TelegramGroup.id)))
    total_groups = grp_result.scalar() or 0

    # Total shift records
    sr_result = await db.execute(select(func.count(ShiftRecord.id)))
    total_shifts = sr_result.scalar() or 0

    # Chart data: last 7 days
    chart_labels = []
    chart_accepted = []
    chart_review = []
    chart_rejected = []

    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        d_start = datetime.combine(d, time.min)
        d_end = datetime.combine(d + timedelta(days=1), time.min)
        chart_labels.append(d.strftime("%d.%m"))

        for status, target_list in [
            ("ACCEPTED", chart_accepted),
            ("NEEDS_REVIEW", chart_review),
            ("REJECTED", chart_rejected),
        ]:
            r = await db.execute(
                select(func.count(ProcessingLog.id)).where(
                    ProcessingLog.status == status,
                    ProcessingLog.created_at >= d_start,
                    ProcessingLog.created_at < d_end,
                )
            )
            target_list.append(r.scalar() or 0)

    stats = {
        "accepted_today": accepted_today,
        "pending_review": pending_review,
        "errors_today": errors_today,
        "total_employees": total_employees,
        "total_groups": total_groups,
        "total_shifts": total_shifts,
    }

    chart_data = {
        "labels": chart_labels,
        "accepted": chart_accepted,
        "review": chart_review,
        "rejected": chart_rejected,
    }

    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {"stats": stats, "chart_data_json": json.dumps(chart_data)},
    )

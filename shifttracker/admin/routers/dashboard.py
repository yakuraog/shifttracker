from datetime import date, datetime, time

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shifttracker.admin.deps import get_db
from shifttracker.db.models import ProcessingLog

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

    # Count pending review today
    pending_result = await db.execute(
        select(func.count(ProcessingLog.id)).where(
            ProcessingLog.status == "NEEDS_REVIEW",
            ProcessingLog.created_at >= today_start,
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

    stats = {
        "accepted_today": accepted_today,
        "pending_review": pending_review,
        "errors_today": errors_today,
    }

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {"request": request, "stats": stats},
    )

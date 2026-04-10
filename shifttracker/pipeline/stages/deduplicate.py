from datetime import date
from uuid import UUID

from sqlalchemy import insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shifttracker.db.models import ProcessedUpdate, ShiftRecord


async def check_duplicate(update_id: int, session: AsyncSession) -> bool:
    """Returns True if update_id was already processed (duplicate).

    Uses INSERT ... ON CONFLICT / IntegrityError pattern for at-most-once semantics.
    - PostgreSQL (prod): INSERT raises IntegrityError on duplicate PK
    - SQLite (tests): INSERT raises IntegrityError on duplicate PK

    On successful insert → not a duplicate (returns False).
    On IntegrityError → duplicate (returns True).
    """
    try:
        stmt = insert(ProcessedUpdate).values(update_id=update_id)
        await session.execute(stmt)
        await session.flush()
        return False  # Insert succeeded — not a duplicate
    except IntegrityError:
        await session.rollback()
        return True  # Constraint violation — already processed


async def check_business_duplicate(
    employee_id: UUID,
    shift_date: date,
    session: AsyncSession,
) -> bool:
    """Returns True if a shift_record already exists for this employee+date.

    Used after update_id dedup to prevent duplicate shift marks for the
    same worker on the same calendar day.
    """
    result = await session.execute(
        select(ShiftRecord.id).where(
            ShiftRecord.employee_id == employee_id,
            ShiftRecord.shift_date == shift_date,
        )
    )
    return result.scalar_one_or_none() is not None

import asyncio

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from shifttracker.config import Settings
from shifttracker.db.engine import async_session_factory
from shifttracker.db.models import ProcessingLog, ShiftRecord
from shifttracker.pipeline.models import ProcessingContext
from shifttracker.pipeline.queue import message_queue
from shifttracker.pipeline.stages.deduplicate import check_business_duplicate, check_duplicate
from shifttracker.pipeline.stages.identify import identify_employee
from shifttracker.pipeline.stages.shift_date import resolve_shift_date

_bot_instance = None


def set_bot(bot):
    """Set bot instance for sending operator notifications."""
    global _bot_instance
    _bot_instance = bot


async def _notify_operator(reason: str, ctx: ProcessingContext):
    """Send notification to operator when message needs review."""
    settings = Settings()
    if not settings.operator_chat_id or not _bot_instance:
        return
    try:
        text = (
            f"Требуется проверка\n\n"
            f"Причина: {reason}\n"
            f"Группа chat_id: {ctx.chat_id}\n"
            f"Подпись: {ctx.caption or 'нет'}\n"
        )
        if ctx.source_link:
            text += f"Источник: {ctx.source_link}"
        await _bot_instance.send_message(settings.operator_chat_id, text)
    except Exception as e:
        logger.warning(f"Failed to notify operator: {e}")


async def process_message(ctx: ProcessingContext, session: AsyncSession) -> None:
    """Process a single message through the full pipeline.

    Pipeline order (per locked decision from 01-CONTEXT.md):
    1. Dedup by update_id (INSERT ON CONFLICT DO NOTHING)
    2. Identify employee(s) via confidence ladder
    3. Resolve shift date with timezone + window
    4. Business dedup (employee_id + shift_date)
    5. Write ShiftRecord + ProcessingLog
    """

    # Step 1: Update dedup
    is_dup = await check_duplicate(ctx.update_id, session)
    if is_dup:
        logger.debug(f"Duplicate update_id={ctx.update_id}, skipping")
        return

    # Step 2: Identify employee(s)
    identifications = await identify_employee(ctx, session)

    if not identifications:
        # No employee identified -> NEEDS_REVIEW
        log_entry = ProcessingLog(
            update_id=ctx.update_id,
            message_id=ctx.message_id,
            chat_id=ctx.chat_id,
            status="NEEDS_REVIEW",
            reason="no_employee_identified",
            source_link=ctx.source_link,
        )
        session.add(log_entry)
        await session.commit()
        await _notify_operator("Сотрудник не определён", ctx)
        return

    # Step 3+4+5: For each identified employee
    for ident in identifications:
        # Step 3: Resolve shift date
        shift_date, date_reason = resolve_shift_date(
            ctx.message_datetime,
            ctx.shift_start_hour,
            ctx.shift_end_hour,
            ctx.group_timezone,
        )

        if shift_date is None:
            # Outside time window -> NEEDS_REVIEW
            log_entry = ProcessingLog(
                update_id=ctx.update_id,
                message_id=ctx.message_id,
                chat_id=ctx.chat_id,
                employee_id=ident.employee_id,
                status="NEEDS_REVIEW",
                reason=date_reason,  # "outside_time_window"
                source_link=ctx.source_link,
            )
            session.add(log_entry)
            await session.commit()
            await _notify_operator(f"Вне окна смены ({ident.employee_name})", ctx)
            continue

        # Step 4: Business dedup (employee + date)
        is_business_dup = await check_business_duplicate(ident.employee_id, shift_date, session)
        if is_business_dup:
            log_entry = ProcessingLog(
                update_id=ctx.update_id,
                message_id=ctx.message_id,
                chat_id=ctx.chat_id,
                employee_id=ident.employee_id,
                shift_date=shift_date,
                status="DUPLICATE_SAME_SHIFT",
                reason=f"shift_record already exists for {ident.employee_name} on {shift_date}",
                source_link=ctx.source_link,
            )
            session.add(log_entry)
            await session.commit()
            continue

        # Step 5: Write ShiftRecord + ProcessingLog
        shift_record = ShiftRecord(
            employee_id=ident.employee_id,
            shift_date=shift_date,
            status="CONFIRMED",
            source_message_id=ctx.message_id,
            source_link=ctx.source_link or "",
            sheet_write_status="PENDING",  # For Phase 2 consumption
        )
        session.add(shift_record)

        log_entry = ProcessingLog(
            update_id=ctx.update_id,
            message_id=ctx.message_id,
            chat_id=ctx.chat_id,
            employee_id=ident.employee_id,
            shift_date=shift_date,
            status="ACCEPTED",
            source_link=ctx.source_link,
        )
        session.add(log_entry)
        await session.commit()


_worker_tasks: list[asyncio.Task] = []


async def _worker(worker_id: int) -> None:
    """Single worker coroutine that pulls from queue and processes."""
    logger.info(f"Worker {worker_id} started")
    while True:
        try:
            ctx = await message_queue.get()
            logger.debug(f"Worker {worker_id} processing update_id={ctx.update_id}")
            async with async_session_factory() as session:
                try:
                    await process_message(ctx, session)
                except Exception as e:
                    await session.rollback()
                    # Log error to a fresh session to avoid using the rolled-back session
                    error_log = ProcessingLog(
                        update_id=ctx.update_id,
                        message_id=ctx.message_id,
                        chat_id=ctx.chat_id,
                        status="ERROR",
                        reason=str(e)[:500],
                        source_link=ctx.source_link,
                    )
                    async with async_session_factory() as err_session:
                        err_session.add(error_log)
                        await err_session.commit()
            message_queue.task_done()
        except asyncio.CancelledError:
            logger.info(f"Worker {worker_id} stopping")
            break


async def start_workers(count: int = 8) -> None:
    """Start `count` worker coroutines as asyncio tasks."""
    for i in range(count):
        task = asyncio.create_task(_worker(i))
        _worker_tasks.append(task)


async def stop_workers() -> None:
    """Cancel all running worker tasks and wait for them to finish."""
    for task in _worker_tasks:
        task.cancel()
    await asyncio.gather(*_worker_tasks, return_exceptions=True)
    _worker_tasks.clear()

from aiogram import Router, F
from aiogram.types import Message, Update
from loguru import logger
from sqlalchemy import select, update

from shifttracker.db.engine import async_session_factory
from shifttracker.db.models import TelegramGroup, ProcessingLog
from shifttracker.pipeline.models import ProcessingContext
from shifttracker.pipeline.queue import enqueue_message
from shifttracker.pipeline.stages.validate import validate_message

router = Router(name="shift_photo_router")


def build_source_link(chat_id: int, message_id: int) -> str:
    """Build a t.me/c/... link from a supergroup chat_id and message_id.

    Supergroup chat_ids look like -1001234567890.
    Strip the leading '-' and then the '100' prefix to get the pure channel ID.
    """
    chat_id_str = str(chat_id).lstrip("-")
    if chat_id_str.startswith("100"):
        chat_id_str = chat_id_str[3:]
    return f"https://t.me/c/{chat_id_str}/{message_id}"


@router.message(F.photo)
async def handle_photo(message: Message, event_update: Update) -> None:
    """Silent handler — never sends responses to the group chat.

    Receives the parent Update via aiogram 3 dependency injection (event_update parameter)
    to extract the real update_id for deduplication (TGRAM-03).
    """
    logger.info(
        f"Получено фото: chat_id={message.chat.id}, "
        f"user_id={message.from_user.id if message.from_user else '?'}, "
        f"caption='{message.caption or ''}'"
    )

    is_valid, reason = validate_message(message)
    if not is_valid:
        # Log skip with real update_id from the Update object
        async with async_session_factory() as session:
            log_entry = ProcessingLog(
                update_id=event_update.update_id,
                message_id=message.message_id,
                chat_id=message.chat.id,
                status="SKIPPED",
                reason=reason,
            )
            session.add(log_entry)
            await session.commit()
        return

    source_link = build_source_link(message.chat.id, message.message_id)

    # Look up the registered group for timezone and shift window
    async with async_session_factory() as session:
        result = await session.execute(
            select(TelegramGroup).where(TelegramGroup.chat_id == message.chat.id)
        )
        group = result.scalar_one_or_none()

    ctx = ProcessingContext(
        update_id=event_update.update_id,
        message_id=message.message_id,
        chat_id=message.chat.id,
        sender_user_id=message.from_user.id if message.from_user else None,
        caption=message.caption,
        message_datetime=message.date,
        group_id=group.id if group else None,
        group_timezone=group.timezone if group else "Europe/Moscow",
        shift_start_hour=group.shift_start_hour if group else 6,
        shift_end_hour=group.shift_end_hour if group else 22,
        source_link=source_link,
    )
    await enqueue_message(ctx)


@router.message(F.migrate_to_chat_id)
async def handle_migration(message: Message) -> None:
    """Handle group -> supergroup migration by updating chat_id in telegram_groups."""
    old_chat_id = message.chat.id
    new_chat_id = message.migrate_to_chat_id
    async with async_session_factory() as session:
        await session.execute(
            update(TelegramGroup)
            .where(TelegramGroup.chat_id == old_chat_id)
            .values(chat_id=new_chat_id)
        )
        await session.commit()

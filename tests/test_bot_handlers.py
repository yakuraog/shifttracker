"""Tests for bot handlers, validation, and queue.

TDD RED phase — tests are written before implementation.
All tests must fail initially since no source files exist yet.
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shifttracker.pipeline.stages.validate import validate_message


# ---------------------------------------------------------------------------
# validate_message tests
# ---------------------------------------------------------------------------

def make_message(
    *,
    photo=None,
    forward_from=None,
    forward_from_chat=None,
    document=None,
    caption=None,
) -> MagicMock:
    """Build a minimal mock Message object."""
    msg = MagicMock()
    msg.photo = photo  # list of PhotoSize or None
    msg.forward_from = forward_from
    msg.forward_from_chat = forward_from_chat
    msg.document = document
    msg.caption = caption
    return msg


class TestValidateMessage:
    def test_valid_photo_message(self):
        """Message with photo list returns (True, None)."""
        msg = make_message(photo=[MagicMock()])  # non-empty photo list
        valid, reason = validate_message(msg)
        assert valid is True
        assert reason is None

    def test_text_only_message_returns_no_photo(self):
        """Text-only message (no photo, no document) returns (False, 'no_photo')."""
        msg = make_message(photo=None, document=None)
        valid, reason = validate_message(msg)
        assert valid is False
        assert reason == "no_photo"

    def test_forwarded_message_with_forward_from(self):
        """Message with forward_from returns (False, 'forwarded_message')."""
        msg = make_message(photo=[MagicMock()], forward_from=MagicMock())
        valid, reason = validate_message(msg)
        assert valid is False
        assert reason == "forwarded_message"

    def test_forwarded_message_with_forward_from_chat(self):
        """Message with forward_from_chat returns (False, 'forwarded_message')."""
        msg = make_message(photo=[MagicMock()], forward_from_chat=MagicMock())
        valid, reason = validate_message(msg)
        assert valid is False
        assert reason == "forwarded_message"

    def test_document_without_photo(self):
        """Message with document but no photo returns (False, 'document_not_photo')."""
        msg = make_message(photo=None, document=MagicMock())
        valid, reason = validate_message(msg)
        assert valid is False
        assert reason == "document_not_photo"


# ---------------------------------------------------------------------------
# build_source_link tests
# ---------------------------------------------------------------------------

class TestBuildSourceLink:
    def test_source_link_format(self):
        """build_source_link produces correct t.me/c/... URL."""
        from shifttracker.bot.router import build_source_link

        # chat_id for supergroups is -100XXXXXXXXXX; strip -100 prefix
        chat_id = -1001234567890
        message_id = 42
        link = build_source_link(chat_id, message_id)
        assert link == "https://t.me/c/1234567890/42"

    def test_source_link_plain_negative(self):
        """Negative chat_id without 100 prefix is stripped of just the minus."""
        from shifttracker.bot.router import build_source_link

        chat_id = -987654321
        message_id = 10
        link = build_source_link(chat_id, message_id)
        # strip '-' then '100' prefix (100 not present, so only minus removed)
        assert link == "https://t.me/c/987654321/10"


# ---------------------------------------------------------------------------
# handle_photo tests — update_id extracted from Update object
# ---------------------------------------------------------------------------

class TestHandlePhoto:
    @pytest.mark.asyncio
    async def test_photo_handler_uses_update_id_from_update_object(self):
        """handle_photo creates ProcessingContext whose update_id comes from Update, not hardcoded."""
        from shifttracker.bot.router import handle_photo

        # Build mock Update with a specific update_id
        mock_update = MagicMock()
        mock_update.update_id = 99999

        # Build mock Message
        mock_message = MagicMock()
        mock_message.photo = [MagicMock()]
        mock_message.forward_from = None
        mock_message.forward_from_chat = None
        mock_message.document = None
        mock_message.message_id = 555
        mock_message.caption = "Test caption"
        mock_message.date = datetime(2026, 4, 10, 8, 0, tzinfo=timezone.utc)
        mock_message.chat = MagicMock()
        mock_message.chat.id = -1001234567890
        mock_message.from_user = MagicMock()
        mock_message.from_user.id = 111222333

        # Capture what gets enqueued
        enqueued_contexts = []

        async def fake_enqueue(ctx):
            enqueued_contexts.append(ctx)

        with patch("shifttracker.bot.router.enqueue_message", fake_enqueue), \
             patch("shifttracker.bot.router.async_session_factory") as mock_sf:
            # Mock session context manager
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sf.return_value = mock_session
            # Mock DB query (group lookup) — return None (no group configured)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            await handle_photo(mock_message, mock_update)

        assert len(enqueued_contexts) == 1
        ctx = enqueued_contexts[0]
        # The critical assertion: update_id must come from the Update object
        assert ctx.update_id == 99999, (
            f"Expected update_id=99999 from Update object, got {ctx.update_id}"
        )

    @pytest.mark.asyncio
    async def test_photo_handler_enqueues_with_correct_fields(self):
        """handle_photo enqueues ProcessingContext with correct chat_id, message_id, etc."""
        from shifttracker.bot.router import handle_photo

        mock_update = MagicMock()
        mock_update.update_id = 12345

        mock_message = MagicMock()
        mock_message.photo = [MagicMock()]
        mock_message.forward_from = None
        mock_message.forward_from_chat = None
        mock_message.document = None
        mock_message.message_id = 777
        mock_message.caption = "John Doe"
        mock_message.date = datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc)
        mock_message.chat = MagicMock()
        mock_message.chat.id = -1009876543210
        mock_message.from_user = MagicMock()
        mock_message.from_user.id = 444555666

        enqueued_contexts = []

        async def fake_enqueue(ctx):
            enqueued_contexts.append(ctx)

        with patch("shifttracker.bot.router.enqueue_message", fake_enqueue), \
             patch("shifttracker.bot.router.async_session_factory") as mock_sf:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_sf.return_value = mock_session
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute = AsyncMock(return_value=mock_result)

            await handle_photo(mock_message, mock_update)

        assert len(enqueued_contexts) == 1
        ctx = enqueued_contexts[0]
        assert ctx.update_id == 12345
        assert ctx.message_id == 777
        assert ctx.chat_id == -1009876543210
        assert ctx.caption == "John Doe"


# ---------------------------------------------------------------------------
# handle_migration tests
# ---------------------------------------------------------------------------

class TestHandleMigration:
    @pytest.mark.asyncio
    async def test_migration_handler_updates_chat_id(self, async_session):
        """Migration handler updates TelegramGroup.chat_id in DB."""
        from shifttracker.bot.router import handle_migration
        from shifttracker.db.models import TelegramGroup

        # Insert a group with old chat_id
        old_chat_id = -100111111111
        new_chat_id = -100222222222
        group = TelegramGroup(
            chat_id=old_chat_id,
            name="Test Group",
        )
        async_session.add(group)
        await async_session.commit()

        # Build mock message for migration
        mock_message = MagicMock()
        mock_message.chat = MagicMock()
        mock_message.chat.id = old_chat_id
        mock_message.migrate_to_chat_id = new_chat_id

        with patch("shifttracker.bot.router.async_session_factory") as mock_sf:
            mock_sf.return_value.__aenter__ = AsyncMock(return_value=async_session)
            mock_sf.return_value.__aexit__ = AsyncMock(return_value=False)
            await handle_migration(mock_message)

        # Verify chat_id was updated
        from sqlalchemy import select
        result = await async_session.execute(
            select(TelegramGroup).where(TelegramGroup.chat_id == new_chat_id)
        )
        updated_group = result.scalar_one_or_none()
        assert updated_group is not None, "Group with new_chat_id should exist after migration"
        assert updated_group.chat_id == new_chat_id

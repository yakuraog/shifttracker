"""SheetsWriter background task.

Consumes PENDING ShiftRecord rows, resolves cell addresses, writes "1" and
source link to Google Sheets via gspread batch_update.  Handles retries with
incremented retry_count (up to sheets_max_retries), duplicate detection, and
groups updates into one batch_update call per spreadsheet.
"""
import asyncio
import functools
import os
from datetime import datetime, timezone
from typing import Any

import gspread.exceptions
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shifttracker.config import Settings
from shifttracker.db.models import (
    GroupEmployee,
    ProcessingLog,
    ShiftRecord,
    TelegramGroup,
)
from shifttracker.sheets.cell_resolve import resolve_cell
from shifttracker.sheets.client import build_client
from shifttracker.sheets.header_cache import get_cached, set_cached


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _run_sync(fn, *args, **kwargs):
    """Run a blocking call in the default executor (thread pool)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))


# ---------------------------------------------------------------------------
# SheetsWriter
# ---------------------------------------------------------------------------

class SheetsWriter:
    """Background task that periodically flushes PENDING ShiftRecords to Google Sheets."""

    def __init__(self, settings: Settings, session_factory) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._task: asyncio.Task | None = None
        self._gc = None  # gspread.Client — set in start()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background flush loop.

        No-ops (with a warning) when credentials are not configured.
        Supports both file path and raw JSON string for credentials.
        """
        cred_file = self._settings.google_sheets_credentials_file
        cred_json = self._settings.google_sheets_credentials_json

        if not cred_file and not cred_json:
            logger.warning(
                "Google Sheets credentials not configured — SheetsWriter disabled"
            )
            return

        if cred_json:
            self._gc = await _run_sync(build_client, credentials_json=cred_json)
        elif cred_file:
            if not os.path.exists(cred_file):
                raise RuntimeError(
                    f"GOOGLE_SHEETS_CREDENTIALS_FILE not found: {cred_file}"
                )
            self._gc = await _run_sync(build_client, credentials_file=cred_file)
        self._task = asyncio.create_task(self._flush_loop())
        logger.info("SheetsWriter background task started")

    async def stop(self) -> None:
        """Cancel and await the background flush loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Flush loop
    # ------------------------------------------------------------------

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(self._settings.sheets_flush_interval)
            try:
                await self._flush()
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(f"SheetsWriter flush error: {exc}")

    # ------------------------------------------------------------------
    # Core flush logic
    # ------------------------------------------------------------------

    async def _flush(self) -> None:
        """Single flush pass: process all PENDING ShiftRecords."""
        # Support both sync sessionmaker (production) and async factory (tests)
        factory_result = self._session_factory()
        _owns_session = False
        if hasattr(factory_result, '__aenter__'):
            # sync sessionmaker — we own this session and must close it
            session: AsyncSession = factory_result
            _owns_session = True
        else:
            # async factory (tests) — caller owns the session
            session: AsyncSession = await factory_result

        try:
            # ------------------------------------------------------------------
            # 1. Load all PENDING records
            # ------------------------------------------------------------------
            result = await session.execute(
                select(ShiftRecord).where(ShiftRecord.sheet_write_status == "PENDING")
            )
            pending: list[ShiftRecord] = list(result.scalars().all())

            if not pending:
                return

            # ------------------------------------------------------------------
            # 2. Resolve context for each record: sheet_id, sheet_name, sheet_row
            # ------------------------------------------------------------------
            grouped: dict[tuple[str, str], list[tuple[ShiftRecord, int]]] = {}

            for record in pending:
                context = await self._resolve_record_context(session, record)
                if context is None:
                    continue

                sheet_id, sheet_name, sheet_row = context

                if not sheet_row or sheet_row < 1:
                    await self._set_record_error(
                        session, record, "employee_row_not_configured"
                    )
                    continue

                key = (sheet_id, sheet_name)
                grouped.setdefault(key, []).append((record, sheet_row))

            # ------------------------------------------------------------------
            # 3. Process each (sheet_id, sheet_name) group with a single batch_update
            # ------------------------------------------------------------------
            for (sheet_id, sheet_name), items in grouped.items():
                await self._process_sheet_group(
                    session, sheet_id, sheet_name, items
                )
        finally:
            if _owns_session:
                await session.close()

    # ------------------------------------------------------------------
    # Context resolution helpers
    # ------------------------------------------------------------------

    async def _resolve_record_context(
        self, session: AsyncSession, record: ShiftRecord
    ) -> tuple[str, str, int | None] | None:
        """Return (sheet_id, sheet_name, sheet_row) or None if no sheet configured.

        Uses the ProcessingLog to find which TelegramGroup the message came from,
        then looks up GroupEmployee.sheet_row.
        """
        # Find chat_id from ProcessingLog for this message
        log_result = await session.execute(
            select(ProcessingLog).where(
                ProcessingLog.message_id == record.source_message_id,
                ProcessingLog.employee_id == record.employee_id,
            )
        )
        plog = log_result.scalars().first()

        if plog is None:
            logger.warning(
                f"No ProcessingLog for record {record.id} "
                f"(source_message_id={record.source_message_id}) — skipping"
            )
            return None

        chat_id = plog.chat_id

        # Look up the TelegramGroup by chat_id
        group_result = await session.execute(
            select(TelegramGroup).where(TelegramGroup.chat_id == chat_id)
        )
        group = group_result.scalar_one_or_none()

        if group is None:
            logger.warning(f"TelegramGroup not found for chat_id={chat_id} — skipping")
            return None

        if not group.sheet_id:
            logger.debug(
                f"TelegramGroup {group.id} has no sheet_id configured — skipping record {record.id}"
            )
            return None  # Caller treats None as "skip silently"

        sheet_name = group.sheet_name or "Sheet1"

        # Resolve GroupEmployee.sheet_row
        ge_result = await session.execute(
            select(GroupEmployee).where(
                GroupEmployee.group_id == group.id,
                GroupEmployee.employee_id == record.employee_id,
            )
        )
        ge = ge_result.scalar_one_or_none()

        sheet_row = ge.sheet_row if ge else None
        return group.sheet_id, sheet_name, sheet_row

    # ------------------------------------------------------------------
    # Per-sheet batch processing
    # ------------------------------------------------------------------

    async def _process_sheet_group(
        self,
        session: AsyncSession,
        sheet_id: str,
        sheet_name: str,
        items: list[tuple[ShiftRecord, int]],
    ) -> None:
        """Write all pending records for one spreadsheet in a single batch_update."""
        # ------------------------------------------------------------------
        # Get or refresh header row
        # ------------------------------------------------------------------
        header_row = get_cached(sheet_id, sheet_name)
        if header_row is None:
            try:
                spreadsheet = await _run_sync(self._gc.open_by_key, sheet_id)
                worksheet = await _run_sync(spreadsheet.worksheet, sheet_name)
                header_row = await _run_sync(worksheet.row_values, 1)
                set_cached(sheet_id, sheet_name, header_row)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error(
                    f"Failed to fetch header row for sheet {sheet_id}/{sheet_name}: {exc}"
                )
                return

        spreadsheet = await _run_sync(self._gc.open_by_key, sheet_id)
        worksheet = await _run_sync(spreadsheet.worksheet, sheet_name)

        # ------------------------------------------------------------------
        # Resolve cell addresses for each record
        # ------------------------------------------------------------------
        resolved: list[tuple[ShiftRecord, str, str]] = []  # (record, value_a1, link_a1)

        for record, sheet_row in items:
            cell_pair = resolve_cell(header_row, sheet_row, record.shift_date)
            if cell_pair is None:
                await self._set_record_error(session, record, "date_column_not_found")
                continue
            value_a1, link_a1 = cell_pair
            resolved.append((record, value_a1, link_a1))

        if not resolved:
            return

        # ------------------------------------------------------------------
        # Duplicate check — batch_get for all value cells at once
        # ------------------------------------------------------------------
        value_ranges = [value_a1 for _, value_a1, _ in resolved]
        try:
            existing_values: list[Any] = await _run_sync(
                worksheet.batch_get, value_ranges
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error(
                f"batch_get failed for sheet {sheet_id}/{sheet_name}: {exc}"
            )
            return

        # Filter out duplicates
        updates: list[dict] = []
        to_write: list[ShiftRecord] = []

        for idx, (record, value_a1, link_a1) in enumerate(resolved):
            # existing_values[idx] is a ValueRange (list of lists); may be empty
            range_data = existing_values[idx] if idx < len(existing_values) else []
            current_value = ""
            if range_data and range_data[0]:
                current_value = str(range_data[0][0])

            if current_value == "1":
                # Already written — log as duplicate and skip
                dup_log = ProcessingLog(
                    update_id=0,
                    message_id=record.source_message_id,
                    chat_id=0,
                    employee_id=record.employee_id,
                    shift_date=record.shift_date,
                    status="DUPLICATE_SHEET_SKIP",
                    reason=f"Cell {value_a1} already contains '1'",
                    source_link=record.source_link,
                )
                session.add(dup_log)
                continue

            updates.append({"range": value_a1, "values": [["1"]]})
            updates.append({"range": link_a1, "values": [[record.source_link]]})
            to_write.append(record)

        if not updates:
            await session.commit()
            return

        # ------------------------------------------------------------------
        # Single batch_update call for this spreadsheet
        # ------------------------------------------------------------------
        try:
            await _run_sync(worksheet.batch_update, updates)
        except gspread.exceptions.APIError as exc:
            logger.warning(
                f"APIError writing to sheet {sheet_id}/{sheet_name}: {exc}. "
                f"Incrementing retry_count for {len(to_write)} records."
            )
            for record in to_write:
                record.retry_count += 1
                if record.retry_count >= self._settings.sheets_max_retries:
                    record.sheet_write_status = "ERROR"
                    logger.error(
                        f"Record {record.id} exceeded max retries "
                        f"({self._settings.sheets_max_retries}) — marking ERROR"
                    )
                # else: stays PENDING
            await session.commit()
            return

        # ------------------------------------------------------------------
        # Mark records as WRITTEN
        # ------------------------------------------------------------------
        now = datetime.now(timezone.utc)
        for record in to_write:
            record.sheet_write_status = "WRITTEN"
            record.written_at = now

        await session.commit()
        logger.info(
            f"Wrote {len(to_write)} records to sheet {sheet_id}/{sheet_name}"
        )

    # ------------------------------------------------------------------
    # Error helper
    # ------------------------------------------------------------------

    async def _set_record_error(
        self, session: AsyncSession, record: ShiftRecord, reason: str
    ) -> None:
        """Set a record's sheet_write_status to ERROR and log a ProcessingLog entry."""
        record.sheet_write_status = "ERROR"
        error_log = ProcessingLog(
            update_id=0,
            message_id=record.source_message_id,
            chat_id=0,
            employee_id=record.employee_id,
            shift_date=record.shift_date,
            status="ERROR",
            reason=reason,
            source_link=record.source_link,
        )
        session.add(error_log)
        await session.commit()

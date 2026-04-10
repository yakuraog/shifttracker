# Phase 2: Google Sheets Integration - Context

**Gathered:** 2026-04-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Write confirmed shift attendance marks as "1" into Google Sheets cells. Consume SHEET_WRITE_PENDING records from Phase 1's shift_records table. Handle rate limits (60 writes/min), batch writes, retry on failure. This phase adds the Sheets writer — it does NOT modify the Telegram bot or identification pipeline.

</domain>

<decisions>
## Implementation Decisions

### Google Sheets API Strategy
- Use `gspread` library with service account authentication (JSON key file)
- Service account email shared with target spreadsheet as editor
- Wrap synchronous gspread calls with `asyncio.get_event_loop().run_in_executor(None, ...)` for async compatibility
- Each group/object can have its own spreadsheet configured in `telegram_groups.sheet_id` and `telegram_groups.sheet_name`

### Spreadsheet Layout Convention
- Rows = employees (identified by name or employee code in column A)
- Columns = dates (headers in row 1, format: DD.MM or DD.MM.YYYY)
- Cell value "1" means employee showed up for that shift date
- Employee row mapping stored in `group_employees.sheet_row` (integer, 1-indexed)
- Date column resolved dynamically by scanning header row for matching date

### Write Buffer Architecture
- Background task runs every 5 seconds
- Collects all shift_records with sheet_write_status = PENDING
- Groups by spreadsheet_id for batch operations
- Uses gspread `batch_update` (single API call per spreadsheet) to write multiple cells
- After successful write: update sheet_write_status to WRITTEN + set written_at timestamp
- On API error: increment retry_count, set status to ERROR if retry_count > 5, otherwise keep PENDING
- Exponential backoff on rate limit (429): 2^retry_count seconds, max 60s

### Cell Address Resolution
- Find employee row: use `group_employees.sheet_row` (pre-configured by admin)
- Find date column: scan header row (row 1) for matching date string
- Cache header row per spreadsheet for 5 minutes (avoid repeated reads)
- If date column not found: log error, set status to ERROR with reason "date_column_not_found"
- If sheet_row is 0 or null: log error, set status to ERROR with reason "employee_row_not_configured"

### Source Link Storage
- After writing "1", also write the Telegram message link in an adjacent cell or notes
- Message link format: `https://t.me/c/{chat_id}/{message_id}` (for private groups)
- Store link in processing_log.source_link field (already exists from Phase 1)

### Duplicate Protection
- Before writing "1", check if cell already contains "1"
- If yes: skip write, log as DUPLICATE_SHEET_SKIP in processing_log
- This is defense-in-depth — Phase 1 business dedup should catch most cases

### Claude's Discretion
- Exact gspread API calls and error handling
- Header row caching implementation
- Retry task lifecycle management
- Test mocking strategy for Google Sheets API

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Documentation
- `.planning/PROJECT.md` — Project context, constraints
- `.planning/REQUIREMENTS.md` — SHEET-01..05 requirements
- `.planning/research/STACK.md` — gspread version, async strategy
- `.planning/research/ARCHITECTURE.md` — Write buffer design, rate limits
- `.planning/research/PITFALLS.md` — Google Sheets API quota (60 req/min)

### Phase 1 Code (dependency)
- `shifttracker/db/models.py` — ShiftRecord model with sheet_write_status column
- `shifttracker/pipeline/worker.py` — Where shift records are created
- `shifttracker/config.py` — Settings class to extend with Sheets config

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `shifttracker/db/engine.py` — async_session_factory for DB operations
- `shifttracker/db/models.py` — ShiftRecord with sheet_write_status (PENDING/WRITTEN/ERROR)
- `shifttracker/config.py` — pydantic-settings pattern to extend
- `shifttracker/app.py` — lifespan pattern to add Sheets writer task

### Established Patterns
- asyncio worker pool pattern from pipeline/worker.py
- Alembic migrations for schema changes
- pytest-asyncio with SQLite in-memory for testing

### Integration Points
- ShiftRecord.sheet_write_status consumed by this phase
- app.py lifespan needs new background task for Sheets writer
- config.py needs GOOGLE_SHEETS_CREDENTIALS_FILE setting

</code_context>

<specifics>
## Specific Ideas

- PostgreSQL is source of truth — Sheets is display layer only
- If Sheets is down, nothing is lost — records stay PENDING in DB
- Batch writes minimize API calls: group multiple cell updates into one batchUpdate
- Service account approach avoids OAuth2 user flow complexity

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-google-sheets-integration*
*Context gathered: 2026-04-10*

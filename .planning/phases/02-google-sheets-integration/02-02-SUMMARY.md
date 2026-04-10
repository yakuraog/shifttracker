---
phase: 02-google-sheets-integration
plan: "02"
subsystem: integration
tags: [gspread, google-sheets, asyncio, batch-update, retry, deduplication, sqlalchemy]

# Dependency graph
requires:
  - phase: 02-google-sheets-integration
    plan: "01"
    provides: build_client(), header_cache, resolve_cell(), ShiftRecord.written_at/retry_count, TelegramGroup.sheet_id/sheet_name, Settings.sheets_flush_interval/sheets_max_retries
  - phase: 01-foundation
    provides: ShiftRecord, TelegramGroup, GroupEmployee, ProcessingLog models, async_session_factory
provides:
  - SheetsWriter class with start/stop lifecycle and _flush_loop background task
  - PENDING ShiftRecord consumption with batching by (sheet_id, sheet_name)
  - gspread batch_update integration writing "1" and source_link to adjacent cell
  - Duplicate detection via batch_get (cells already containing "1" -> DUPLICATE_SHEET_SKIP)
  - APIError retry logic with retry_count increments and max_retries -> ERROR escalation
  - date_column_not_found and employee_row_not_configured error handling
  - FastAPI lifespan integration (start before yield, stop during shutdown)
affects:
  - 03-admin-api (can query written_at and sheet_write_status)
  - 03-monitoring (SheetsWriter accessible via app.state.sheets_writer)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SheetsWriter: run blocking gspread calls in thread pool via loop.run_in_executor"
    - "Batch by spreadsheet: group PENDING records by (sheet_id, sheet_name) for single batch_update"
    - "ProcessingLog-based context resolution: use chat_id from ProcessingLog to find TelegramGroup"
    - "Duplicate check: batch_get before batch_update to detect cells already containing '1'"
    - "Graceful no-op: SheetsWriter.start() logs warning and returns if credentials file not configured"

key-files:
  created:
    - shifttracker/sheets/writer.py
    - tests/test_sheets_writer.py
  modified:
    - shifttracker/app.py

key-decisions:
  - "ProcessingLog used to resolve TelegramGroup from ShiftRecord: chat_id in ProcessingLog matches TelegramGroup.chat_id"
  - "session_factory callable accepted instead of direct AsyncSession: writer creates its own sessions per flush cycle"
  - "Header cache cleared in test autouse fixture (clear_all): ensures test isolation across test cases using same spreadsheet key"
  - "batch_get precedes batch_update: reads existing values in one call to detect duplicates before writing"
  - "sheets_writer.stop() called before engine.dispose() in shutdown sequence: ensures in-flight flush completes cleanly"

patterns-established:
  - "Pattern: SheetsWriter tests call _flush() directly — not the loop — for deterministic unit test control"
  - "Pattern: ProcessingLog chat_id is the join key from ShiftRecord to TelegramGroup (ShiftRecord has no direct group_id)"
  - "Pattern: _run_sync helper wraps all blocking gspread I/O in run_in_executor for asyncio compatibility"

requirements-completed:
  - SHEET-01
  - SHEET-02
  - SHEET-03
  - SHEET-04
  - SHEET-05

# Metrics
duration: 10min
completed: 2026-04-10
---

# Phase 2 Plan 02: SheetsWriter Summary

**SheetsWriter background task writes PENDING shift records to Google Sheets via gspread batch_update with duplicate detection, exponential retry via retry_count, and FastAPI lifespan wiring**

## Performance

- **Duration:** 10 min
- **Started:** 2026-04-10T17:55:07Z
- **Completed:** 2026-04-10T18:00:07Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- SheetsWriter class fully implemented: start/stop lifecycle, _flush_loop background task, _flush() with full batching and error handling
- ProcessingLog-based TelegramGroup resolution: uses source_message_id + employee_id to find chat_id, then TelegramGroup
- Duplicate protection via batch_get: reads all target cells before writing, skips cells already containing "1", creates DUPLICATE_SHEET_SKIP log entries
- Retry logic: APIError increments retry_count; reaching sheets_max_retries (5) elevates to ERROR status
- FastAPI lifespan integration: SheetsWriter starts after polling and stops before engine disposal
- 10 TDD test cases all passing with mocked gspread (including header cache isolation autouse fixture)

## Task Commits

Each task was committed atomically:

1. **TDD RED: Failing tests for SheetsWriter** - `b170a38` (test)
2. **Task 1: Implement SheetsWriter** - `245616c` (feat)
3. **Task 2: Wire SheetsWriter into FastAPI lifespan** - `6a773e8` (feat)

**Plan metadata:** (pending — see final commit)

## Files Created/Modified
- `shifttracker/sheets/writer.py` - SheetsWriter class with full flush loop, batching, retry, duplicate detection
- `tests/test_sheets_writer.py` - 10 test cases covering all SHEET requirements with mocked gspread
- `shifttracker/app.py` - Added SheetsWriter import, start/stop in lifespan, app.state.sheets_writer

## Decisions Made
- Used ProcessingLog.chat_id to resolve TelegramGroup from ShiftRecord — ShiftRecord has no direct group_id column, but ProcessingLog records the originating chat_id at processing time
- session_factory callable pattern instead of injecting a session directly — each _flush() call opens a fresh session to avoid stale transaction issues
- Header cache autouse fixture (clear_all) added to tests — necessary because the in-process dict cache persists between tests when using the same (sheet_id, sheet_name) key
- batch_get called before batch_update — reads all target cell values in one API call to detect duplicates without extra round-trips
- sheets_writer.stop() positioned before engine.dispose() in shutdown — ensures any ongoing flush completes while DB is still accessible

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test isolation via header cache autouse fixture**
- **Found during:** Task 1 (GREEN phase — test_date_column_not_found failed)
- **Issue:** test_write_one_cell populated in-process header cache for ("spreadsheet-abc", "Sheet1") with ["Name", "09.04", "09.04 link"]. Subsequent test_date_column_not_found used different headers mock but writer served cached headers, causing WRITTEN instead of ERROR
- **Fix:** Added `autouse=True` fixture in test file that calls `clear_all()` before and after each test
- **Files modified:** tests/test_sheets_writer.py
- **Verification:** All 10 tests pass in sequence
- **Committed in:** 245616c (Task 1 feat commit)

**2. [Rule 1 - Bug] Fixed incorrect assertion in test_batch_groups_by_spreadsheet**
- **Found during:** Task 1 (GREEN phase — assertion mismatch)
- **Issue:** Test comment correctly stated "emp1+emp2 already WRITTEN, so 0" but assertion said `== 1` — contradiction
- **Fix:** Corrected assertion to `== 0` for same-sheet mock_ws (already written) and `== 1` for other-sheet mock_ws2 (new record)
- **Files modified:** tests/test_sheets_writer.py
- **Verification:** test_batch_groups_by_spreadsheet passes
- **Committed in:** 245616c (Task 1 feat commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs in test logic)
**Impact on plan:** Both fixes were test-code correctness issues, not implementation changes. No scope creep. Production code matches plan specification exactly.

## Issues Encountered
- Header cache in-process dict requires explicit clearing between tests — test_header_cache.py already has clear_all() utility; the same pattern needed to be applied in test_sheets_writer.py via autouse fixture

## User Setup Required
None — SheetsWriter gracefully no-ops when GOOGLE_SHEETS_CREDENTIALS_FILE is not set. Production credentials setup is a deployment concern.

## Next Phase Readiness
- All SHEET-01 through SHEET-05 requirements are now implemented
- Phase 2 Google Sheets integration is complete
- Phase 3 (admin API / monitoring) can query sheet_write_status, written_at, retry_count on ShiftRecord
- SheetsWriter accessible via app.state.sheets_writer for health checks or manual flush endpoints
- Blocker from STATE.md still applies: production spreadsheet header date format must be validated before go-live

---
*Phase: 02-google-sheets-integration*
*Completed: 2026-04-10*

## Self-Check: PASSED

All 3 created/modified files found on disk. All 3 task commits (b170a38, 245616c, 6a773e8) confirmed in git log.

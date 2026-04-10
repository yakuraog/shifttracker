---
phase: 02-google-sheets-integration
plan: "01"
subsystem: database
tags: [gspread, google-auth, alembic, sheets, header-cache, cell-resolution]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: ShiftRecord, TelegramGroup, GroupEmployee models; Settings config; pytest/alembic infra
provides:
  - gspread==6.2.1 and google-auth>=2.0 project dependencies
  - ShiftRecord.written_at and ShiftRecord.retry_count columns
  - TelegramGroup.sheet_id and TelegramGroup.sheet_name columns
  - Alembic migration 002_add_sheets_fields
  - Settings.google_sheets_credentials_file, sheets_flush_interval, sheets_max_retries config
  - shifttracker/sheets/ module: build_client(), get_cached/set_cached/invalidate, resolve_cell()
affects:
  - 02-02-sheets-writer (consumes all artifacts produced here)

# Tech tracking
tech-stack:
  added:
    - gspread==6.2.1
    - google-auth>=2.0
  patterns:
    - "In-process dict cache with time.monotonic() TTL (no external cache dependency)"
    - "Multi-format date matching in header scan (DD.MM, D.M, with/without year)"
    - "gspread.utils.rowcol_to_a1 for A1 notation — handles columns beyond Z correctly"
    - "Thin factory function (build_client) for gspread.Client construction from service account file"

key-files:
  created:
    - shifttracker/sheets/__init__.py
    - shifttracker/sheets/client.py
    - shifttracker/sheets/header_cache.py
    - shifttracker/sheets/cell_resolve.py
    - shifttracker/db/migrations/versions/002_add_sheets_fields.py
    - tests/test_header_cache.py
    - tests/test_cell_resolve.py
  modified:
    - shifttracker/db/models.py
    - shifttracker/config.py
    - pyproject.toml

key-decisions:
  - "header_cache uses time.monotonic() not datetime.utcnow() — monotonic clock immune to system clock changes"
  - "CACHE_TTL stored as integer seconds (300) not timedelta — simpler arithmetic with monotonic float"
  - "resolve_cell tries 4 date formats: DD.MM, D.M, DD.MM.YYYY, D.M.YYYY — guards against unknown client spreadsheet format"
  - "Alembic migration written manually (no live DB needed) — matches autogenerate output format"
  - "google_sheets_credentials_file defaults to empty string — empty means Sheets writer disabled, avoids startup failure when unconfigured"

patterns-established:
  - "Pattern: sheets module is clean boundary — no other module imports gspread directly"
  - "Pattern: resolve_cell returns None for sheet_row=0 or None — prevents row 0 writes overwriting headers"
  - "Pattern: header cache clear_all() function for test isolation"

requirements-completed:
  - SHEET-01
  - SHEET-04
  - SHEET-05

# Metrics
duration: 3min
completed: 2026-04-10
---

# Phase 2 Plan 01: Google Sheets Infrastructure Summary

**gspread client factory, 300s in-process header cache, and multi-format cell resolver built with 20 passing unit tests and Alembic migration for 4 new DB columns**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-10T17:50:42Z
- **Completed:** 2026-04-10T17:53:58Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Extended ShiftRecord with written_at + retry_count and TelegramGroup with sheet_id + sheet_name; Alembic migration 002 created
- Added gspread==6.2.1 and google-auth>=2.0 as project dependencies and installed them
- Created shifttracker/sheets/ module with build_client(), header_cache (get/set/invalidate/clear_all with 300s TTL), and resolve_cell() with 4 date format candidates
- 20 unit tests covering all edge cases: cache miss/hit/expiry/invalidation, date format variants, sheet_row=0/None, adjacent link cell, whitespace stripping

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend models, config, and add dependencies** - `665effb` (feat)
2. **Task 2: Create sheets module — client, header cache, cell resolution** - `1d9ad65` (feat)

**Plan metadata:** (pending — see final commit)

## Files Created/Modified
- `pyproject.toml` - Added gspread==6.2.1, google-auth>=2.0 to dependencies
- `shifttracker/db/models.py` - Added written_at, retry_count to ShiftRecord; sheet_id, sheet_name to TelegramGroup
- `shifttracker/config.py` - Added google_sheets_credentials_file, sheets_flush_interval, sheets_max_retries settings
- `shifttracker/db/migrations/versions/002_add_sheets_fields.py` - Alembic migration for all 4 new columns
- `shifttracker/sheets/__init__.py` - Module stub with docstring
- `shifttracker/sheets/client.py` - build_client() factory using Credentials.from_service_account_file
- `shifttracker/sheets/header_cache.py` - In-process dict cache with CACHE_TTL=300s using time.monotonic()
- `shifttracker/sheets/cell_resolve.py` - resolve_cell() scanning headers with 4 date format candidates
- `tests/test_header_cache.py` - 9 tests for cache behavior including TTL expiry mock
- `tests/test_cell_resolve.py` - 11 tests for date format resolution and edge cases

## Decisions Made
- Used `time.monotonic()` for TTL tracking — immune to system clock changes unlike `datetime.utcnow()`
- `CACHE_TTL` stored as int (not timedelta) — arithmetic with float monotonic is simpler
- `resolve_cell` tries 4 date formats (DD.MM, D.M, DD.MM.YYYY, D.M.YYYY) — production header format is unknown per STATE.md blocker; multi-format matching handles the uncertainty safely
- Alembic migration written manually — autogenerate requires live DB connection not available in CI; manual migration matches the exact same output format
- `google_sheets_credentials_file` defaults to `""` — empty string signals Sheets writer should stay disabled, not fail at startup

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None — all steps succeeded on first attempt. The plan correctly anticipated that alembic autogenerate requires a live DB connection; manual migration was the intended approach per the migration file path specified in the plan frontmatter (`alembic/versions/002_add_sheets_fields.py`).

## User Setup Required

None — no external service configuration required for this infrastructure plan. Credentials setup will be required when the SheetsWriter (Plan 02) is deployed.

## Next Phase Readiness
- All infrastructure for Plan 02 (SheetsWriter) is in place
- build_client(), get_cached/set_cached/invalidate, and resolve_cell() are ready to be consumed
- DB models and migration are in place for all Sheets-related fields
- Blocker from STATE.md still applies: actual spreadsheet header date format (DD.MM vs D.M) must be validated against production data before Phase 2 goes live

---
*Phase: 02-google-sheets-integration*
*Completed: 2026-04-10*

## Self-Check: PASSED

All 7 created files found on disk. Both task commits (665effb, 1d9ad65) confirmed in git log.

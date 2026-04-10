---
phase: 01-foundation
plan: "03"
subsystem: bot-ingestion
tags: [aiogram, asyncio, queue, deduplication, tdd, sqlalchemy]

# Dependency graph
requires:
  - "01-01 (ORM models: TelegramGroup, ProcessingLog, ProcessedUpdate, ShiftRecord; async_session_factory)"
provides:
  - "aiogram Router with photo handler (silent, injects Update via DI for real update_id)"
  - "aiogram Router with migration handler updating TelegramGroup.chat_id"
  - "validate_message() filtering forwarded/document/non-photo messages"
  - "asyncio.Queue(maxsize=500) bounded queue with enqueue_message helper"
  - "check_duplicate() using INSERT + IntegrityError (inbox pattern)"
  - "check_business_duplicate() querying ShiftRecord by (employee_id, shift_date)"
affects: [pipeline-workers, shift-resolution, identify-stage]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "aiogram 3 DI: declare event_update: Update in handler params to receive parent Update"
    - "Inbox dedup: INSERT ProcessedUpdate + catch IntegrityError (works SQLite + PostgreSQL)"
    - "Silent processing: handlers return None, never call message.answer/reply"
    - "TDD: RED commit (failing tests) then GREEN commit (implementation)"

key-files:
  created:
    - shifttracker/bot/router.py
    - shifttracker/bot/middleware.py
    - shifttracker/pipeline/queue.py
    - shifttracker/pipeline/stages/__init__.py
    - shifttracker/pipeline/stages/validate.py
    - shifttracker/pipeline/stages/deduplicate.py
    - tests/test_bot_handlers.py
    - tests/test_dedup.py
  modified: []

key-decisions:
  - "event_update: Update DI parameter used in handle_photo to extract real update_id (never hardcoded)"
  - "IntegrityError catch for dedup instead of ON CONFLICT DO NOTHING — compatible with SQLite in tests"
  - "build_source_link strips -100 prefix from supergroup chat_id to form t.me/c/{id}/{msg} URL"

# Metrics
duration: 3min
completed: 2026-04-10
---

# Phase 1 Plan 03: Bot Ingestion, Validation, and Deduplication Summary

**aiogram 3 router with silent photo/migration handlers, validate_message filter, bounded asyncio.Queue, and inbox-pattern update_id dedup — all tested via TDD**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-10T17:19:20Z
- **Completed:** 2026-04-10T17:22:54Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- aiogram Router with `handle_photo` handler that receives the parent `Update` via aiogram 3 dependency injection (`event_update: Update` parameter), extracts the real `update_id` for dedup — never hardcoded
- `validate_message()` filters three rejection cases: `forwarded_message`, `document_not_photo`, `no_photo`
- `asyncio.Queue(maxsize=500)` with `enqueue_message()` helper for backpressure-aware enqueueing
- `check_duplicate()` uses INSERT + `IntegrityError` catch — works with both SQLite (tests) and PostgreSQL (prod)
- `check_business_duplicate()` queries `ShiftRecord` by `(employee_id, shift_date)` to prevent double shift marks
- `ErrorBoundaryMiddleware` catches handler exceptions, logs via loguru, prevents bot crash
- Migration handler updates `TelegramGroup.chat_id` when group upgrades to supergroup
- 18 tests passing (10 bot handler tests + 8 dedup tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: TDD RED — failing bot handler tests** - `6c09bab` (test)
2. **Task 1: TDD GREEN — bot router, validation, queue** - `27a5622` (feat)
3. **Task 2: TDD RED — failing dedup tests** - `0915552` (test)
4. **Task 2: TDD GREEN — deduplication stage** - `738ded5` (feat)

_Note: Each TDD task has two commits: test (RED) then feat (GREEN)._

## Files Created/Modified

- `shifttracker/bot/router.py` - aiogram Router with photo handler (update_id via DI), migration handler, build_source_link
- `shifttracker/bot/middleware.py` - ErrorBoundaryMiddleware catching exceptions with loguru logging
- `shifttracker/pipeline/queue.py` - Module-level asyncio.Queue(maxsize=500) and enqueue_message()
- `shifttracker/pipeline/stages/__init__.py` - Package init (empty)
- `shifttracker/pipeline/stages/validate.py` - validate_message() with 3 rejection reasons
- `shifttracker/pipeline/stages/deduplicate.py` - check_duplicate() and check_business_duplicate()
- `tests/test_bot_handlers.py` - 10 tests: validate_message, build_source_link, handle_photo update_id, migration handler
- `tests/test_dedup.py` - 8 tests: new/duplicate update_ids, DB insertion, business dedup scenarios

## Decisions Made

- `event_update: Update` is the standard aiogram 3 way to inject the parent Update object — declaring the parameter with type annotation causes aiogram to inject it from the middleware data dict key `event_update`
- `IntegrityError` catch chosen over `ON CONFLICT DO NOTHING` rowcount check for SQLite test compatibility
- `build_source_link` strips the `-100` prefix from supergroup chat IDs (e.g., `-1001234567890` → `1234567890`) to form valid `t.me/c/...` links
- Silent processing enforced: no `message.answer` or `message.reply` calls anywhere in router

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

All 6 created files exist. All 4 task commits found (6c09bab, 27a5622, 0915552, 738ded5). All 18 tests pass. Imports verified OK.

---
phase: 01-foundation
plan: "04"
subsystem: pipeline
tags: [asyncio, worker, fastapi, aiogram, uvicorn, sqlalchemy, pytest]

# Dependency graph
requires:
  - phase: 01-02
    provides: pipeline stage functions (identify_employee, resolve_shift_date, check_duplicate, check_business_duplicate)
  - phase: 01-03
    provides: aiogram router, ProcessingContext, message queue
provides:
  - process_message: full 5-stage pipeline orchestration
  - start_workers / stop_workers: asyncio task pool management
  - create_app: FastAPI app factory with lifespan
  - uvicorn entry point at shifttracker.main:app
affects: [phase-02-sheets, integration-tests]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - 5-stage pipeline: dedup -> identify -> resolve_date -> business_dedup -> write
    - TDD with in-memory SQLite fixture for end-to-end pipeline tests
    - asyncio task pool with cancel-on-shutdown pattern
    - FastAPI lifespan managing bot polling + worker pool

key-files:
  created:
    - shifttracker/pipeline/worker.py
    - shifttracker/app.py
    - shifttracker/main.py
    - tests/test_pipeline.py
  modified: []

key-decisions:
  - "Bot runs in long-polling mode (dev mode) via asyncio.create_task — not SimpleRequestHandler webhook — for Phase 1"
  - "polling_task cancelled with explicit await to suppress CancelledError on shutdown"
  - "test group_timezone set to UTC explicitly in outside_time_window test to avoid Europe/Moscow (+3h) tolerance overlap"

patterns-established:
  - "process_message: each pipeline stage outcome (ACCEPTED/NEEDS_REVIEW/DUPLICATE_SAME_SHIFT/ERROR) writes its own ProcessingLog and commits independently"
  - "_worker_tasks module-level list enables clean cancel/gather on shutdown"

requirements-completed:
  - TGRAM-03
  - TGRAM-05
  - IDENT-04
  - SHIFT-01
  - SHIFT-02
  - SHIFT-03
  - SHIFT-04
  - JRNL-01
  - JRNL-02
  - JRNL-03
  - JRNL-04

# Metrics
duration: 3min
completed: 2026-04-10
---

# Phase 01 Plan 04: Pipeline Worker and App Assembly Summary

**Full 5-stage pipeline worker with asyncio task pool, FastAPI app factory with lifespan, and 8 end-to-end tests proving every processing outcome**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-04-10T17:25:23Z
- **Completed:** 2026-04-10T17:28:00Z
- **Tasks:** 2 of 2
- **Files modified:** 4 created

## Accomplishments

- process_message wires all pipeline stages: update dedup -> identify employee -> resolve shift date -> business dedup -> write ShiftRecord + ProcessingLog
- Every processing outcome handled correctly: ACCEPTED, NEEDS_REVIEW (unknown employee + outside time window), DUPLICATE_SAME_SHIFT, ERROR (in worker error handler)
- ShiftRecord written with sheet_write_status=PENDING for Phase 2 Google Sheets writer consumption
- FastAPI create_app() with lifespan starts bot long-polling and 8 worker tasks, shuts down gracefully
- All 57 tests pass (8 new end-to-end pipeline tests + all prior test suites)

## Task Commits

Each task was committed atomically:

1. **Task 1: RED - Failing pipeline tests** - `e9f94ac` (test)
2. **Task 1: GREEN - Pipeline worker implementation** - `b4ab49c` (feat)
3. **Task 2: FastAPI app factory and entry point** - `88eb6e2` (feat)

## Files Created/Modified

- `shifttracker/pipeline/worker.py` - process_message, _worker, start_workers, stop_workers
- `shifttracker/app.py` - create_app() with lifespan context manager for bot + workers
- `shifttracker/main.py` - uvicorn entry point, app = create_app()
- `tests/test_pipeline.py` - 8 end-to-end pipeline tests covering all outcomes

## Decisions Made

- Bot runs in long-polling mode (dev mode) via `asyncio.create_task(dp.start_polling(bot))` — not webhook — for Phase 1. SimpleRequestHandler webhook pattern is deferred to production hardening.
- polling_task cancellation uses explicit `await polling_task` with CancelledError catch to avoid unhandled exception on shutdown.
- End-to-end test for outside_time_window explicitly sets `ctx.group_timezone = "UTC"` because the default group_timezone in ProcessingContext is "Europe/Moscow" (+3h UTC offset), which would push a 02:00 UTC message to 05:00 local — within the ±2h tolerance window of a 06:00 shift start.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test timezone mismatch in outside_time_window test**
- **Found during:** Task 1 (GREEN phase — test failed unexpectedly)
- **Issue:** Test built a TelegramGroup with timezone="UTC" but the ProcessingContext default group_timezone is "Europe/Moscow". At 02:00 UTC + 3h = 05:00 Moscow, only 1h before shift start (within ±2h tolerance). Test expected NEEDS_REVIEW but got CONFIRMED.
- **Fix:** Added `ctx.group_timezone = "UTC"` override in the test so local hour stays 02:00, which is 4h before 06:00 shift start — correctly outside ±2h tolerance.
- **Files modified:** tests/test_pipeline.py
- **Verification:** Test now produces NEEDS_REVIEW with reason="outside_time_window" as expected
- **Committed in:** b4ab49c (Task 1 feat commit, updated tests file)

---

**Total deviations:** 1 auto-fixed (Rule 1 — bug in test logic)
**Impact on plan:** Necessary correctness fix in test. No scope creep.

## Issues Encountered

None beyond the timezone test fix above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 1 Foundation complete: database models, pipeline stages, bot ingestion, worker orchestration, and app entry point are all production-ready
- Phase 2 can consume ShiftRecord rows where sheet_write_status="PENDING" to write to Google Sheets
- Bot privacy mode must be disabled via BotFather before connecting to any real group (pre-existing blocker from earlier plans)

---
*Phase: 01-foundation*
*Completed: 2026-04-10*

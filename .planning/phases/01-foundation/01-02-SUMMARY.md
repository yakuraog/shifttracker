---
phase: 01-foundation
plan: "02"
subsystem: pipeline-logic
tags: [sqlalchemy, zoneinfo, pytest-asyncio, tdd, confidence-ladder, night-shift]

# Dependency graph
requires:
  - "01-01: Employee, TelegramGroup, GroupEmployee, CaptionRule ORM models"
provides:
  - "identify_employee() function implementing 5-tier confidence ladder"
  - "resolve_shift_date() function with night shift midnight crossover and ±2h tolerance"
  - "ProcessingContext and IdentificationResult dataclasses in pipeline/models.py"
affects: [03-pipeline-wiring, 04-bot-handler]

# Tech tracking
tech-stack:
  added:
    - tzdata>=2024.1 (dev) — required for zoneinfo named timezones on Windows
  patterns:
    - "TDD: test files written before implementation (RED then GREEN commits)"
    - "Caption normalization: re.sub(r'\\s+', ' ', text.strip()).lower()"
    - "Confidence ladder: early-return on telegram_account, accumulate for caption_exact"
    - "Night shift detection: is_night_shift = shift_start_hour > shift_end_hour"

key-files:
  created:
    - shifttracker/pipeline/__init__.py
    - shifttracker/pipeline/models.py
    - shifttracker/pipeline/stages/__init__.py
    - shifttracker/pipeline/stages/identify.py
    - shifttracker/pipeline/stages/shift_date.py
    - tests/test_identification.py
    - tests/test_shift_date.py
  modified:
    - pyproject.toml (added tzdata>=2024.1 to dev deps)

key-decisions:
  - "telegram_account match is definitive — early return, no further steps evaluated"
  - "caption_exact can return multiple results (one per matched employee name)"
  - "Night shift detection: shift_start_hour > shift_end_hour (e.g. 22 > 6)"
  - "Naive datetime input assumed to be local time (no UTC conversion applied)"
  - "tzdata added to dev deps for Windows zoneinfo support (auto-fix Rule 3)"

# Metrics
duration: 3min
completed: 2026-04-10
---

# Phase 1 Plan 02: Pipeline Logic Summary

**Two pure business logic pipeline stages: employee identification confidence ladder (telegram_account > caption_exact > caption_keyword > group_fallback > empty) and shift date resolution with night shift midnight crossover and ±2h tolerance**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-10T17:19:16Z
- **Completed:** 2026-04-10T17:22:07Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- `ProcessingContext` and `IdentificationResult` dataclasses providing shared types for all pipeline stages
- `identify_employee()` implementing full 5-tier confidence ladder with case-insensitive normalized matching, multi-employee caption support, and early-return priority semantics
- `resolve_shift_date()` with complete day/night shift logic: midnight crossover (morning part = yesterday), ±2h tolerance at boundaries, and full timezone conversion via `zoneinfo.ZoneInfo`
- 23 total tests passing: 10 identification tests + 13 shift date tests (8 parametrized + 5 standalone)

## Task Commits

Each task was committed atomically using TDD (RED then GREEN):

1. **Task 1: TDD RED - failing identification tests** - `787a193` (test)
2. **Task 1: TDD GREEN - pipeline models and identify_employee** - `5261c56` (feat)
3. **Task 2: TDD RED - failing shift_date tests** - `3062150` (test)
4. **Task 2: TDD GREEN - resolve_shift_date implementation** - `b3eb51e` (feat)

_Note: Each TDD task has two commits: test (RED) then feat (GREEN)._

## Files Created/Modified

- `shifttracker/pipeline/__init__.py` — Empty package init
- `shifttracker/pipeline/models.py` — ProcessingContext and IdentificationResult dataclasses
- `shifttracker/pipeline/stages/__init__.py` — Empty package init
- `shifttracker/pipeline/stages/identify.py` — identify_employee() confidence ladder implementation
- `shifttracker/pipeline/stages/shift_date.py` — resolve_shift_date() with night shift and tolerance logic
- `tests/test_identification.py` — 10 test cases for all identification paths
- `tests/test_shift_date.py` — 13 test cases (8 parametrized) for shift date resolution
- `pyproject.toml` — Added tzdata>=2024.1 to dev deps

## Decisions Made

- `telegram_account` match is an early return — no other steps evaluated when user ID matches
- `caption_exact` accumulates all matching employees (enables multi-person captions) and returns them all
- Night shift detection is `shift_start_hour > shift_end_hour` — simple arithmetic, no flag needed
- Naive datetime inputs are treated as already in local time (applied ZoneInfo without conversion)
- `tzdata` added as dev dependency to support `zoneinfo` named timezone lookups on Windows

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Missing tzdata package for zoneinfo on Windows**
- **Found during:** Task 1 (first test run)
- **Issue:** `zoneinfo.ZoneInfo("Europe/Moscow")` raises `ZoneInfoNotFoundError` on Windows without `tzdata` package — system timezone database not available on Windows Python
- **Fix:** Installed `tzdata` via pip and added `tzdata>=2024.1` to `pyproject.toml` dev dependencies
- **Files modified:** `pyproject.toml`
- **Commit:** `5261c56` (included in Task 1 feat commit)

---

**Total deviations:** 1 auto-fixed (1 missing platform dependency)
**Impact on plan:** Essential for tests to run on Windows. No scope creep.

## Issues Encountered

None beyond the tzdata auto-fix above.

## User Setup Required

None — no external service configuration required for this plan.

## Next Phase Readiness

- `identify_employee()` and `resolve_shift_date()` ready to be called from the message processing pipeline (Plan 03)
- Both functions use `AsyncSession` (identify) and pure Python (shift_date) — easily composable
- All ORM model imports verified working through test suite
- **Note for Plan 03:** Pipeline wiring will call `identify_employee(ctx, session)` then `resolve_shift_date(ctx.message_datetime, ctx.shift_start_hour, ctx.shift_end_hour, ctx.group_timezone)` and populate `ctx.identifications` and `ctx.resolved_shift_date`

---
*Phase: 01-foundation*
*Completed: 2026-04-10*

## Self-Check: PASSED

All 8 expected files exist. All 4 task commits found (787a193, 5261c56, 3062150, b3eb51e). All 23 tests pass (10 identification + 13 shift_date).

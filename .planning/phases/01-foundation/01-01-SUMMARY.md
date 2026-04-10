---
phase: 01-foundation
plan: "01"
subsystem: database
tags: [sqlalchemy, alembic, pydantic-settings, asyncpg, aiosqlite, pytest-asyncio]

# Dependency graph
requires: []
provides:
  - "7 SQLAlchemy 2.0 ORM models: Employee, TelegramGroup, GroupEmployee, CaptionRule, ShiftRecord, ProcessingLog, ProcessedUpdate"
  - "Async DB engine factory via async_sessionmaker"
  - "Settings class loading from env vars via pydantic-settings"
  - "Alembic async migration env.py with 001_initial_schema creating all 7 tables"
  - "pytest async_session fixture using SQLite in-memory (aiosqlite)"
affects: [02-pipeline, 03-bot, 04-admin-ui]

# Tech tracking
tech-stack:
  added:
    - aiogram==3.27.0
    - sqlalchemy[asyncio]==2.0.49
    - asyncpg==0.31.0
    - alembic==1.18.4
    - pydantic-settings>=2.0
    - loguru>=0.7
    - fastapi[standard]
    - uvicorn[standard]
    - aiosqlite>=0.20 (test)
    - pytest-asyncio>=0.23 (test)
    - pytest-timeout (test)
  patterns:
    - "async_sessionmaker at module level — never create engine per-request"
    - "Settings via pydantic-settings BaseSettings with .env file support"
    - "SQLAlchemy 2.0 Mapped/mapped_column declarative style"
    - "TDD: test file written before implementation"

key-files:
  created:
    - pyproject.toml
    - shifttracker/__init__.py
    - shifttracker/config.py
    - shifttracker/db/__init__.py
    - shifttracker/db/engine.py
    - shifttracker/db/models.py
    - alembic.ini
    - shifttracker/db/migrations/env.py
    - shifttracker/db/migrations/script.py.mako
    - shifttracker/db/migrations/versions/001_initial_schema.py
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_models.py
    - .env.example
  modified: []

key-decisions:
  - "pydantic-settings used for config (not python-dotenv) — reads .env natively via SettingsConfigDict"
  - "bot_token and database_url have placeholder defaults so config is importable without .env in tests"
  - "pytest-timeout added to dev deps (required for --timeout=10 flag in verify commands)"
  - "Alembic async env.py uses asyncio.run() pattern with async_engine_from_config"

patterns-established:
  - "Settings: import from shifttracker.config; instantiate in module that needs it"
  - "Engine: module-level singleton in shifttracker/db/engine.py; tests create their own engine"
  - "Tests: use SQLite+aiosqlite in-memory via async_session fixture from conftest.py"
  - "Models: SQLAlchemy 2.0 style — Mapped[T] = mapped_column(...)"

requirements-completed: [TGRAM-03, SHIFT-03, JRNL-01, JRNL-02, JRNL-03, JRNL-04]

# Metrics
duration: 4min
completed: 2026-04-10
---

# Phase 1 Plan 01: Foundation Summary

**7 SQLAlchemy 2.0 async ORM models with UNIQUE deduplication constraints, Alembic async migration, pydantic-settings config, and passing pytest fixtures using SQLite in-memory**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-10T17:12:24Z
- **Completed:** 2026-04-10T17:16:32Z
- **Tasks:** 2
- **Files modified:** 14

## Accomplishments

- Project scaffold with pyproject.toml including all runtime and dev dependencies (aiogram 3.27.0, SQLAlchemy 2.0.49, asyncpg, alembic, pydantic-settings, loguru)
- 7 SQLAlchemy 2.0 ORM models with correct field types, UNIQUE constraints on `processed_updates.update_id` and `shift_records(employee_id, shift_date)`, and index on `processing_log(employee_id, shift_date)`
- Alembic async migration setup with `001_initial_schema.py` creating all 7 tables with correct constraints
- pytest fixtures with async SQLite in-memory session — all 8 model tests passing including IntegrityError assertions

## Task Commits

Each task was committed atomically:

1. **Task 1: Project scaffold, config, and DB engine** - `5e17e61` (feat)
2. **Task 2: TDD RED - failing model tests** - `bb61031` (test)
3. **Task 2: TDD GREEN - DB models and Alembic migration** - `e02374c` (feat)

_Note: TDD Task 2 has two commits: test (RED) then feat (GREEN)._

## Files Created/Modified

- `pyproject.toml` - Project metadata, all runtime + dev dependencies, pytest asyncio_mode=auto
- `shifttracker/config.py` - Settings class with pydantic-settings BaseSettings, .env support
- `shifttracker/db/engine.py` - Async engine and async_session_factory module-level singletons
- `shifttracker/db/models.py` - All 7 ORM models with Mapped/mapped_column, UNIQUE constraints, index
- `alembic.ini` - Alembic config pointing to shifttracker/db/migrations
- `shifttracker/db/migrations/env.py` - Async Alembic env using async_engine_from_config
- `shifttracker/db/migrations/versions/001_initial_schema.py` - Initial schema migration for all 7 tables
- `tests/conftest.py` - async_session fixture with SQLite in-memory, create_all/drop_all lifecycle
- `tests/test_models.py` - 8 tests covering all model fields and UNIQUE constraint violations
- `.env.example` - Template with all required env var placeholders

## Decisions Made

- `bot_token` and `database_url` have placeholder defaults in Settings so the class is importable in tests without a real `.env` file
- `pytest-timeout` added to dev dependencies because `--timeout=10` flag in verify commands requires it
- TDD flow followed: failing tests committed first (`bb61031`), then models implemented (`e02374c`)
- Alembic `env.py` uses `asyncio.run(run_async_migrations())` pattern for fully async migration execution

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added pytest-timeout to dev dependencies**
- **Found during:** Task 2 (verification step)
- **Issue:** `--timeout=10` flag in verify command requires `pytest-timeout` package; plan listed `timeout = 10` in pytest ini_options but did not include the package
- **Fix:** Added `pytest-timeout>=0.5` to `[project.optional-dependencies] dev` in pyproject.toml
- **Files modified:** pyproject.toml
- **Verification:** `pytest tests/test_models.py -x -q --timeout=10` runs without argument error
- **Committed in:** e02374c (Task 2 feat commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical dep)
**Impact on plan:** Essential for verify commands to work. No scope creep.

## Issues Encountered

- `python-telegram-bot 20.3` (pre-installed globally) conflicts with `httpx 0.28.1` — pip resolver warning only, does not affect shifttracker installation or test execution.

## User Setup Required

None - no external service configuration required for this plan. Database and bot token are not needed until integration testing.

## Next Phase Readiness

- All 7 ORM models importable and tested via SQLite in-memory
- Alembic ready to run against a real PostgreSQL instance (`alembic upgrade head`)
- Engine and session factory ready for use in subsequent pipeline and bot plans
- **Blocker reminder from STATE.md:** Bot privacy mode must be disabled via BotFather before connecting to any group

---
*Phase: 01-foundation*
*Completed: 2026-04-10*

## Self-Check: PASSED

All 13 expected files exist. All 3 task commits found (5e17e61, bb61031, e02374c). All 8 model tests pass. STATE.md updated, ROADMAP.md updated, 6 requirements marked complete.

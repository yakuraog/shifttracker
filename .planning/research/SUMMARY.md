# Project Research Summary

**Project:** ShiftTracker — Telegram Shift Monitoring + Google Sheets Auto-Fill
**Domain:** Telegram bot + async web API + Google Sheets integration (Python)
**Researched:** 2026-04-10
**Confidence:** HIGH

## Executive Summary

ShiftTracker is an automated attendance tracking system that monitors existing Telegram group chats for employee check-in photos and writes shift presence marks to Google Sheets. The key architectural insight from research is that this system must treat **PostgreSQL as the source of truth** and Google Sheets as a display layer only. The recommended approach is a single Python process built on the asyncio event loop, combining aiogram 3 (Telegram webhook handling) and FastAPI (admin API) within a shared uvicorn process, connected by an in-process `asyncio.Queue` that decouples photo ingestion from processing. This design handles 200 groups and thousands of photos per day without any external broker dependency.

The biggest technical risks are the Google Sheets API write quota (60 requests/minute per user) and Telegram's at-least-once delivery guarantee. Both are entirely mitigatable with established patterns: batch-buffer all Sheets writes and flush on a 5-second timer (one `batchUpdate` call covers N cells), and implement an inbox-pattern deduplication table keyed on `update_id` before any business logic. Employee identification is the core business-logic complexity — a three-tier confidence model (HIGH/MEDIUM/LOW) routing low-confidence matches to a manual review queue is the correct design. Never auto-assign on ambiguous caption matches.

A critical operational pitfall that catches developers by surprise is Telegram's **bot privacy mode**, which is enabled by default and silently discards all group photo messages that are not explicitly directed at the bot. This must be disabled via BotFather before adding the bot to any group, or the bot must hold admin status in each group. Night-shift midnight crossover logic (a photo at 00:15 belongs to Monday's shift, not Tuesday's) must be implemented as a configurable per-group shift window with a `date_offset` field — this is non-negotiable for correctness and must be built and unit-tested before any Sheets integration.

---

## Key Findings

### Recommended Stack

The stack is fully async Python built on aiogram 3.27.0 and FastAPI 0.115.x sharing a single asyncio event loop under uvicorn. PostgreSQL 16 with SQLAlchemy 2.0 async (asyncpg driver) handles all persistence. Google Sheets integration uses gspread 6.2.1 wrapped in gspread-asyncio to avoid blocking the event loop. All versions are pinned and verified from PyPI; compatibility constraints between packages are well-documented.

The stack avoids several common mistakes: psycopg2 (synchronous, blocks the event loop), Celery (overkill and fights asyncio), synchronous gspread without an executor wrapper, and the Telethon/Pyrogram userbot approach (ToS violation). The async-first design is consistent from the Telegram handler down to the database driver.

**Core technologies:**
- **Python 3.11+**: Stable production runtime; required by aiogram 3's asyncio foundation
- **aiogram 3.27.0**: De-facto standard async Telegram bot framework; Router/FSM/middleware system
- **FastAPI 0.115.x**: Admin API and webhook endpoint; shares asyncio event loop with aiogram; Pydantic v2 validation built-in
- **PostgreSQL 16 + SQLAlchemy 2.0 async (asyncpg 0.31.0)**: ACID-compliant persistence; handles concurrent writes; composite indexes for deduplication hot path
- **Alembic 1.18.4**: Schema migrations; initialized with async template (`alembic init -t async`)
- **gspread 6.2.1 + gspread-asyncio**: Google Sheets API v4; async wrapper prevents event loop blocking
- **tenacity 8.x**: Exponential backoff on Sheets 429 errors
- **pydantic-settings 2.x**: Typed configuration from environment variables

### Expected Features

The feature set is well-defined. The system's differentiating constraint is zero behavioral change for guards — they continue sending photos in existing groups; the system is invisible to them. All complexity is in the backend.

**Must have (table stakes):**
- Photo message ingestion from configured Telegram groups
- Employee identification by caption text (exact + fuzzy match) with Telegram account as fallback
- Shift date resolution with configurable per-group time windows (midnight crossover handled via `date_offset`)
- Duplicate rejection via DB unique constraint on `(employee_id, shift_date, group_id)`
- Idempotent Google Sheets write ("1" in cell) with local DB as primary dedup layer
- Processing audit log — every message gets exactly one log record with full state history
- Manual review queue with accept/reject/escalate actions in admin UI
- Employee registry CRUD (name, aliases, Telegram account linkage)
- Group configuration CRUD (group → object, spreadsheet ID, shift windows)

**Should have (competitive differentiators):**
- Confidence scoring on employee identification (HIGH/MEDIUM/LOW) surfaced in review queue
- Per-group caption parsing rules for non-standard group conventions
- Operator Telegram notifications for new review queue items (mobile-friendly)
- Graceful quota degradation: `SHEET_WRITE_PENDING` state with independent retry job and dashboard visibility

**Defer (v2+):**
- Face recognition on check-in photos — requires GPU infra, labeled data, privacy assessment; only pursue if caption-based system has high error rate
- Payroll/HR system integration (1C, etc.) — different compliance domain
- Predictive no-show alerts — requires schedule data not just attendance records
- Mobile app for operators — web interface is sufficient for v1

### Architecture Approach

The system runs as a single Python process on the asyncio event loop. A Telegram webhook handler (aiogram, mounted on a FastAPI route via `SimpleRequestHandler`) journals incoming photo messages to PostgreSQL and drops them into a bounded `asyncio.Queue(maxsize=500)`. A pool of 8 worker coroutines drains the queue through a stage-based pipeline: validate → identify employee → resolve shift date → deduplicate → enqueue Sheets write. The Sheets writer batches all pending writes and flushes every 5 seconds via a single `batchUpdate` API call. On crashes, messages in `RECEIVED` status are replayed from PostgreSQL on startup. At this scale (200 groups, ~5k messages/day), this single-process design is sufficient; Redis + arq is the upgrade path if multiple processes are ever needed.

**Major components:**
1. **Telegram Webhook Handler** (`bot/`) — receives updates via HTTPS POST, journals to DB with status `RECEIVED`, enqueues to processing queue; returns 200 immediately (never processes inline)
2. **Processing Pipeline** (`pipeline/stages/`) — validate, identify, shift_date, deduplicate, write_sheet as independent pure async stage functions receiving/returning a `ProcessingContext`; exception types (`SkipMessage`, `NeedsReview`) route to appropriate log states
3. **Sheets Writer** (`sheets/`) — accumulates `SheetWriteRequest` objects; flushes on timer or buffer-size threshold; exponential backoff on 429; never called directly by pipeline stages
4. **Admin API** (`admin/`) — FastAPI CRUD routers for groups, employees, shift windows, review queue; business logic in `db/repositories/`, not in route handlers
5. **Database Layer** (`db/`) — SQLAlchemy 2.x async models; `messages` table is the audit log; `processed_shifts` table is the dedup guard with unique index on `(employee_id, group_id, shift_date)`

### Critical Pitfalls

1. **Bot privacy mode silently blocks all group photo messages** — Disable via BotFather `/setprivacy` before adding to any group, then re-add the bot. Or make the bot an admin in each group (more reliable long-term for 200 groups). Verify by sending an un-mentioned photo and checking for a DB record.

2. **Google Sheets write quota exhausted during shift-start bursts** — Never write per-message. Buffer all writes in PostgreSQL (`SHEET_WRITE_PENDING`), flush via `batchUpdate` every 5 seconds. One `batchUpdate` call covers N cells and counts as 1 API request. Implement from day one — retrofitting is painful.

3. **Midnight crossover assigns check-in to wrong shift date** — Implement `resolve_shift_date(timestamp, group_id)` using per-group shift windows with a `date_offset` field. Store the resolved date in the DB; never derive it at query time. Unit test with explicit timestamps: 23:50, 00:01, 00:15, 06:00.

4. **Telegram at-least-once delivery causes duplicate processing** — Inbox pattern: `INSERT INTO processed_updates (update_id) ON CONFLICT DO NOTHING` before any business logic, within the same transaction as the attendance write. Dedup key for business logic is `(employee_id, group_id, shift_date)`, not `message_id`.

5. **Group-to-supergroup migration changes chat_id permanently** — Handle `migrate_to_chat_id` service messages; update `groups.chat_id` in DB automatically. Without this handler, the bot silently stops receiving messages from migrated groups with no error.

6. **Employee identification ambiguity causes silent wrong assignments** — Three-tier confidence model is mandatory: HIGH (exact account match) → auto-approve; MEDIUM (fuzzy caption) → auto-approve with audit flag; LOW/NONE → mandatory manual review queue. Never auto-write on ambiguous matches. An always-empty review queue is a warning sign, not a success indicator.

7. **Bot restart with `drop_pending_updates=True` loses attendance records** — Never use this in production. Telegram buffers updates for 24 hours. On startup, process the backlog at a controlled rate. Persist polling offset to PostgreSQL (not memory).

---

## Implications for Roadmap

### Phase 1: Foundation — Database + Bot Infrastructure

**Rationale:** All other components depend on the database schema and the ability to receive Telegram messages. Privacy mode, group migration handling, and deduplication must be established first — they cannot be retrofitted without replaying historical data. The processing pipeline stages are pure business logic that can be built and tested without Sheets or a live Telegram connection.

**Delivers:**
- PostgreSQL schema with all tables, indexes, and Alembic migrations
- aiogram 3 webhook handler mounted on FastAPI; lifespan startup/shutdown wired
- Inbox-pattern deduplication (`processed_updates` table)
- Group migration handler (`migrate_to_chat_id`)
- Shift date resolver (`resolve_shift_date`) with unit tests covering midnight edge cases
- Employee identification pipeline stages (validate → identify → shift_date → deduplicate) with confidence tiers
- Manual review queue data model
- Processing audit log (all status states: RECEIVED, PROCESSING, PROCESSED, SKIPPED, NEEDS_REVIEW, DUPLICATE_REJECTED, ERROR, SHEET_WRITE_PENDING)

**Addresses features:** Photo ingestion, employee identification (caption + account), shift date resolution, duplicate rejection, audit log, manual review queue data model

**Avoids pitfalls:** Privacy mode (document setup procedure), deduplication (inbox pattern from first commit), midnight crossover (resolver unit-tested before integration), group migration (handler in initial bot router), update recovery on restart (no `drop_pending_updates`), outbound rate limiting (AioRateLimiter middleware installed)

**Research flag:** Standard patterns — this phase uses well-documented aiogram 3 and SQLAlchemy 2 async patterns. No additional research phase needed.

---

### Phase 2: Google Sheets Integration

**Rationale:** Sheets integration is isolated because it has its own rate-limit domain and failure mode. The pipeline outputs `SHEET_WRITE_PENDING` records to PostgreSQL in Phase 1; this phase adds the writer that consumes them. Building this after the pipeline ensures the source-of-truth (PostgreSQL) is stable before adding the display layer.

**Delivers:**
- `SheetsWriter` class with internal write buffer, 5-second flush timer, `batchUpdate` API call
- Exponential backoff with jitter on HTTP 429 (tenacity)
- Service account authentication (no personal OAuth tokens)
- Cell address resolution by header name (not hardcoded row/column positions)
- Independent retry job for `SHEET_WRITE_PENDING` records on startup and periodic sweep
- Load test: 70 write requests within 60 seconds, all eventually persisted

**Uses:** gspread 6.2.1, gspread-asyncio, google-auth, tenacity

**Avoids pitfalls:** Sheets quota exhaustion (batching from day one), hardcoded cell addresses (header-lookup pattern), personal OAuth (service account only)

**Research flag:** Standard patterns — Google Sheets batch API is well-documented. Rate-limit handling with tenacity is established. No additional research phase needed.

---

### Phase 3: Admin Web Interface

**Rationale:** Once the pipeline and Sheets writer are functional end-to-end, the admin interface exposes configuration and the review queue to operators. This phase has no new architectural risk — it is CRUD over data models already built in Phase 1. It can be developed and tested independently against the existing database.

**Delivers:**
- Employee registry CRUD (name, caption aliases, Telegram account)
- Group configuration CRUD (group → spreadsheet, shift windows per group)
- Manual review queue UI (accept with employee assignment, reject with reason, escalate)
- Sheets sync status display per group (last synced, pending write count)
- Basic authentication for admin endpoints
- FastAPI OpenAPI docs auto-generated

**Addresses features:** Employee registry admin, group/shift window config admin, manual review workflow, audit trail visibility

**Avoids pitfalls:** Review queue SLA visibility (created_at surfaced in UI), sync error visibility (SHEET_WRITE_PENDING count shown per group)

**Research flag:** Standard patterns — FastAPI CRUD with SQLAlchemy repositories is fully established. No additional research phase needed.

---

### Phase 4: Hardening + Observability

**Rationale:** After end-to-end integration is working with real data, known edge cases and operational visibility gaps surface. This phase addresses v1.x features identified in research: confidence score display, per-group caption rules, retry queue dashboard, and operator Telegram notifications. These are triggered by real operator feedback, not speculative.

**Delivers:**
- Confidence score display in review queue UI
- Per-group configurable caption parsing rules (regex patterns)
- Operator Telegram notifications for new review queue items (inline keyboard accept/reject)
- Retry queue dashboard (pending writes, retry history, 429 event log)
- Startup alert with buffered update count
- SLA alerting for review queue items older than 4 hours

**Addresses features:** Confidence scoring, per-group caption rules, operator notifications, graceful quota degradation dashboard

**Research flag:** Operator Telegram notifications require research — inline keyboard callbacks with operator bot or existing bot instance involves non-trivial aiogram FSM state management. Recommend `/gsd:research-phase` for this phase.

---

### Phase Ordering Rationale

- **Phase 1 before Phase 2:** PostgreSQL is the source of truth; Sheets is the display layer. Processing pipeline must be stable before connecting the display layer. Deduplication and shift date logic must be correct before any cell is written.
- **Phase 1 before Phase 3:** Admin UI operates over data models built in Phase 1. No admin UI decisions need to be made until the pipeline is running.
- **Phase 2 before Phase 3:** Sheets sync status (pending writes, last sync) displayed in admin UI requires the Sheets writer to be operational.
- **Phase 4 last:** Hardening features are explicitly triggered by real production feedback. Building them before having production data leads to solving the wrong problems.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (Operator Telegram Notifications):** Inline keyboard callbacks for review actions in an existing bot require careful state management; the interaction model for operator-facing bots in aiogram 3 has nuances not covered in the initial research. Recommend `/gsd:research-phase` before planning Phase 4.

Phases with standard patterns (skip research-phase):
- **Phase 1:** aiogram 3 webhook + SQLAlchemy 2 async + Alembic are well-documented with multiple corroborating sources. All patterns verified from official docs.
- **Phase 2:** Google Sheets `batchUpdate` and tenacity retry patterns are fully documented. Rate limit numbers verified from Google official docs.
- **Phase 3:** FastAPI CRUD + dependency injection pattern is canonical. No novel integration work.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified from PyPI; integration patterns from official docs and active community; version compatibility matrix explicit |
| Features | HIGH (core), MEDIUM (edge cases) | Core features (ingestion, identification, dedup, Sheets write) are HIGH. Edge-case behaviors (confidence tier thresholds, per-group caption rule syntax) are MEDIUM — will be tuned during v1.x |
| Architecture | HIGH (patterns), MEDIUM (scale estimates) | Single-process asyncio design is well-validated. Scale estimates (8 workers sufficient for 200 groups) are reasonable estimates, not benchmarked |
| Pitfalls | HIGH | All critical pitfalls verified against official Telegram and Google docs; Telegram rate limits and privacy mode behavior confirmed from official sources |

**Overall confidence:** HIGH

### Gaps to Address

- **Confidence tier thresholds:** The exact Levenshtein distance threshold and score weights for MEDIUM vs LOW identification confidence are not empirically validated. These should be tunable configuration values from day one, with defaults to be calibrated against real caption data from the first production groups.
- **gspread-asyncio maturity:** Listed as MEDIUM confidence in STACK.md. The library is a maintained wrapper but has a smaller community than gspread itself. If it proves problematic, the fallback is running gspread in `loop.run_in_executor()` manually — functionally equivalent.
- **Spreadsheet layout conventions:** The research assumes "1" is written to a cell identified by employee row + shift date column. The exact cell address resolution strategy (header-lookup vs named ranges) depends on the actual client spreadsheet structure, which was not available during research. This must be validated with the client before Phase 2 development begins.
- **Operator notification delivery model (Phase 4):** Whether to use the existing bot or a separate operator bot for inline keyboard review notifications has UX and security implications that require clarification with the client before Phase 4 planning.

---

## Sources

### Primary (HIGH confidence)
- [aiogram PyPI 3.27.0](https://pypi.org/project/aiogram/) — version confirmed
- [aiogram GitHub releases](https://github.com/aiogram/aiogram/releases) — changelog and compatibility
- [aiogram webhook docs](https://docs.aiogram.dev/en/latest/dispatcher/webhook.html) — SimpleRequestHandler pattern
- [gspread PyPI 6.2.1](https://pypi.org/project/gspread/) — version confirmed
- [SQLAlchemy PyPI 2.0.49](https://pypi.org/project/sqlalchemy/) — version confirmed
- [asyncpg PyPI 0.31.0](https://pypi.org/project/asyncpg/) — version confirmed
- [Alembic PyPI 1.18.4](https://pypi.org/project/alembic/) — version confirmed
- [Alembic async cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html) — async migration pattern
- [FastAPI settings docs](https://fastapi.tiangolo.com/advanced/settings/) — pydantic-settings integration
- [FastAPI lifespan events](https://fastapi.tiangolo.com/advanced/events/) — lifespan context manager
- [Google Sheets API limits](https://developers.google.com/workspace/sheets/api/limits) — 300 req/min/project, 60 req/min/user confirmed
- [Google Sheets batchUpdate guide](https://developers.google.com/workspace/sheets/api/guides/batchupdate) — batch write pattern
- [Telegram Bot API privacy mode](https://core.telegram.org/bots/features) — default privacy mode behavior
- [Telegram Bot API rate limits](https://core.telegram.org/bots/faq) — 30 msg/s global, 20 msg/min per chat
- [Inbox Pattern for idempotency](https://dev.to/actor-dev/inbox-pattern-51af) — deduplication pattern

### Secondary (MEDIUM confidence)
- [gspread-asyncio docs](https://gspread-asyncio.readthedocs.io/en/latest/api.html) — async wrapper API
- [aiogram-fastapi-server PyPI](https://pypi.org/project/aiogram-fastapi-server/) — FastAPI mount helper
- [aiogram + FastAPI template](https://github.com/bralbral/fastapi_aiogram_template) — integration example
- [BetterStack: TortoiseORM vs SQLAlchemy 2025](https://betterstack.com/community/guides/scaling-python/tortoiseorm-vs-sqlalchemy/) — ORM comparison
- [asyncio backpressure patterns](https://blog.changs.co.uk/asyncio-backpressure-processing-lots-of-tasks-in-parallel.html) — worker pool pattern
- [DutyTick competitor](https://dutytick.com/) — feature comparison reference
- [TelegramAttendanceBot open-source reference](https://github.com/AsutoshPati/TelegramAttendanceBot) — existing pattern
- [Telegram group migration behavior](https://github.com/tdlib/telegram-bot-api/issues/266) — chat_id change on supergroup upgrade

### Tertiary (LOW confidence)
- Confidence tier threshold values (Levenshtein distance ≤ 2) — inferred from general NLP fuzzy matching practice; needs empirical calibration against real caption data

---
*Research completed: 2026-04-10*
*Ready for roadmap: yes*

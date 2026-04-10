# Architecture Research

**Domain:** Telegram-based shift tracking system (photo ingestion → data extraction → Google Sheets)
**Researched:** 2026-04-10
**Confidence:** HIGH (core patterns), MEDIUM (scale estimates)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Single Python Process                         │
│                    (uvicorn + asyncio event loop)                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────┐        ┌──────────────────────────────┐    │
│  │   Telegram Webhook   │        │        Admin API             │    │
│  │   (aiogram 3)        │        │        (FastAPI)             │    │
│  │                      │        │                              │    │
│  │  photo_handler       │        │  /groups  /employees         │    │
│  │  middleware stack    │        │  /shifts  /review            │    │
│  └──────────┬───────────┘        └──────────────────────────────┘    │
│             │ enqueue                                                 │
│             ▼                                                         │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │              asyncio.Queue  (bounded, maxsize=500)           │    │
│  └──────────────────────┬───────────────────────────────────────┘    │
│                         │ dequeue                                     │
│             ┌───────────┴────────────┐                               │
│             ▼                        ▼                               │
│  ┌──────────────────┐    ┌──────────────────┐  (N workers, default 8)│
│  │  Worker Coroutine │    │  Worker Coroutine │                       │
│  │  ┌─────────────┐ │    │  ┌─────────────┐ │                       │
│  │  │ 1. Validate │ │    │  │ 1. Validate │ │                       │
│  │  │ 2. Identify │ │    │  │ 2. Identify │ │                       │
│  │  │ 3. Dedupe   │ │    │  │ 3. Dedupe   │ │                       │
│  │  │ 4. Write    │ │    │  │ 4. Write    │ │                       │
│  │  └─────────────┘ │    │  └─────────────┘ │                       │
│  └──────────┬────────┘    └──────────┬───────┘                       │
│             └───────────┬────────────┘                               │
│                         ▼                                            │
│            ┌────────────────────────┐                                │
│            │   Sheets Writer        │                                │
│            │   (gspread-asyncio)    │                                │
│            │   batch queue + retry  │                                │
│            └────────────────────────┘                                │
├─────────────────────────────────────────────────────────────────────┤
│                          Data Layer                                  │
│  ┌─────────────────┐   ┌──────────────────┐   ┌──────────────────┐  │
│  │   PostgreSQL     │   │  Google Sheets   │   │  Telegram CDN    │  │
│  │   (SQLAlchemy    │   │  (shift table)   │   │  (photo storage  │  │
│  │    async)        │   │                  │   │   by reference)  │  │
│  └─────────────────┘   └──────────────────┘   └──────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Implementation |
|-----------|----------------|----------------|
| Telegram Webhook Handler | Receive updates from Telegram, enqueue raw messages | aiogram 3 router mounted on FastAPI via `SimpleRequestHandler` |
| asyncio.Queue | Decouple ingestion from processing, bound burst load | `asyncio.Queue(maxsize=500)` — native to event loop, no external deps |
| Worker Pool | Parallel processing of queued messages (N concurrent) | `asyncio.gather` over N worker coroutines, each loops on `queue.get()` |
| Processing Pipeline | Validate → identify → deduplicate → route | Pure async functions called in sequence within each worker |
| Sheets Writer | Batch writes to Google Sheets with rate-limit awareness | gspread-asyncio with internal write buffer, flush every N seconds |
| Admin API | CRUD for groups, employees, rules; review queue | FastAPI routers, same process, shared DB connection pool |
| PostgreSQL | Message journal, employee registry, dedup cache, review queue | SQLAlchemy 2.x async (asyncpg driver) |

## Recommended Project Structure

```
shifttracker/
├── main.py                   # process entry point: build app, start uvicorn
├── app.py                    # FastAPI app factory, lifespan context manager
├── config.py                 # pydantic-settings, env vars
│
├── bot/
│   ├── router.py             # aiogram Router, photo/message handlers
│   ├── middleware.py         # logging, error boundary middleware
│   └── webhook.py            # SimpleRequestHandler mount helper
│
├── pipeline/
│   ├── queue.py              # module-level asyncio.Queue instance
│   ├── worker.py             # worker coroutine, pool startup/shutdown
│   ├── stages/
│   │   ├── validate.py       # message has photo + caption, group is known
│   │   ├── identify.py       # match employee from caption / tg user id
│   │   ├── shift_date.py     # determine shift date from time windows
│   │   ├── deduplicate.py    # check processed_messages table
│   │   └── write_sheet.py    # call sheets_writer
│   └── models.py             # ProcessingContext dataclass passed through stages
│
├── sheets/
│   ├── writer.py             # gspread-asyncio wrapper, internal batch buffer
│   ├── retry.py              # exponential backoff for 429 errors
│   └── models.py             # SheetWriteRequest dataclass
│
├── admin/
│   ├── router.py             # FastAPI router: /api/v1/...
│   ├── groups.py             # group CRUD
│   ├── employees.py          # employee CRUD
│   ├── review.py             # manual review endpoint
│   └── deps.py               # shared FastAPI dependencies (db session etc.)
│
├── db/
│   ├── engine.py             # async engine + session factory
│   ├── models.py             # SQLAlchemy ORM models
│   ├── repositories/
│   │   ├── employees.py
│   │   ├── groups.py
│   │   ├── messages.py       # journal + dedup
│   │   └── shifts.py
│   └── migrations/           # alembic
│
└── tests/
    ├── unit/
    └── integration/
```

### Structure Rationale

- **bot/**: Isolated so aiogram handlers never import from admin/. Depends only on pipeline/.
- **pipeline/stages/**: Each stage is a pure function `async def run(ctx: ProcessingContext) -> ProcessingContext`. Easy to test, easy to add/remove stages.
- **sheets/**: Isolated because Google Sheets API has its own rate-limit logic. Other code calls `writer.enqueue(request)`, never calls gspread directly.
- **admin/**: FastAPI routers only. Business logic goes in db/repositories/.
- **db/**: Single source of truth for all persistence. No model definitions scattered across features.

## Architectural Patterns

### Pattern 1: Webhook over Long-Polling for Production

**What:** aiogram 3 provides `SimpleRequestHandler` which mounts aiogram's dispatcher as a FastAPI route handler. Telegram pushes updates via HTTPS POST to your endpoint.
**When to use:** Production. Long-polling is fine for development only — it blocks process shutdown, can miss updates under load, and does not compose with uvicorn graceful shutdown.
**Trade-offs:** Requires public HTTPS URL (use ngrok in dev). Certificate must be valid.

**Example:**
```python
# app.py
from contextlib import asynccontextmanager
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from fastapi import FastAPI

bot: Bot | None = None
dp: Dispatcher | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bot, dp
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(bot_router)

    # Start worker pool
    await worker_pool.start(queue=message_queue, n_workers=settings.worker_count)

    # Register webhook
    await bot.set_webhook(url=settings.webhook_url, secret_token=settings.webhook_secret)

    yield

    # Shutdown
    await worker_pool.stop()
    await bot.delete_webhook()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

# Mount aiogram handler
handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
handler.register(app, path="/webhook/telegram")
```

### Pattern 2: Bounded asyncio.Queue as Processing Buffer

**What:** The Telegram handler drops the raw aiogram `Message` object into an `asyncio.Queue`. A fixed pool of worker coroutines consumes from it. `maxsize` applies backpressure when workers fall behind.
**When to use:** Single-process deployments handling bursty I/O-bound workloads. Thousands of messages per day at 200 groups is roughly 10-50 msg/sec peak — well within asyncio's capacity without any external broker.
**Trade-offs:** Queue is in-memory. Process restart loses un-processed messages in queue (mitigated: messages are already journaled in DB at enqueue time so they can be replayed). If you grow past one process, replace queue with Redis + arq.

**Example:**
```python
# pipeline/queue.py
import asyncio

message_queue: asyncio.Queue = asyncio.Queue(maxsize=500)

# pipeline/worker.py
async def worker(queue: asyncio.Queue):
    while True:
        message = await queue.get()
        try:
            ctx = await build_context(message)
            ctx = await validate(ctx)
            ctx = await identify(ctx)
            ctx = await shift_date(ctx)
            ctx = await deduplicate(ctx)
            await write_sheet(ctx)
            await journal_success(ctx)
        except SkipMessage as e:
            await journal_skip(message, reason=str(e))
        except Exception as e:
            await journal_error(message, error=str(e))
        finally:
            queue.task_done()

async def start_pool(queue: asyncio.Queue, n: int = 8):
    return [asyncio.create_task(worker(queue)) for _ in range(n)]
```

### Pattern 3: Write-Buffer for Google Sheets

**What:** Never call Google Sheets API per message. Accumulate writes in an in-memory list. Flush on timer (every 5s) OR when buffer reaches N entries. Use `spreadsheets.values.batchUpdate` to write multiple cells in one API call.
**When to use:** Always. Google Sheets API allows 300 requests/minute/project and 60 requests/minute/user. At 10 messages/sec that is 600 req/min — hits limit immediately without batching.
**Trade-offs:** Writes are delayed by up to flush interval. Acceptable for shift tracking (near real-time, not millisecond real-time). If Sheets write fails, the message journal in PostgreSQL is the source of truth — a retry job can replay from there.

**Example:**
```python
# sheets/writer.py
import asyncio
from dataclasses import dataclass, field

@dataclass
class SheetWriteRequest:
    spreadsheet_id: str
    range_: str       # e.g. "Sheet1!C5"
    value: str        # "1"
    message_id: int   # for tracing

class SheetsWriter:
    def __init__(self, flush_interval: float = 5.0, max_buffer: int = 50):
        self._buffer: list[SheetWriteRequest] = []
        self._flush_interval = flush_interval
        self._max_buffer = max_buffer
        self._task: asyncio.Task | None = None

    async def start(self):
        self._task = asyncio.create_task(self._flush_loop())

    async def enqueue(self, req: SheetWriteRequest):
        self._buffer.append(req)
        if len(self._buffer) >= self._max_buffer:
            await self._flush()

    async def _flush_loop(self):
        while True:
            await asyncio.sleep(self._flush_interval)
            if self._buffer:
                await self._flush()

    async def _flush(self):
        batch, self._buffer = self._buffer, []
        # call gspread-asyncio batchUpdate with exponential backoff
        ...
```

### Pattern 4: Stage-Based Processing Pipeline

**What:** Each processing step is an independent async function receiving and returning a `ProcessingContext` dataclass. Stages raise typed exceptions (`SkipMessage`, `NeedsReview`, `ProcessingError`) rather than returning error codes.
**When to use:** Always for this domain. Shift detection involves conditional branching (known employee? known group? time window valid?) that becomes unmaintainable in a monolithic handler.
**Trade-offs:** Slightly more boilerplate than inline code. Worth it: each stage is unit-testable in isolation.

## Data Flow

### Happy Path: Photo Arrives → Shift Marked

```
Telegram servers
    │ POST /webhook/telegram
    ▼
aiogram SimpleRequestHandler
    │ parse Update → Message
    ▼
photo_handler (aiogram router)
    │ journal_received(message) → DB [status=RECEIVED]
    │ queue.put_nowait(message)
    ▼
asyncio.Queue
    ▼
Worker coroutine
    │
    ├── validate(ctx)          checks: has photo, has caption, group is registered
    │                          raises SkipMessage if not
    │
    ├── identify(ctx)          match caption → employee_id (exact name)
    │                          or match tg_user_id → employee_id (registry)
    │                          raises NeedsReview if ambiguous
    │
    ├── shift_date(ctx)        apply time window rules for group
    │                          determine: today / yesterday / specific date
    │
    ├── deduplicate(ctx)       SELECT FROM processed_messages
    │                          WHERE employee_id=? AND shift_date=? AND group_id=?
    │                          raises SkipMessage(DUPLICATE) if exists
    │
    ├── sheets_writer.enqueue  add to write buffer (non-blocking)
    │
    └── journal_success(ctx)   UPDATE messages SET status=PROCESSED → DB
                               INSERT processed_messages (dedup record) → DB

Sheets flush timer (every 5s)
    │ batchUpdate Google Sheets API
    ▼
Google Sheets cell = "1"
```

### Review Flow: Ambiguous Message

```
identify(ctx) raises NeedsReview
    │
    ▼
journal_needs_review(ctx) → DB [status=NEEDS_REVIEW, review_note="ambiguous caption"]
    │
    ▼
Admin API GET /api/v1/review     (operator polls or is notified)
    │
    ▼
Operator sets employee_id manually
    │
    ▼
Admin API POST /api/v1/review/{id}/resolve
    │ validates + writes Sheets directly
    │ updates message status=PROCESSED
    ▼
Done
```

### Key Data Flows

1. **Deduplication:** Check happens in pipeline before Sheets write. Uses DB index on `(employee_id, shift_date, group_id)`. A message is a duplicate if any PROCESSED record exists for that triple — not just the same `message_id`.
2. **Crash recovery:** On restart, query `messages WHERE status=RECEIVED AND created_at > NOW()-1hour` and re-enqueue. The `RECEIVED` status means "in queue but not yet processed" — set before enqueuing.
3. **Sheets failure isolation:** If Google Sheets API fails, the message is still journaled in PostgreSQL with status `SHEET_WRITE_PENDING`. A periodic job retries these rows independently of the main pipeline.

## Database Schema

### Core Tables

```sql
-- Employee registry
CREATE TABLE employees (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,            -- used for caption matching
    tg_user_id  BIGINT UNIQUE,            -- optional, for user-based match
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Group configuration
CREATE TABLE groups (
    id              SERIAL PRIMARY KEY,
    tg_chat_id      BIGINT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    spreadsheet_id  TEXT NOT NULL,        -- Google Sheets ID
    shift_start_hour INT DEFAULT 6,       -- time window: shift starts at 06:00
    shift_end_hour   INT DEFAULT 22,      -- messages after 22:00 belong to next day
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Employee ↔ Group assignment (which employees work in which groups)
CREATE TABLE group_employees (
    group_id    INT REFERENCES groups(id) ON DELETE CASCADE,
    employee_id INT REFERENCES employees(id) ON DELETE CASCADE,
    sheet_row   INT NOT NULL,             -- row in the shift table for this employee
    PRIMARY KEY (group_id, employee_id)
);

-- Message journal (audit log + processing state)
CREATE TABLE messages (
    id              BIGSERIAL PRIMARY KEY,
    tg_message_id   BIGINT NOT NULL,
    tg_chat_id      BIGINT NOT NULL,
    tg_user_id      BIGINT,
    tg_username     TEXT,
    caption         TEXT,
    photo_file_id   TEXT,                 -- Telegram file_id for reference
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          TEXT NOT NULL DEFAULT 'RECEIVED',
                    -- RECEIVED | PROCESSING | PROCESSED | SKIPPED | NEEDS_REVIEW | ERROR | SHEET_WRITE_PENDING
    resolved_at     TIMESTAMPTZ,
    employee_id     INT REFERENCES employees(id),
    shift_date      DATE,
    skip_reason     TEXT,                 -- why SKIPPED (DUPLICATE, NO_PHOTO, UNKNOWN_GROUP, etc.)
    error_detail    TEXT,
    review_note     TEXT,
    UNIQUE (tg_chat_id, tg_message_id)    -- dedup at ingestion level
);

-- Processed shifts (dedup guard for business rule)
CREATE TABLE processed_shifts (
    id          BIGSERIAL PRIMARY KEY,
    employee_id INT NOT NULL REFERENCES employees(id),
    group_id    INT NOT NULL REFERENCES groups(id),
    shift_date  DATE NOT NULL,
    message_id  BIGINT NOT NULL REFERENCES messages(id),
    marked_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (employee_id, group_id, shift_date)  -- the dedup key
);
```

### Index Strategy

```sql
-- Fast lookup for deduplication check (hot path in pipeline)
CREATE INDEX idx_processed_shifts_dedup ON processed_shifts (employee_id, group_id, shift_date);

-- Admin review queue
CREATE INDEX idx_messages_status ON messages (status) WHERE status IN ('NEEDS_REVIEW', 'SHEET_WRITE_PENDING');

-- Crash recovery query
CREATE INDEX idx_messages_received_at ON messages (received_at) WHERE status = 'RECEIVED';
```

### Audit Pattern Decision

Use an application-level `messages` table as the audit log rather than PostgreSQL triggers. Rationale:
- The `messages` table IS the audit log — it records every photo received, what was decided, and why.
- Trigger-based audit is appropriate when you need to capture changes to multiple tables (employee updates, config changes). For this system the primary audit need is the message processing journal, which is explicitly modeled.
- If admin config changes need auditing later, add a separate `audit_log` table with jsonb diff columns — do not complicate v1.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Telegram Bot API | Webhook via HTTPS POST, aiogram `SimpleRequestHandler` mounted on FastAPI route | Secret token header validates requests are from Telegram. Set with `bot.set_webhook(secret_token=...)` |
| Google Sheets API | gspread-asyncio, batched writes every 5s, exponential backoff on 429 | Rate limit: 300 req/min/project. One `batchUpdate` per flush covers all pending writes. Use a service account, not OAuth. |
| PostgreSQL | asyncpg driver via SQLAlchemy 2.x async session | Connection pool size: min 5, max 20. All DB calls are awaited — never call sync SQLAlchemy in async context. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| bot/ ↔ pipeline/ | `asyncio.Queue.put_nowait()` | Handler never awaits processing result. Fire-and-forget into queue. |
| pipeline/ ↔ sheets/ | `SheetsWriter.enqueue()` (non-blocking, appends to buffer list) | Decouples processing latency from Sheets API latency |
| pipeline/ ↔ db/ | Async SQLAlchemy repository calls | Each worker gets its own DB session scoped to task |
| admin/ ↔ db/ | Async SQLAlchemy repository calls | FastAPI dependency injection provides session per request |
| admin/ ↔ sheets/ | Direct write call for manual review resolution | Bypasses queue and worker — admin writes are low-frequency |

## Recommended Build Order

Build in this order — each step produces something testable before proceeding:

1. **Database layer** (`db/`) — Define models, run migrations, write repositories. This is the foundation everything else depends on. Test with direct repository calls.

2. **Processing pipeline** (`pipeline/stages/`) — Implement each stage as pure functions against the DB. No Telegram, no Sheets yet. Test with synthetic `ProcessingContext` objects. This is the core business logic.

3. **Sheets writer** (`sheets/`) — Implement the write buffer and gspread-asyncio integration. Test against a real dev spreadsheet. Validate rate-limit handling.

4. **Telegram bot** (`bot/`) + webhook mount — Wire up aiogram handlers that journal messages and enqueue them. Test with Telegram's test environment or ngrok.

5. **Admin API** (`admin/`) — FastAPI routes for CRUD and review. The processing pipeline and DB are already working, so this is just exposing them over HTTP.

6. **Integration + queue wiring** (`main.py`, `app.py`) — Assemble lifespan, start worker pool, mount routes. System is now fully operational.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| v1: <50 groups, <500 msg/day | Single process, asyncio.Queue, no external dependencies. Current design is sufficient. |
| v1 production: 200 groups, ~5k msg/day | Same single process. At ~3 msg/sec average, 8 workers with asyncio is vastly sufficient. Monitor queue depth. |
| Future: >1000 groups, >100k msg/day | Replace asyncio.Queue with Redis + arq. Run multiple worker processes. Add Redis-based dedup cache to reduce DB roundtrips. |
| Future: multi-bot | Use aiogram multibot factory pattern (separate Bot instances, same Dispatcher). One FastAPI process handles all webhooks. |

### Scaling Priorities

1. **First bottleneck: Google Sheets API rate limits.** 300 req/min/project means if writes are not batched they fail at ~5 msg/sec. The batch buffer solves this — it is the most important performance design in the system.
2. **Second bottleneck: PostgreSQL connection pool exhaustion.** With 8 workers + FastAPI handlers concurrently, set pool size to at least 20. asyncpg handles this efficiently.
3. **Third bottleneck (far future): Single-process queue capacity.** asyncio.Queue saturates around 10k msg/sec on a modern machine — not a concern for this scale.

## Anti-Patterns

### Anti-Pattern 1: Processing in the Telegram Handler

**What people do:** Call the full processing pipeline synchronously inside the aiogram message handler before returning.
**Why it's wrong:** Telegram Bot API has a 60-second timeout for webhook responses. Any slow stage (DB, Sheets API) causes timeouts, Telegram retries, and duplicate deliveries. Handler should return in <1 second.
**Do this instead:** Journal the message and enqueue it. Return immediately. Workers process asynchronously.

### Anti-Pattern 2: One Google Sheets API Call Per Message

**What people do:** `worksheet.update_cell(row, col, "1")` for every processed message.
**Why it's wrong:** At 5 msg/sec that is 300 req/min — the entire project quota. The system hits 429 errors and stalls within the first minute of load.
**Do this instead:** Batch buffer with periodic flush. One `batchUpdate` call for many cells.

### Anti-Pattern 3: Using Long-Polling in Production

**What people do:** `await dp.start_polling(bot)` — the aiogram default quick-start pattern.
**Why it's wrong:** Long-polling cannot run alongside uvicorn. It blocks the event loop or requires a separate process. Also has lower throughput and harder graceful shutdown.
**Do this instead:** Webhook via `SimpleRequestHandler` mounted as a FastAPI route. Both run on the same uvicorn event loop.

### Anti-Pattern 4: Deduplication Only by message_id

**What people do:** Check `WHERE tg_message_id = ?` before writing.
**Why it's wrong:** Message IDs are per-chat, not globally unique. More importantly, the business rule is "one shift per employee per day" — a different photo in a different message by the same employee is still a duplicate shift entry.
**Do this instead:** The dedup key is `(employee_id, group_id, shift_date)` in `processed_shifts`. Message ID uniqueness (at ingestion) is a separate concern.

### Anti-Pattern 5: Running aiogram and FastAPI with Two Event Loops

**What people do:** `asyncio.run(dp.start_polling(bot))` in one thread, uvicorn in another.
**Why it's wrong:** Two event loops in one process causes subtle bugs, shared state is unsafe, and SQLAlchemy async connections are not thread-safe across loops.
**Do this instead:** One uvicorn process, one event loop. aiogram mounts as a FastAPI route handler. Worker pool runs as asyncio tasks on the same loop. Everything shares the same event loop safely.

## Sources

- aiogram 3 webhook documentation: https://docs.aiogram.dev/en/latest/dispatcher/webhook.html
- aiogram + FastAPI integration examples: https://github.com/bralbral/fastapi_aiogram_template
- aiogram-fastapi-server package: https://pypi.org/project/aiogram-fastapi-server/
- Google Sheets API rate limits: https://developers.google.com/sheets/api/limits
- gspread-asyncio: https://gspread-asyncio.readthedocs.io/en/latest/api.html
- asyncio backpressure and worker pools: https://blog.changs.co.uk/asyncio-backpressure-processing-lots-of-tasks-in-parallel.html
- FastAPI lifespan events: https://fastapi.tiangolo.com/advanced/events/
- PostgreSQL audit logging patterns: https://medium.com/@sehban.alam/lets-build-production-ready-audit-logs-in-postgresql-7125481713d8

---
*Architecture research for: Telegram shift tracking system (ShiftTracker)*
*Researched: 2026-04-10*

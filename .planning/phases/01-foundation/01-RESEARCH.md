# Phase 1: Foundation - Research

**Researched:** 2026-04-10
**Domain:** Telegram bot ingestion pipeline, employee identification, shift date resolution, deduplication, audit log (Python/aiogram 3/SQLAlchemy 2 async/PostgreSQL)
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Employee Identification Strategy**
- Confidence ladder (checked in order):
  1. Telegram account match — user_id привязан к сотруднику в справочнике (highest confidence)
  2. Caption exact match — подпись содержит точное совпадение с ФИО/позывным/табельным номером
  3. Caption keyword match — подпись содержит ключевые слова из шаблонов идентификации группы
  4. Single-employee group fallback — если в группе привязан только один сотрудник, и фото от любого участника → этот сотрудник
  5. No match → NEEDS_REVIEW — ни один метод не сработал, отправляем на ручную проверку
- Если по подписи определяется несколько сотрудников — создаём отдельную запись для каждого
- Case-insensitive matching для подписей
- Подпись нормализуется: trim, collapse whitespace, lowercase для сравнения

**Shift Date Resolution**
- Каждая группа/объект имеет настраиваемое окно смены: `shift_start_hour` и `shift_end_hour`
- Дефолтное окно: 06:00 — 22:00 (дневная смена)
- Для ночных смен (например 22:00 — 06:00): фото в 01:30 относится к предыдущему дню
- Алгоритм: `resolve_shift_date(message_datetime, shift_start_hour, shift_end_hour)` — если время сообщения < shift_start_hour и ночная смена активна, дата = вчера
- Фото за пределами ±2 часов от окна смены → NEEDS_REVIEW с причиной "outside_time_window"
- Часовой пояс: UTC+3 (Москва) по умолчанию, настраиваемый для каждой группы

**Edge Case Handling**
- Фото без подписи: если Telegram user_id привязан к сотруднику → обработать; иначе → NEEDS_REVIEW с причиной "no_caption_no_account_match"
- Несколько фото подряд от одного сотрудника за одну смену: первое принимается, остальные логируются как DUPLICATE_SAME_SHIFT
- Фото-документ (file, не photo): игнорировать, обрабатываем только сжатые фото (photo object в Telegram API)
- Пересланные сообщения: игнорировать (forward_from != null), т.к. это не факт заступления
- Отредактированное сообщение: не переобрабатывать (update_id уже обработан)
- Удалённое сообщение: не откатывать отметку, но логировать событие удаления
- Нерелевантные фото (мемы, скриншоты и т.д.): на уровне v1 не фильтруем по содержимому

**Message Processing Pipeline**
- Ingestion → Dedup (update_id) → Filter (has photo?) → Identify (employee) → Resolve Date → Business Dedup (employee+date) → Write to DB → Queue for Sheets (Phase 2)
- asyncio.Queue с 8 worker coroutines для параллельной обработки
- Bounded queue (maxsize=500) для backpressure
- Все этапы логируются в processing_log с таймстемпами

**Database Schema Approach**
- `employees` — справочник сотрудников (name, telegram_user_id, employee_code)
- `telegram_groups` — подключённые группы (chat_id, name, shift_start_hour, shift_end_hour, timezone)
- `group_employees` — привязка сотрудников к группам (many-to-many + sheet_row для Phase 2)
- `caption_rules` — шаблоны подписей для групп (group_id, pattern, employee_id)
- `shift_records` — записи о сменах (employee_id, shift_date, status, source_message_id, source_link)
- `processing_log` — журнал обработки (message_id, update_id, group_id, status, reason, employee_id, timestamps)
- `processed_updates` — дедупликация по update_id (UNIQUE constraint)
- Alembic для миграций
- Индексы: (employee_id, shift_date) UNIQUE на shift_records; update_id UNIQUE на processed_updates

**Bot Configuration**
- Polling mode для разработки, webhook-ready architecture для продакшена
- Privacy mode must be OFF (BotFather → /setprivacy → Disable)
- Бот должен быть добавлен в группу как участник (не обязательно админ, но privacy mode отключён)
- Обработка migrate_to_chat_id: автоматическое обновление chat_id в telegram_groups
- pydantic-settings для конфигурации (BOT_TOKEN, DATABASE_URL, etc.)

**System Architecture**
- Single asyncio process — aiogram 3 + FastAPI sharing one event loop under uvicorn
- PostgreSQL is source of truth; Google Sheets is display layer only
- Bot API only (not MTProto); bots must be added to groups with message read rights
- Inbox-pattern deduplication on update_id before all business logic
- shift_records table must have a `sheet_write_status` column (PENDING/WRITTEN/ERROR) for Phase 2 consumption
- processing_log must be queryable by Phase 3 admin UI
- Бот не должен отвечать в группы (silent processing) — никаких сообщений в чат
- ON CONFLICT DO NOTHING на update_id для at-least-once delivery

### Claude's Discretion
- Exact SQLAlchemy model field types and constraints
- Alembic migration naming conventions
- Logging format and levels
- Project directory structure (src layout)
- Test framework choice (pytest recommended)
- Error retry strategies for Telegram API calls

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| TGRAM-01 | Бот принимает фотографии с подписями из подключенных Telegram-групп в реальном времени | aiogram 3 Router with photo filter + `F.photo` filter; privacy mode must be OFF |
| TGRAM-02 | Бот фильтрует нерелевантные сообщения (без фото) и не обрабатывает их | aiogram `F.photo` filter + forward check (`F.forward_from` / `F.forward_from_chat`); document files are separate content type |
| TGRAM-03 | Повторная обработка одного и того же сообщения не создает дублей (дедупликация по update_id) | Inbox pattern: `INSERT INTO processed_updates (update_id) VALUES ($1) ON CONFLICT DO NOTHING`; check before business logic |
| TGRAM-04 | Бот корректно обрабатывает миграцию группы в супергруппу (migrate_to_chat_id) | aiogram `F.migrate_to_chat_id` filter; update `telegram_groups.chat_id` atomically in DB |
| TGRAM-05 | При пиковых нагрузках сообщения ставятся в очередь без потери | `asyncio.Queue(maxsize=500)` with 8 workers; journal message as RECEIVED in DB before enqueuing so it survives restarts |
| IDENT-01 | Система определяет сотрудника по привязке Telegram-аккаунта к записи в справочнике | `employees.telegram_user_id` lookup; highest-confidence tier; no caption needed |
| IDENT-02 | Система определяет сотрудника по шаблону/ключевым словам в подписи к фото | `caption_rules` table per group; normalize caption (trim/lowercase/collapse spaces); exact then keyword match |
| IDENT-03 | Система использует привязку группы к ограниченному перечню сотрудников как fallback | `group_employees` table; if exactly one employee → use as fallback at LOW confidence |
| IDENT-04 | Если сотрудник не определен однозначно, сообщение отправляется на ручную проверку | Pipeline raises `NeedsReview` exception; worker catches and writes status=NEEDS_REVIEW with reason |
| IDENT-05 | Если в одном сообщении указано несколько сотрудников, каждый обрабатывается отдельно | `identify()` stage returns a list; worker loops and creates separate `shift_records` for each |
| SHIFT-01 | Система определяет дату смены по фактическому времени публикации сообщения | `message.date` (UTC unix timestamp) → convert to group timezone → apply shift window |
| SHIFT-02 | Для ночных смен система корректно разрешает дату через настраиваемое окно (date_offset) | `resolve_shift_date(dt, shift_start_hour, shift_end_hour, tz)` — if hour < shift_start_hour and it's a night shift window → yesterday |
| SHIFT-03 | Временные окна подтверждения смены настраиваются отдельно для каждой группы/объекта | `telegram_groups.shift_start_hour`, `shift_end_hour`, `timezone` columns; per-group overrides |
| SHIFT-04 | Фото, отправленное за пределами допустимого окна, отправляется на ручную проверку | ±2h tolerance window around shift boundaries; outside → NEEDS_REVIEW with reason "outside_time_window" |
| JRNL-01 | Каждое обработанное сообщение фиксируется в журнале со статусом | `processing_log` table; every message gets exactly one log entry; status enum: RECEIVED/ACCEPTED/DUPLICATE_SAME_SHIFT/NEEDS_REVIEW/SKIPPED/ERROR |
| JRNL-02 | Для отклоненных сообщений сохраняется причина отклонения | `processing_log.reason` column; populated for all non-ACCEPTED outcomes |
| JRNL-03 | Оператор может открыть первоисточник (ссылка на сообщение в Telegram) | `processing_log.source_link` = `https://t.me/c/{chat_id_abs}/{message_id}`; Phase 3 renders as link |
| JRNL-04 | Доступна история автоматических изменений по каждому сотруднику и каждой дате | `processing_log` indexed by (employee_id, shift_date); queryable by Phase 3 admin UI |
</phase_requirements>

---

## Summary

Phase 1 builds the complete Telegram-to-PostgreSQL pipeline: bot receives photo messages, the processing pipeline identifies employees, resolves shift dates, deduplicates, writes `shift_records`, and logs every outcome in `processing_log`. There is no UI and no Google Sheets interaction in this phase — both are deferred to Phases 2 and 3.

The architecture is a single Python process running aiogram 3 and FastAPI on the same uvicorn event loop. Incoming Telegram updates are immediately journaled to PostgreSQL (status=RECEIVED) and placed onto a bounded `asyncio.Queue`. Eight worker coroutines drain the queue, each running the message through sequential pipeline stages: update-level dedup → filter → identify → shift date → business dedup → write shift_record → update log status. Every exception path results in a log entry with a specific reason rather than silent discard.

The most critical correctness requirements for this phase are: (1) the inbox-pattern dedup on `update_id` must fire before any business logic to handle Telegram's at-least-once delivery; (2) `resolve_shift_date` must handle midnight crossover correctly for night-shift groups; (3) privacy mode must be disabled in BotFather before any group integration. The `shift_records.sheet_write_status` and `processing_log` tables are designed now to satisfy Phase 2 and Phase 3 consumers without schema changes.

**Primary recommendation:** Build bottom-up — DB models and Alembic migration first, then pipeline stages as isolated pure async functions, then wire aiogram handlers and worker pool last. Each layer is testable before the next one is built.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.11+ | Runtime | aiogram requires 3.10+; 3.11 has best performance improvements without bleeding-edge risk |
| aiogram | 3.27.0 | Telegram Bot API framework | De-facto standard for async Python Telegram bots; native asyncio, Router/Filter/FSM system |
| FastAPI | 0.115.x | Webhook endpoint + future admin API | Async-native; shares same event loop as aiogram; Pydantic v2 validation built in |
| PostgreSQL | 16.x | Persistent storage | ACID; UNIQUE constraints for dedup; handles concurrent writes from many groups |
| SQLAlchemy | 2.0.49 | ORM + async query interface | Full native asyncio in v2.0; pairs with asyncpg and Alembic |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Fastest async driver; required by `postgresql+asyncpg://` dialect |
| Alembic | 1.18.4 | Database migrations | Official SQLAlchemy migration tool; async template via `alembic init -t async` |
| pydantic-settings | 2.x | Configuration from env vars | Validates BOT_TOKEN, DATABASE_URL etc. at startup; reads .env file directly |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uvicorn | 0.29.x | ASGI server | Always — runs FastAPI + aiogram webhook on one event loop |
| loguru | 0.7.x | Structured logging | Async-safe via `enqueue=True`; simpler than stdlib logging for this project scale |
| pytest | latest | Test runner | Unit tests for pipeline stages, DB repositories |
| pytest-asyncio | latest | Async test support | Required for testing async functions and SQLAlchemy async sessions |
| pytz / zoneinfo | stdlib 3.9+ | Timezone handling | Use stdlib `zoneinfo` (Python 3.9+) for UTC+3 conversion; no extra install needed |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQLAlchemy 2.0 async | Tortoise ORM | Tortoise simpler for pure async CRUD but Alembic is native to SQLAlchemy; non-trivial queries needed |
| asyncio.Queue (in-process) | Celery + Redis | Celery is overkill; async queue handles 5k msg/day on one process with zero extra infra |
| aiogram polling (dev) | ngrok + webhook | Polling is simpler for local dev; no public URL required; switch to webhook for production |
| loguru | structlog | structlog better for high-volume log aggregation pipelines; loguru simpler for this scale |

**Installation:**
```bash
# Core
pip install aiogram==3.27.0 fastapi[standard] uvicorn[standard]
# Database
pip install "sqlalchemy[asyncio]==2.0.49" asyncpg==0.31.0 alembic==1.18.4
# Configuration and utilities
pip install pydantic-settings loguru
# Dev/test
pip install pytest pytest-asyncio ruff
```

---

## Architecture Patterns

### Recommended Project Structure

```
shifttracker/
├── main.py                    # Entry point: build app, run uvicorn (or polling)
├── app.py                     # FastAPI app factory, lifespan context manager
├── config.py                  # pydantic-settings: BOT_TOKEN, DATABASE_URL, etc.
│
├── bot/
│   ├── router.py              # aiogram Router: photo handler, migration handler
│   └── filters.py             # Custom filters: is_photo, not_forwarded, group_registered
│
├── pipeline/
│   ├── queue.py               # Module-level asyncio.Queue(maxsize=500)
│   ├── worker.py              # Worker coroutine + pool start/stop
│   ├── context.py             # ProcessingContext dataclass
│   └── stages/
│       ├── dedup_update.py    # Stage 1: update_id inbox dedup (ON CONFLICT DO NOTHING)
│       ├── filter_message.py  # Stage 2: has photo? not forwarded? group registered?
│       ├── identify.py        # Stage 3: confidence ladder → employee_id list
│       ├── shift_date.py      # Stage 4: resolve_shift_date() with timezone + window
│       ├── dedup_shift.py     # Stage 5: business dedup (employee_id, shift_date) UNIQUE
│       └── write_record.py    # Stage 6: insert shift_records + update processing_log
│
├── db/
│   ├── engine.py              # async_engine + async_sessionmaker (module-level singleton)
│   ├── models.py              # SQLAlchemy ORM models (all tables)
│   ├── repositories/
│   │   ├── employees.py       # lookup by tg_user_id, by name/code
│   │   ├── groups.py          # lookup by chat_id, update chat_id on migration
│   │   ├── caption_rules.py   # fetch rules for group_id
│   │   ├── shift_records.py   # insert with UNIQUE conflict handling
│   │   └── processing_log.py  # insert / update log entries
│   └── migrations/            # alembic: env.py (async), versions/
│
└── tests/
    ├── unit/
    │   ├── test_identify.py
    │   ├── test_shift_date.py
    │   └── test_dedup.py
    └── integration/
        └── test_pipeline.py
```

### Pattern 1: Inbox Dedup — update_id ON CONFLICT DO NOTHING

**What:** Every incoming Telegram update is stored in `processed_updates` before business logic runs. If the update_id already exists, the entire message is skipped.
**When to use:** Always — Telegram guarantees at-least-once delivery. Webhooks are retried on non-200. This is the first thing that runs.

```python
# db/repositories/processing_log.py
from sqlalchemy.dialects.postgresql import insert as pg_insert

async def try_claim_update(session: AsyncSession, update_id: int) -> bool:
    """Returns True if this update_id is new and was claimed, False if duplicate."""
    stmt = pg_insert(ProcessedUpdate).values(update_id=update_id)
    stmt = stmt.on_conflict_do_nothing(index_elements=["update_id"])
    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount > 0
```

### Pattern 2: Stage-Based Processing Pipeline

**What:** Each pipeline stage is a pure `async def` that takes and returns a `ProcessingContext` dataclass. Stages signal non-happy-path outcomes by raising typed exceptions.
**When to use:** Always — enables isolated unit testing, clear separation of concerns, and predictable exception flow.

```python
# pipeline/context.py
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

@dataclass
class ProcessingContext:
    update_id: int
    message_id: int
    chat_id: int
    user_id: Optional[int]
    caption: Optional[str]
    photo_file_id: str
    received_at: datetime
    # Populated by stages:
    employee_ids: list[int] = field(default_factory=list)
    shift_date: Optional[date] = None
    log_entry_id: Optional[int] = None

class NeedsReview(Exception):
    def __init__(self, reason: str):
        self.reason = reason

class SkipMessage(Exception):
    def __init__(self, reason: str):
        self.reason = reason
```

```python
# pipeline/worker.py
async def worker(queue: asyncio.Queue, session_factory):
    while True:
        message = await queue.get()
        try:
            ctx = build_context(message)
            async with session_factory() as session:
                if not await try_claim_update(session, ctx.update_id):
                    raise SkipMessage("duplicate_update_id")
                ctx = await filter_message(ctx, session)
                ctx = await identify(ctx, session)
                for employee_id in ctx.employee_ids:
                    emp_ctx = replace(ctx, employee_ids=[employee_id])
                    emp_ctx = await resolve_shift_date(emp_ctx, session)
                    emp_ctx = await dedup_shift(emp_ctx, session)
                    await write_shift_record(emp_ctx, session)
        except NeedsReview as e:
            await write_needs_review(ctx, reason=e.reason, session_factory=session_factory)
        except SkipMessage as e:
            await write_skip_log(ctx, reason=e.reason, session_factory=session_factory)
        except Exception as e:
            await write_error_log(ctx, error=str(e), session_factory=session_factory)
        finally:
            queue.task_done()
```

### Pattern 3: Shift Date Resolution

**What:** `resolve_shift_date` converts a UTC datetime to a logical shift date considering group timezone and shift window.
**When to use:** Always for every message — raw timestamp is never stored as shift_date.

```python
# pipeline/stages/shift_date.py
from zoneinfo import ZoneInfo
from datetime import date, timedelta

def resolve_shift_date(
    message_utc: datetime,
    shift_start_hour: int,  # e.g. 6 for day shift, 22 for night shift
    shift_end_hour: int,    # e.g. 22 for day shift, 6 for night shift
    timezone: str = "Europe/Moscow",
) -> date:
    """
    Resolve the logical shift date.
    Night shift example: start=22, end=6
      - Photo at 23:45 Tuesday → Tuesday (shift started Tuesday)
      - Photo at 01:30 Wednesday → Tuesday (before shift_end_hour, belongs to Tuesday's night shift)
    Day shift example: start=6, end=22
      - Photo at 14:00 → today's date
    """
    local_dt = message_utc.astimezone(ZoneInfo(timezone))
    local_hour = local_dt.hour
    local_date = local_dt.date()

    is_night_shift = shift_start_hour > shift_end_hour  # wraps midnight

    if is_night_shift and local_hour < shift_end_hour:
        # Early morning hours belong to the previous calendar day's shift
        return local_date - timedelta(days=1)
    return local_date


def is_within_shift_window(
    message_utc: datetime,
    shift_start_hour: int,
    shift_end_hour: int,
    timezone: str = "Europe/Moscow",
    tolerance_hours: int = 2,
) -> bool:
    """Returns True if message time is within the shift window ± tolerance."""
    local_dt = message_utc.astimezone(ZoneInfo(timezone))
    local_hour = local_dt.hour
    is_night_shift = shift_start_hour > shift_end_hour

    if is_night_shift:
        # Window: [start-tol, 24) union [0, end+tol)
        in_window = (
            local_hour >= (shift_start_hour - tolerance_hours)
            or local_hour < (shift_end_hour + tolerance_hours)
        )
    else:
        in_window = (
            (shift_start_hour - tolerance_hours) <= local_hour < (shift_end_hour + tolerance_hours)
        )
    return in_window
```

### Pattern 4: Employee Identification Confidence Ladder

**What:** `identify()` stage runs four checks in order. Returns list of employee_ids (can be multiple if caption matches several employees).
**When to use:** Always — determines shift attribution.

```python
# pipeline/stages/identify.py

async def identify(ctx: ProcessingContext, session: AsyncSession) -> ProcessingContext:
    caption_normalized = normalize_caption(ctx.caption) if ctx.caption else None

    # Tier 1: Telegram user_id exact match (highest confidence)
    if ctx.user_id:
        employee = await employees_repo.get_by_tg_user_id(session, ctx.user_id, ctx.chat_id)
        if employee:
            return replace(ctx, employee_ids=[employee.id])

    # Tier 2: Caption exact match against employee names / codes
    if caption_normalized:
        matches = await employees_repo.find_by_exact_caption(session, caption_normalized, ctx.chat_id)
        if matches:
            return replace(ctx, employee_ids=[e.id for e in matches])

    # Tier 3: Caption keyword match via caption_rules table
    if caption_normalized:
        matches = await caption_rules_repo.find_matches(session, caption_normalized, ctx.chat_id)
        if matches:
            return replace(ctx, employee_ids=[e.id for e in matches])

    # Tier 4: Single-employee group fallback
    group_employees = await groups_repo.get_employees(session, ctx.chat_id)
    if len(group_employees) == 1:
        # LOW confidence — flag for review but still create record
        raise NeedsReview(reason="single_employee_group_fallback")

    # No match
    raise NeedsReview(reason="no_employee_match")


def normalize_caption(caption: str) -> str:
    """Trim, collapse whitespace, lowercase."""
    return " ".join(caption.strip().lower().split())
```

### Pattern 5: aiogram Router — Photo Handler

**What:** Minimal handler that journals and enqueues. Returns immediately without awaiting processing.
**When to use:** Always — Telegram has 60s webhook timeout; processing must be async.

```python
# bot/router.py
from aiogram import Router, F
from aiogram.types import Message

router = Router()

@router.message(F.photo, ~F.forward_date)  # has photo, not forwarded
async def handle_photo(message: Message, queue: asyncio.Queue, session_factory) -> None:
    # Journal as RECEIVED immediately (crash recovery: restart can re-enqueue RECEIVED records)
    async with session_factory() as session:
        await processing_log_repo.insert_received(session, message)
    # Enqueue for async processing
    try:
        queue.put_nowait(message)
    except asyncio.QueueFull:
        async with session_factory() as session:
            await processing_log_repo.update_status(session, message.message_id, "QUEUE_FULL")

@router.message(F.migrate_to_chat_id)
async def handle_migration(message: Message, session_factory) -> None:
    old_id = message.chat.id
    new_id = message.migrate_to_chat_id
    async with session_factory() as session:
        await groups_repo.update_chat_id(session, old_id, new_id)
```

### Pattern 6: FastAPI Lifespan — Shared Event Loop

**What:** aiogram and FastAPI share one uvicorn event loop. Worker pool and polling mode both start/stop in the FastAPI lifespan.
**When to use:** Always — two event loops in one process causes subtle SQLAlchemy bugs.

```python
# app.py
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start worker pool
    workers = await start_worker_pool(message_queue, n=settings.worker_count)
    # Start polling (dev) or set webhook (prod)
    if settings.use_polling:
        poll_task = asyncio.create_task(dp.start_polling(bot))
    else:
        await bot.set_webhook(url=settings.webhook_url)
    yield
    # Shutdown
    for w in workers:
        w.cancel()
    await message_queue.join()
    if settings.use_polling:
        poll_task.cancel()
    else:
        await bot.delete_webhook()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)
```

### Pattern 7: SQLAlchemy Async Session Factory

**What:** Module-level engine and session factory. Never create a new engine per request.
**When to use:** Always.

```python
# db/engine.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(
    settings.database_url,  # postgresql+asyncpg://...
    pool_size=10,
    max_overflow=10,
    echo=False,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

### Anti-Patterns to Avoid

- **Processing in the Telegram handler:** Any slow await (DB, Sheets) inside the handler will cause Telegram webhook timeouts (60s limit) → retries → duplicates. Handler must journal + enqueue only.
- **Two event loops:** Running `asyncio.run(dp.start_polling())` in a thread alongside uvicorn causes SQLAlchemy async connection issues. Use one loop.
- **Dedup only by message_id:** Business rule is one shift per (employee_id, shift_date) — a second photo from the same employee on the same day is a business duplicate even if it has a different message_id.
- **Wall-clock date as shift_date:** Night shift photos at 01:30 get assigned to the wrong calendar day. Always run through `resolve_shift_date()`.
- **drop_pending_updates=True on startup:** Discards up to 24 hours of Telegram updates during downtime. Fatal for attendance tracking. Never use.
- **Blocking calls in async context:** `psycopg2`, synchronous gspread without executor, `time.sleep()` — all block the event loop under load.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async PostgreSQL access | Custom connection manager | SQLAlchemy 2.0 async + asyncpg | Connection pooling, prepared statements, transaction management are non-trivial |
| Database migrations | `create_all()` or manual ALTER TABLE | Alembic with async template | No upgrade path from create_all; Alembic handles rollbacks, multi-step migrations |
| Telegram update parsing | Raw HTTP POST parsing | aiogram 3 | Update schema has 60+ fields; aiogram handles parsing, retries, webhook secret validation |
| Configuration validation | Custom env parsing | pydantic-settings | Type coercion, required field validation, .env file loading for free |
| Timezone conversion | Manual UTC offset math | stdlib `zoneinfo` (Python 3.9+) | DST transitions, historical offset changes handled correctly |
| Unique constraint dedup | Application-level check-then-insert | PostgreSQL UNIQUE + ON CONFLICT DO NOTHING | Race conditions in concurrent workers make application-level checks unsafe |

**Key insight:** The deduplication correctness in a concurrent async worker pool requires database-level UNIQUE constraints. Any check-then-insert pattern at the application level has a race window between the check and the insert.

---

## Common Pitfalls

### Pitfall 1: Bot Privacy Mode Silently Blocks All Photos

**What goes wrong:** Bot added to groups, no errors, zero messages received. Privacy mode is ON by default — bots only see messages directed at them (@mentions, commands, replies).
**Why it happens:** Developers test in private chats or as group admin (admins bypass privacy mode). The issue is invisible until real deployment.
**How to avoid:** Execute `BotFather → /setprivacy → Disable` BEFORE adding the bot to any group. After changing the setting, remove and re-add the bot from every existing group.
**Warning signs:** Bot logs show updates from its own commands but never from plain photo messages in groups.

### Pitfall 2: Midnight Crossover Assigns Night Shift to Wrong Date

**What goes wrong:** Guard sends check-in photo at 23:50. System uses `datetime.now().date()` = Tuesday. Supervisor's night shift runs Monday 22:00–Tuesday 06:00. The mark appears under Tuesday, but supervisor expects it under Monday.
**Why it happens:** Raw timestamp date is used directly as shift date without considering shift window configuration.
**How to avoid:** Always use `resolve_shift_date(message_utc, shift_start_hour, shift_end_hour, timezone)`. Store the *resolved* date, never derive it from raw timestamp at query time.
**Warning signs:** Night-shift guards showing absent in the column supervisors expect; duplicate entries in adjacent date columns.

### Pitfall 3: Telegram At-Least-Once Delivery Creates Duplicate Records

**What goes wrong:** Bot restarts mid-delivery; Telegram retries the webhook; same update_id processed twice. Results in two shift_records for one employee on one day, or `(employee_id, shift_date)` UNIQUE violation noise in logs.
**Why it happens:** Telegram guarantees at-least-once, not exactly-once. Webhooks are retried on non-200. Polling with unperisted offset re-delivers on crash.
**How to avoid:** Inbox pattern — `INSERT INTO processed_updates (update_id) ON CONFLICT DO NOTHING` returns rowcount=0 for duplicates. Skip all processing if rowcount=0. This must be the very first DB operation, before any business logic.
**Warning signs:** Duplicate rows with same update_id in processing_log; `(employee_id, shift_date)` UNIQUE violations in shift_records table.

### Pitfall 4: Group Migration Breaks chat_id References

**What goes wrong:** A regular group is promoted to a supergroup. chat_id changes from positive to negative `-100XXXXXXXXXX`. All DB rows pointing to the old chat_id become orphaned. Bot stops receiving messages from that group silently.
**Why it happens:** The `migrate_to_chat_id` service message is sent once and dropped if no handler exists.
**How to avoid:** Implement `@router.message(F.migrate_to_chat_id)` handler that atomically updates `telegram_groups.chat_id` from old to new value.
**Warning signs:** A previously active group suddenly produces zero records. Bot API returns error with `migrate_to_chat_id` field.

### Pitfall 5: QueueFull Drops Messages Without a Journal Entry

**What goes wrong:** 500-message backpressure limit is hit during a burst. `queue.put_nowait()` raises `QueueFull`. Message is lost with no DB record.
**Why it happens:** Message is journaled AFTER the queue put rather than BEFORE.
**How to avoid:** Write to `processing_log` with status=RECEIVED *before* calling `queue.put_nowait()`. If QueueFull is raised after journaling, update the log entry to status=QUEUE_FULL. On restart, re-enqueue all RECEIVED-status log entries.
**Warning signs:** Employee reports sending a photo; no log entry exists at all for that message.

### Pitfall 6: Caption Match Without Normalization Causes False Negatives

**What goes wrong:** Employee writes "  Иванов  " (extra spaces) or "иванов" (lowercase). Exact string match against the registry fails. Message goes to NEEDS_REVIEW even though the guard's name is clearly in the caption.
**Why it happens:** Caption text arrives verbatim from Telegram; registry entries may use different casing/spacing conventions.
**How to avoid:** Always normalize before matching: `caption.strip().lower()` and collapse internal whitespace via `" ".join(caption.split())`. Apply same normalization to registry entries at lookup time (or store pre-normalized aliases).

### Pitfall 7: Forwarded Messages Incorrectly Recorded as Check-ins

**What goes wrong:** Guard forwards someone else's photo from another chat. Bot identifies the employee from the caption and creates a shift record for a different day/employee.
**Why it happens:** No check for `message.forward_date` or `message.forward_from` before processing.
**How to avoid:** Filter out forwarded messages at the bot handler level using aiogram filter `~F.forward_date`. Log them as SKIPPED with reason "forwarded_message".

---

## Code Examples

Verified patterns from official sources and project research:

### Alembic Async Init and env.py Pattern

```bash
# Source: Alembic official cookbook — async migrations
alembic init -t async alembic
```

Generated `alembic/env.py` uses `async_engine_from_config` and runs migrations via `run_sync`. Individual migration files remain synchronous (`op.create_table`, `op.add_column` etc.) — this is correct and expected.

### SQLAlchemy ORM Models (Core Tables for Phase 1)

```python
# db/models.py
from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey,
    Integer, String, Text, UniqueConstraint, func
)
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    telegram_user_id = Column(BigInteger, unique=True, nullable=True)
    employee_code = Column(String(50), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class TelegramGroup(Base):
    __tablename__ = "telegram_groups"
    id = Column(Integer, primary_key=True)
    chat_id = Column(BigInteger, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    shift_start_hour = Column(Integer, default=6, nullable=False)
    shift_end_hour = Column(Integer, default=22, nullable=False)
    timezone = Column(String(50), default="Europe/Moscow", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class GroupEmployee(Base):
    __tablename__ = "group_employees"
    group_id = Column(Integer, ForeignKey("telegram_groups.id", ondelete="CASCADE"), primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True)
    sheet_row = Column(Integer, nullable=True)  # Phase 2 consumer field

class CaptionRule(Base):
    __tablename__ = "caption_rules"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("telegram_groups.id", ondelete="CASCADE"), nullable=False)
    pattern = Column(Text, nullable=False)  # normalized keyword or phrase
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)

class ShiftRecord(Base):
    __tablename__ = "shift_records"
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    group_id = Column(Integer, ForeignKey("telegram_groups.id"), nullable=False)
    shift_date = Column(Date, nullable=False)
    status = Column(String(30), nullable=False, default="ACCEPTED")
    source_message_id = Column(BigInteger, nullable=True)
    source_link = Column(Text, nullable=True)
    sheet_write_status = Column(String(20), default="PENDING", nullable=False)  # Phase 2
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("employee_id", "group_id", "shift_date", name="uq_shift_per_employee_day"),
    )

class ProcessingLog(Base):
    __tablename__ = "processing_log"
    id = Column(Integer, primary_key=True)
    update_id = Column(BigInteger, nullable=False)
    message_id = Column(BigInteger, nullable=False)
    group_id = Column(Integer, ForeignKey("telegram_groups.id"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    status = Column(String(30), nullable=False)
    # RECEIVED / ACCEPTED / DUPLICATE_SAME_SHIFT / NEEDS_REVIEW / SKIPPED / ERROR / QUEUE_FULL
    reason = Column(Text, nullable=True)
    source_link = Column(Text, nullable=True)
    shift_date = Column(Date, nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    raw_caption = Column(Text, nullable=True)

class ProcessedUpdate(Base):
    __tablename__ = "processed_updates"
    update_id = Column(BigInteger, primary_key=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())
```

### aiogram Photo Filter with Forward Check

```python
# bot/router.py
from aiogram import Router, F
from aiogram.types import Message

router = Router()

# Only process: has photo, is NOT a forwarded message, is NOT an edited message re-delivery
@router.message(F.photo, ~F.forward_date, ~F.forward_from, ~F.forward_from_chat)
async def handle_photo(message: Message) -> None:
    ...

@router.message(F.migrate_to_chat_id)
async def handle_group_migration(message: Message) -> None:
    ...
```

### pydantic-settings Configuration

```python
# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    bot_token: str
    database_url: str  # postgresql+asyncpg://user:pass@host/db
    worker_count: int = 8
    queue_maxsize: int = 500
    use_polling: bool = True  # False in production
    webhook_url: str = ""
    webhook_secret: str = ""
    default_timezone: str = "Europe/Moscow"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| python-telegram-bot (sync) | aiogram 3 (async) | aiogram 3.0 released 2023 | Full asyncio native; no blocking in event loop |
| SQLAlchemy 1.x sync | SQLAlchemy 2.0 async | 2.0 released Jan 2023 | `AsyncSession`, `async_sessionmaker` native; no greenlets needed |
| pytz for timezones | stdlib `zoneinfo` | Python 3.9 (2020) | No extra install; correct DST handling; use `ZoneInfo("Europe/Moscow")` |
| `create_all()` for schema | Alembic migrations | Best practice; tooling stable since 2014 | Schema evolution without data loss; upgrade/downgrade paths |
| Long-polling in production | Webhook via FastAPI lifespan | aiogram 3 SimpleRequestHandler | Single event loop; composable with FastAPI routes; cleaner shutdown |
| Celery for background tasks | asyncio.Queue + worker tasks | asyncio maturity (~2018+) | Zero additional infra for this message volume; simpler deployment |

**Deprecated/outdated:**
- `python-telegram-bot` sync API: fights asyncio, not recommended for this stack
- `psycopg2`: synchronous driver, blocks event loop in async context; use asyncpg
- `aiogram 2.x`: incompatible Router/Filter API; aiogram 3.x is a full rewrite
- `oauth2client` for Google auth: deprecated in favor of `google-auth`

---

## Open Questions

1. **Exact `caption_rules` matching semantics**
   - What we know: Pattern column stores a normalized keyword or phrase; case-insensitive matching against normalized caption
   - What's unclear: Whether patterns are exact substring, regex, or word-boundary match; regex adds power but complexity
   - Recommendation: Start with case-insensitive substring contains (simplest, covers most cases); add regex support in v1.x if operators report false positives

2. **Behavior when group has no registered employees at all**
   - What we know: Single-employee fallback handles groups with exactly one employee; no match → NEEDS_REVIEW
   - What's unclear: Should receiving a photo from an entirely unconfigured group (not in telegram_groups table) raise a warning to operators or silently skip?
   - Recommendation: Log as SKIPPED with reason "group_not_registered"; do not raise errors in processing loop

3. **Performance of employee registry lookups under concurrent workers**
   - What we know: 8 workers; each queries DB for employee match on every message; PITFALLS.md warns about cache miss under > 50 concurrent messages
   - What's unclear: Whether in-memory caching of the employee registry is needed in Phase 1 or can be deferred
   - Recommendation: Defer caching to Phase 1.x; PostgreSQL connection pool of 10 is sufficient for v1 traffic; add Redis cache only when DB latency spikes are observed

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (latest stable) |
| Config file | `pytest.ini` or `pyproject.toml [tool.pytest.ini_options]` — Wave 0 creates this |
| Quick run command | `pytest tests/unit/ -x -q` |
| Full suite command | `pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TGRAM-01 | Bot receives photo messages from groups | integration | `pytest tests/integration/test_bot_handler.py -x` | ❌ Wave 0 |
| TGRAM-02 | Forwards filtered; documents filtered; non-photo filtered | unit | `pytest tests/unit/test_filter_message.py -x` | ❌ Wave 0 |
| TGRAM-03 | Duplicate update_id returns rowcount=0, no business logic runs | unit | `pytest tests/unit/test_dedup_update.py -x` | ❌ Wave 0 |
| TGRAM-04 | migrate_to_chat_id updates telegram_groups.chat_id | unit | `pytest tests/unit/test_migration_handler.py -x` | ❌ Wave 0 |
| TGRAM-05 | QueueFull handled; pre-journal ensures no silent loss | unit | `pytest tests/unit/test_worker_queue.py -x` | ❌ Wave 0 |
| IDENT-01 | tg_user_id match returns correct employee | unit | `pytest tests/unit/test_identify.py::test_account_match -x` | ❌ Wave 0 |
| IDENT-02 | Caption exact match and keyword match | unit | `pytest tests/unit/test_identify.py::test_caption_match -x` | ❌ Wave 0 |
| IDENT-03 | Single-employee group fallback → NeedsReview | unit | `pytest tests/unit/test_identify.py::test_single_employee_fallback -x` | ❌ Wave 0 |
| IDENT-04 | No match → NeedsReview with correct reason | unit | `pytest tests/unit/test_identify.py::test_no_match -x` | ❌ Wave 0 |
| IDENT-05 | Multi-employee caption creates separate records | unit | `pytest tests/unit/test_identify.py::test_multi_employee -x` | ❌ Wave 0 |
| SHIFT-01 | Day shift: message time → correct calendar date | unit | `pytest tests/unit/test_shift_date.py::test_day_shift -x` | ❌ Wave 0 |
| SHIFT-02 | Night shift: 23:50 → same day; 01:30 → previous day | unit | `pytest tests/unit/test_shift_date.py::test_night_shift_crossover -x` | ❌ Wave 0 |
| SHIFT-03 | Per-group shift_start_hour/shift_end_hour used | unit | `pytest tests/unit/test_shift_date.py::test_per_group_config -x` | ❌ Wave 0 |
| SHIFT-04 | Outside ±2h window → NeedsReview "outside_time_window" | unit | `pytest tests/unit/test_shift_date.py::test_outside_window -x` | ❌ Wave 0 |
| JRNL-01 | Every message produces exactly one processing_log entry | integration | `pytest tests/integration/test_pipeline.py::test_log_always_created -x` | ❌ Wave 0 |
| JRNL-02 | Rejected messages have non-null reason in log | unit | `pytest tests/unit/test_processing_log.py::test_rejection_reason -x` | ❌ Wave 0 |
| JRNL-03 | source_link format: `https://t.me/c/{abs_chat_id}/{msg_id}` | unit | `pytest tests/unit/test_processing_log.py::test_source_link_format -x` | ❌ Wave 0 |
| JRNL-04 | processing_log queryable by (employee_id, shift_date) | integration | `pytest tests/integration/test_processing_log.py::test_query_by_employee_date -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/unit/ -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `pytest.ini` — configure `asyncio_mode = "auto"` and testpaths
- [ ] `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`
- [ ] `tests/conftest.py` — async DB session fixtures, mock aiogram Message factory
- [ ] `tests/unit/test_shift_date.py` — covers SHIFT-01, SHIFT-02, SHIFT-03, SHIFT-04
- [ ] `tests/unit/test_identify.py` — covers IDENT-01 through IDENT-05
- [ ] `tests/unit/test_dedup_update.py` — covers TGRAM-03
- [ ] `tests/unit/test_filter_message.py` — covers TGRAM-02
- [ ] `tests/unit/test_migration_handler.py` — covers TGRAM-04
- [ ] `tests/unit/test_worker_queue.py` — covers TGRAM-05
- [ ] `tests/unit/test_processing_log.py` — covers JRNL-02, JRNL-03
- [ ] `tests/integration/test_pipeline.py` — covers TGRAM-01, JRNL-01
- [ ] `tests/integration/test_processing_log.py` — covers JRNL-04
- [ ] Framework install: `pip install pytest pytest-asyncio` (add to requirements-dev.txt)

---

## Sources

### Primary (HIGH confidence)
- Project research: `.planning/research/STACK.md` — library versions, integration patterns verified from PyPI
- Project research: `.planning/research/ARCHITECTURE.md` — system design, data flow, ORM schema, anti-patterns
- Project research: `.planning/research/PITFALLS.md` — 8 critical pitfalls with official source citations
- Project research: `.planning/research/FEATURES.md` — feature specifications, identification ladder, audit log fields
- Project decisions: `.planning/phases/01-foundation/01-CONTEXT.md` — locked implementation decisions

### Secondary (MEDIUM confidence)
- aiogram 3 official docs — https://docs.aiogram.dev/en/latest/ — Router, Filter, F magic filter system
- SQLAlchemy 2.0 async docs — https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html — AsyncSession, async_sessionmaker
- Alembic async cookbook — https://alembic.sqlalchemy.org/en/latest/cookbook.html — async template

### Tertiary (LOW confidence)
- None — all key claims verified via project research files with cited primary sources

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified from PyPI in STACK.md research
- Architecture: HIGH — patterns from official aiogram + SQLAlchemy docs and multi-source ARCHITECTURE.md research
- Pitfalls: HIGH — Telegram API limits and behaviors verified from official docs in PITFALLS.md

**Research date:** 2026-04-10
**Valid until:** 2026-07-10 (90 days — stable libraries; aiogram 3.x and SQLAlchemy 2.x are mature)

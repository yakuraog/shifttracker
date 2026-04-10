# Stack Research

**Domain:** Telegram bot + async web API + Google Sheets integration (Python)
**Researched:** 2026-04-10
**Confidence:** HIGH (versions verified from PyPI; integration patterns from official docs and active community)

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11+ | Runtime | 3.11 is the stable production choice; aiogram requires 3.10–3.14, and 3.11 gives best performance improvements (faster CPython) without bleeding-edge risk |
| aiogram | 3.27.0 | Telegram Bot API framework | De-facto standard for async Python Telegram bots; built on asyncio + aiohttp; middleware, FSM, Router system native to v3 |
| FastAPI | 0.115.x | Admin API and webhook endpoint | Async-native, shares the same asyncio event loop as aiogram; auto-generates OpenAPI docs; Pydantic v2 validation built in |
| PostgreSQL | 16.x | Persistent storage | Reliable, ACID-compliant; handles concurrent writes from 200 groups; JSONb for flexible message metadata |
| SQLAlchemy | 2.0.49 | ORM + async query interface | Industry standard; v2.0 adds full native asyncio support with `AsyncSession`; pairs with asyncpg and Alembic for migrations |
| asyncpg | 0.31.0 | Async PostgreSQL driver | Fastest PostgreSQL driver for Python async; required by SQLAlchemy's `postgresql+asyncpg://` dialect |
| gspread | 6.2.1 | Google Sheets write/read | Simplest Sheets API v4 wrapper for Python; far less boilerplate than raw `google-api-python-client`; handles auth, retries |
| Alembic | 1.18.4 | Database migrations | Official SQLAlchemy migration tool; supports async via `alembic init -t async`; auto-generates diffs from models |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic-settings | 2.x | Configuration management from env vars | Always — load `BOT_TOKEN`, `DATABASE_URL`, `GOOGLE_CREDENTIALS_JSON` from environment; validates types at startup |
| gspread-asyncio | 1.x | Async wrapper around gspread | Use when Sheets writes happen inside async handlers to avoid blocking the event loop; wraps gspread calls in threadpool |
| google-auth | 2.x | OAuth2 / service account auth for Sheets | Required by gspread for service account credentials; install alongside gspread |
| aiogram-fastapi-server | latest | Mount aiogram webhook into FastAPI router | Removes webhook endpoint boilerplate; integrates aiogram dispatcher into FastAPI lifespan |
| uvicorn | 0.29.x | ASGI server for FastAPI | Standard ASGI server; use `uvicorn[standard]` for hot reload in dev; Gunicorn + UvicornWorker in production |
| loguru | 0.7.x | Structured application logging | Simple, zero-config structured logs; async-safe via `enqueue=True`; better DX than stdlib logging for this project size |
| tenacity | 8.x | Retry logic with backoff | Google Sheets API has rate limits (60 req/min/user); wrap Sheets writes in tenacity retry decorators |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| Docker + Docker Compose | Containerization and local dev environment | Single `docker-compose.yml` runs bot + FastAPI + PostgreSQL; use `depends_on` with health checks so app waits for DB |
| Alembic CLI | Schema migrations | `alembic init -t async` creates async-compatible env.py; run migrations before app start in Docker entrypoint |
| pytest + pytest-asyncio | Async test runner | Required for testing aiogram handlers and SQLAlchemy async sessions; use `asyncio_mode = "auto"` in pytest.ini |
| ruff | Linting and formatting | Replaces flake8 + isort + black in one fast tool; configure in `pyproject.toml` |
| python-dotenv | Local .env loading for dev | pydantic-settings reads .env directly — python-dotenv not needed as a separate dep if using `model_config = SettingsConfigDict(env_file=".env")` |

---

## Installation

```bash
# Core runtime
pip install aiogram==3.27.0 fastapi[standard] uvicorn[standard]

# Database
pip install sqlalchemy[asyncio]==2.0.49 asyncpg==0.31.0 alembic==1.18.4

# Google Sheets
pip install gspread==6.2.1 gspread-asyncio google-auth

# Configuration & utilities
pip install pydantic-settings loguru tenacity

# Dev dependencies
pip install pytest pytest-asyncio ruff
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| gspread 6.x | google-api-python-client | Only if you need multiple Google APIs (Drive, Calendar, etc.) in the same service — then the generic client avoids double-auth setup |
| SQLAlchemy 2.0 async | Tortoise ORM | Tortoise is simpler for greenfield async-only CRUD. Choose it if the team is new to async ORMs and doesn't need SQLAlchemy's raw SQL escape hatches. SQLAlchemy wins here because Alembic is native and the project has non-trivial query needs (join log + employee + group) |
| SQLAlchemy 2.0 async | SQLModel | SQLModel is a thin Pydantic+SQLAlchemy layer; still in early maturity (0.x). Avoid for production data models |
| gspread-asyncio | Run gspread in executor manually | Equivalent result; gspread-asyncio is a maintained wrapper that handles the executor internally — less boilerplate |
| loguru | structlog | structlog is better for high-volume structured log pipelines with external aggregators. For this project scale, loguru's simplicity wins |
| Alembic | Automatic schema creation (`create_all`) | create_all is fine for prototypes but provides no upgrade path. Always use Alembic in anything that will run against real data |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Celery | Heavy Redis/RabbitMQ dependency; synchronous-first design fights asyncio; overkill for this message volume | In-process asyncio queue (`asyncio.Queue`) for burst buffering; if a true task queue is needed, use `taskiq` with Redis broker |
| Telethon / Pyrogram (userbot) | Violates Telegram ToS; requires user account login; explicitly out of scope | aiogram 3 (Bot API only) |
| psycopg2 | Synchronous driver — blocks the event loop in async context | asyncpg via `postgresql+asyncpg://` |
| Synchronous gspread without executor | Blocks asyncio event loop during Sheets I/O; will stall bot processing | gspread-asyncio wrapper |
| SQLModel | Still at 0.x, API unstable, adds abstraction with no benefit here | SQLAlchemy 2.0 + Pydantic-settings directly |
| Webhook polling fallback | Long-polling and webhook in the same process causes update duplication | Pick one: webhook in production (FastAPI handles it), polling in local dev without public URL |

---

## Integration Points

### aiogram + FastAPI — Shared Lifespan

aiogram 3 and FastAPI both run on asyncio. The correct integration pattern is:

1. Define a FastAPI `lifespan` async context manager.
2. Inside lifespan startup: call `await bot.set_webhook(url)` and start aiogram dispatcher.
3. Mount an `/webhook` POST endpoint on FastAPI that forwards raw updates to aiogram's `feed_webhook_update`.
4. `aiogram-fastapi-server` (`SimpleRequestHandler`) handles this mounting automatically.

```python
# Minimal pattern (without aiogram-fastapi-server helper)
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher

bot = Bot(token=settings.bot_token)
dp = Dispatcher()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.set_webhook(settings.webhook_url)
    yield
    await bot.delete_webhook()
    await bot.session.close()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    update = await request.json()
    await dp.feed_raw_update(bot, update)
```

### SQLAlchemy Async — Session Factory Pattern

Never create a new engine per request. Use a module-level `async_sessionmaker`:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(settings.database_url, pool_size=10)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
```

Inject sessions via FastAPI `Depends` or aiogram middleware.

### Google Sheets — Rate Limit Handling

Google Sheets API v4 limits: **300 req/60s per project, 60 req/60s per user**.

Strategy:
1. Collect all `update_cell` calls for a batch window (e.g., 2–5 seconds).
2. Use `worksheet.batch_update()` to write multiple cells in one API call.
3. Wrap Sheets calls in `tenacity.retry` with exponential backoff for 429 errors.
4. Run Sheets writes in `gspread-asyncio` to avoid blocking aiogram handler coroutines.

### Alembic with Async Engine

Initialize with the async template:
```bash
alembic init -t async alembic
```

This generates an `env.py` that uses `async_engine_from_config` and `run_sync` inside `run_migrations_online`. Individual migration scripts remain synchronous (use `op.get_bind()` — works transparently with asyncpg).

---

## Stack Patterns by Variant

**Local development (no public URL for webhooks):**
- Use aiogram polling mode: `await dp.start_polling(bot)`
- Run FastAPI separately on localhost for admin UI testing
- No webhook setup needed

**Production (with public URL / reverse proxy):**
- Run everything as one FastAPI app; aiogram receives updates via webhook
- Use Gunicorn + `UvicornWorker` for multi-process production deployment
- Set `WEBHOOK_URL=https://yourdomain.com/webhook` in environment

**High load (200+ active groups, thousands of photos/day):**
- Add `asyncio.Queue` in the bot process to buffer incoming photo messages
- One worker coroutine drains the queue and writes to DB + Sheets
- This avoids thundering-herd on Sheets API during burst periods

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|----------------|-------|
| aiogram 3.27.0 | Python 3.10–3.14 | Do NOT use Python 3.9 or below |
| SQLAlchemy 2.0.49 | asyncpg 0.31.0 | Use `postgresql+asyncpg://` DSN; `psycopg2` will not work async |
| SQLAlchemy 2.0.49 | Alembic 1.18.4 | Alembic 1.13+ required for SQLAlchemy 2.0 compatibility |
| gspread 6.2.1 | google-auth 2.x | gspread 6.x dropped support for oauth2client; use google-auth only |
| FastAPI 0.115.x | Pydantic v2 | FastAPI 0.100+ requires Pydantic v2; pydantic-settings 2.x matches |
| pydantic-settings 2.x | Pydantic v2 | Do not mix with pydantic-settings 1.x (Pydantic v1 API) |

---

## Sources

- [aiogram PyPI — version 3.27.0 confirmed](https://pypi.org/project/aiogram/) — HIGH confidence
- [aiogram GitHub releases](https://github.com/aiogram/aiogram/releases) — HIGH confidence
- [gspread PyPI — version 6.2.1](https://pypi.org/project/gspread/) — HIGH confidence
- [gspread-asyncio docs](https://gspread-asyncio.readthedocs.io/en/latest/api.html) — MEDIUM confidence
- [SQLAlchemy PyPI — version 2.0.49](https://pypi.org/project/sqlalchemy/) — HIGH confidence
- [asyncpg PyPI — version 0.31.0](https://pypi.org/project/asyncpg/) — HIGH confidence
- [Alembic PyPI — version 1.18.4](https://pypi.org/project/alembic/) — HIGH confidence
- [Alembic async cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html) — HIGH confidence
- [aiogram-fastapi-server PyPI](https://pypi.org/project/aiogram-fastapi-server/) — MEDIUM confidence
- [FastAPI settings docs](https://fastapi.tiangolo.com/advanced/settings/) — HIGH confidence
- [BetterStack: TortoiseORM vs SQLAlchemy 2025](https://betterstack.com/community/guides/scaling-python/tortoiseorm-vs-sqlalchemy/) — MEDIUM confidence

---

*Stack research for: ShiftTracker (Telegram shift monitoring + Google Sheets auto-fill)*
*Researched: 2026-04-10*

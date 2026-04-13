import asyncio
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from fastapi import FastAPI
from loguru import logger
from starlette.middleware.sessions import SessionMiddleware

from shifttracker.config import Settings
from shifttracker.bot.router import router as photo_router
from shifttracker.db.engine import engine, async_session_factory
from shifttracker.db.models import Base
from shifttracker.pipeline.worker import start_workers, stop_workers, set_bot
from shifttracker.sheets.writer import SheetsWriter
from shifttracker.admin.router import admin_router

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    bot = None
    dp = None
    polling_task = None

    # Auto-create tables (for SQLite dev mode; production uses Alembic)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")

    # Bot is optional — skip if token is not configured (allows admin UI testing)
    if settings.bot_token and settings.bot_token != "your-bot-token-here":
        try:
            bot = Bot(
                token=settings.bot_token,
                default=DefaultBotProperties(parse_mode=None),
            )
            dp = Dispatcher()
            dp.include_router(photo_router)

            # Start pipeline workers
            await start_workers(count=settings.worker_count)
            logger.info(f"Started {settings.worker_count} pipeline workers")

            # Start polling (dev mode — long-polling for development convenience)
            polling_task = asyncio.create_task(dp.start_polling(bot))
            logger.info("Bot polling started")

            app.state.bot = bot
            app.state.dp = dp
            set_bot(bot)  # Для уведомлений оператору
        except Exception as e:
            logger.warning(f"Bot startup skipped: {e}")
            bot = None
    else:
        logger.info("Bot token not configured — running in admin-only mode")

    # Start Sheets writer (no-ops gracefully when credentials not configured)
    sheets_writer = SheetsWriter(settings=settings, session_factory=async_session_factory)
    await sheets_writer.start()
    app.state.sheets_writer = sheets_writer

    yield

    # Shutdown
    if polling_task:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        await stop_workers()
    await sheets_writer.stop()
    await engine.dispose()
    if bot:
        await bot.session.close()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="ShiftTracker API",
        version="0.1.0",
        description="Система автоматического заполнения таблицы смен на основе фотографий из Telegram-групп",
        lifespan=lifespan,
    )

    # Session middleware must be added before routers
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.include_router(admin_router, prefix="/admin")

    return app

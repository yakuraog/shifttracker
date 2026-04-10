import asyncio
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from fastapi import FastAPI
from loguru import logger

from shifttracker.config import Settings
from shifttracker.bot.router import router as photo_router
from shifttracker.db.engine import engine, async_session_factory
from shifttracker.pipeline.worker import start_workers, stop_workers
from shifttracker.sheets.writer import SheetsWriter

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
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

    # Start Sheets writer (no-ops gracefully when credentials not configured)
    sheets_writer = SheetsWriter(settings=settings, session_factory=async_session_factory)
    await sheets_writer.start()
    app.state.sheets_writer = sheets_writer

    yield

    # Shutdown
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    await stop_workers()
    await sheets_writer.stop()
    await engine.dispose()
    await bot.session.close()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(title="ShiftTracker", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app

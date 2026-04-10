import asyncio

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from shifttracker.db.models import Base


@pytest.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def test_client():
    """Synchronous TestClient with in-memory SQLite and SessionMiddleware."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient

    # Create in-memory async engine for tests
    test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)

    async def setup_db():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.new_event_loop().run_until_complete(setup_db())

    test_session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    # Patch session factory used by admin deps.get_db
    with patch("shifttracker.admin.deps.async_session_factory", test_session_factory):
        # Import here to pick up patched session factory
        from shifttracker.app import create_app
        from contextlib import asynccontextmanager
        from fastapi import FastAPI
        from starlette.middleware.sessions import SessionMiddleware
        from shifttracker.admin.router import admin_router
        from shifttracker.config import Settings

        # Build a minimal test app — skip lifespan (bot/workers) entirely
        settings = Settings()

        test_app = FastAPI()
        test_app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
        test_app.include_router(admin_router, prefix="/admin")

        with TestClient(test_app, raise_server_exceptions=True) as client:
            yield client

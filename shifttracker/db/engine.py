from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from shifttracker.config import Settings

settings = Settings()
engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

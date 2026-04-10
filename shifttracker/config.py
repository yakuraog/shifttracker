from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    bot_token: str = "placeholder"
    database_url: str = "postgresql+asyncpg://shifttracker:password@localhost:5432/shifttracker"
    test_database_url: str = "sqlite+aiosqlite://"
    timezone: str = "Europe/Moscow"
    queue_max_size: int = 500
    worker_count: int = 8
    log_level: str = "INFO"

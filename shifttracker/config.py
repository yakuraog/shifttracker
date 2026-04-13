from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    bot_token: str = "placeholder"
    database_url: str = "sqlite+aiosqlite:///shifttracker.db"
    test_database_url: str = "sqlite+aiosqlite://"
    timezone: str = "Europe/Moscow"
    queue_max_size: int = 500
    worker_count: int = 8
    log_level: str = "INFO"
    google_sheets_credentials_file: str = ""  # empty string = Sheets writer disabled
    sheets_flush_interval: int = 5  # seconds between flush cycles
    sheets_max_retries: int = 5  # retry_count threshold before ERROR
    admin_username: str = "admin"
    admin_password: str = "changeme"
    secret_key: str = "dev-secret-change-in-production"
    operator_chat_id: int = 0  # 0 = уведомления отключены; Telegram chat_id оператора

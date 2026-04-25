from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "staging", "production"] = "development"
    app_secret_key: str = Field(min_length=32)
    app_base_url: str = "http://localhost:8000"
    session_lifetime_hours: int = 168

    database_url: str
    redis_url: str = "redis://redis:6379/0"

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    timezone: str = "Europe/Moscow"

    avito_proxy_url: str | None = None
    avito_request_rate_limit: float = 1.0

    openrouter_api_key: str | None = None
    openrouter_default_text_model: str = "anthropic/claude-haiku-4.5"
    openrouter_default_vision_model: str = "anthropic/claude-sonnet-4.7"
    openrouter_daily_usd_limit: float = 10.0

    telegram_bot_token: str | None = None
    telegram_allowed_user_ids: str = ""

    system_paused: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

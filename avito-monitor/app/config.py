from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
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

    # avito-xapi gateway (used by avito-mcp + health-checker).
    avito_xapi_url: str = "http://host.docker.internal:8080"
    avito_xapi_api_key: str = "test_dev_key_123"

    # V2 reliability: health-checker.
    reliability_enabled: bool = True
    health_check_interval_sec: int = 300

    # V2.1 reliability — scenario I (notification listener freshness):
    # how stale the latest forwarded Android notification can be before scenario
    # I starts failing. The default is generous because real chat traffic is
    # bursty; tighten for accounts with constant inbound volume.
    notification_freshness_hours: float = 12.0

    # V2 reliability: activity-simulator (TZ §6).
    activity_sim_enabled: bool = True
    activity_sim_timezone: str = "Europe/Moscow"
    activity_sim_workhours_start: int = 10
    activity_sim_workhours_end: int = 22
    activity_sim_actions_per_hour_work: int = 10
    activity_sim_actions_per_hour_off: int = 2

    # V2 reliability: messenger-bot (TZ §6, Stage 6).
    messenger_bot_enabled: bool = True
    messenger_bot_template: str = (
        "Здравствуйте! Минуту, сейчас подключится оператор и ответит."
    )
    messenger_bot_rate_limit_per_hour: int = 60
    messenger_bot_per_channel_cooldown_sec: int = 60
    messenger_bot_whitelist_own_listings_only: bool = True
    # Optional override; if unset the bot resolves it from
    # ``GET /api/v1/sessions/current`` once and caches the result.
    avito_own_user_id: int | None = None

    @field_validator("avito_own_user_id", mode="before")
    @classmethod
    def _empty_str_is_none(cls, v):
        """Treat empty .env value (``AVITO_OWN_USER_ID=``) as None."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    openrouter_api_key: str | None = None
    openrouter_default_text_model: str = "anthropic/claude-haiku-4.5"
    openrouter_default_vision_model: str = "anthropic/claude-sonnet-4.7"
    openrouter_daily_usd_limit: float = 10.0

    telegram_bot_token: str | None = None
    telegram_allowed_user_ids: str = ""

    # V2 reliability — Stage 8: Telegram alerts (lite). TZ §6.
    reliability_tg_alert_enabled: bool = True
    reliability_tg_alert_fail_threshold: int = 3
    reliability_tg_alert_daily_summary_hour: int = 9

    system_paused: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

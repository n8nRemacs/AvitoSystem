"""
Configuration management for Avito SmartFree
Loads settings from environment variables
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment"""

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://avito:avito@localhost:5432/avito_smartfree",
        description="PostgreSQL connection URL"
    )

    # Token Farm
    farm_host: str = Field(default="0.0.0.0", description="Token Farm API host")
    farm_port: int = Field(default=8000, description="Token Farm API port")
    farm_api_key: Optional[str] = Field(default=None, description="API key for farm access")
    farm_api_url: Optional[str] = Field(default=None, description="Token Farm API URL (for MCP server)")

    # Redroid containers
    redroid_image: str = Field(default="redroid/redroid:12.0.0-latest", description="Redroid Docker image")
    redroid_containers: int = Field(default=10, description="Number of Redroid containers")
    container_ram_mb: int = Field(default=1536, description="RAM per container in MB")

    # Token refresh
    token_refresh_hours: int = Field(default=20, description="Refresh tokens every N hours")
    sync_timeout_seconds: int = Field(default=120, description="Timeout for account sync")

    # Telegram
    telegram_bot_token: str = Field(default="", description="Telegram bot token")
    telegram_admin_ids: list[int] = Field(default=[], description="Admin Telegram user IDs")

    # Avito
    avito_ws_url: str = Field(
        default="wss://socket.avito.ru/socket",
        description="Avito WebSocket URL"
    )
    avito_api_url: str = Field(
        default="https://app.avito.ru",
        description="Avito API base URL"
    )
    avito_user_agent: str = Field(
        default="AVITO 215.1 (Samsung SM-G998B; Android 12; ru)",
        description="User-Agent for Avito requests"
    )

    # Proxy
    proxy_url: Optional[str] = Field(default=None, description="Default proxy URL")
    proxy_rotation_enabled: bool = Field(default=True, description="Enable proxy rotation")

    # MCP Server
    mcp_host: str = Field(default="0.0.0.0", description="MCP server host")
    mcp_port: int = Field(default=8080, description="MCP server port")
    mcp_workers: int = Field(default=4, description="Number of MCP workers")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format (json or text)")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get settings instance"""
    return settings

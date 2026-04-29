"""Settings for avito-mcp.

All configuration is read from env vars. Designed to be importable both inside
the docker container (where defaults work) and locally for tests.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Upstream avito-xapi.
    # Default targets the developer machine's port-forward via docker host gateway.
    avito_xapi_url: str = "http://host.docker.internal:8080"
    avito_xapi_api_key: str = "test_dev_key_123"
    avito_xapi_timeout_seconds: float = 30.0

    # MCP transport.
    avito_mcp_transport: Literal["stdio", "http", "sse"] = "stdio"
    avito_mcp_http_host: str = "0.0.0.0"  # noqa: S104 — container-bound, exposed via docker
    avito_mcp_http_port: int = 9000
    # Bearer token required when transport is http/sse. Empty string means
    # "no auth" but we refuse to start over HTTP without one — see __main__.py.
    avito_mcp_auth_token: str = ""

    # User-Agent identifying the MCP client to xapi (for logging).
    avito_mcp_user_agent: str = Field(default="avito-mcp/0.1.0")


@lru_cache
def get_mcp_settings() -> McpSettings:
    return McpSettings()  # type: ignore[call-arg]

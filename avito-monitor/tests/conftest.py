"""Project-wide pytest fixtures.

Sets dummy env vars required by ``app.config`` / ``avito_mcp.config`` so that
importing modules in unit tests doesn't blow up with validation errors.
"""
from __future__ import annotations

import os

# These must be set before any test imports app.config / avito_mcp.config.
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-must-be-at-least-32-chars-long-xxxx")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/test",
)
os.environ.setdefault("AVITO_XAPI_URL", "http://xapi.test")
os.environ.setdefault("AVITO_XAPI_API_KEY", "test-key")

"""Unit tests for the DB-backed rate-limit helpers."""
from __future__ import annotations

import pytest

from app.config import Settings
from app.services.messenger_bot.rate_limit import (
    is_channel_rate_limited,
    is_globally_rate_limited,
)


def make_settings(**overrides) -> Settings:
    base = {
        "app_secret_key": "x" * 32,
        "database_url": "postgresql+asyncpg://t:t@localhost/t",
        "messenger_bot_rate_limit_per_hour": 60,
        "messenger_bot_per_channel_cooldown_sec": 60,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_global_rate_limit_not_tripped_below_threshold(patch_sessionmaker):
    patch_sessionmaker.queue_scalar(40)  # below 60/hour
    limited, used = await is_globally_rate_limited(make_settings())
    assert limited is False
    assert used == 40


@pytest.mark.asyncio
async def test_global_rate_limit_tripped_at_threshold(patch_sessionmaker):
    patch_sessionmaker.queue_scalar(60)  # exactly at limit
    limited, used = await is_globally_rate_limited(make_settings())
    assert limited is True
    assert used == 60


@pytest.mark.asyncio
async def test_global_rate_limit_tripped_above_threshold(patch_sessionmaker):
    patch_sessionmaker.queue_scalar(100)
    limited, used = await is_globally_rate_limited(
        make_settings(messenger_bot_rate_limit_per_hour=60)
    )
    assert limited is True
    assert used == 100


@pytest.mark.asyncio
async def test_channel_rate_limit_tripped_when_recent_outgoing(patch_sessionmaker):
    patch_sessionmaker.queue_scalar(1)
    assert await is_channel_rate_limited("u2i-x", make_settings()) is True


@pytest.mark.asyncio
async def test_channel_rate_limit_clear_when_zero(patch_sessionmaker):
    patch_sessionmaker.queue_scalar(0)
    assert await is_channel_rate_limited("u2i-x", make_settings()) is False

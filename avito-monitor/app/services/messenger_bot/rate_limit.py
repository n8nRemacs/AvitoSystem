"""DB-backed rate limit for the messenger-bot.

Both checks query ``messenger_messages`` for outgoing rows in a recent
window. The DB is the source of truth — restart-resilient, multi-instance-safe.

* :func:`global_outgoing_count_last_hour` — for the global per-hour cap.
* :func:`channel_outgoing_count_within` — for the per-channel cooldown.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.config import Settings
from app.db.base import get_sessionmaker
from app.db.models import MessengerMessage


async def global_outgoing_count_last_hour() -> int:
    """Count ``direction='out'`` rows written in the last 60 minutes."""
    cutoff = datetime.now(UTC) - timedelta(hours=1)
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stmt = (
            select(func.count())
            .select_from(MessengerMessage)
            .where(MessengerMessage.direction == "out")
            .where(MessengerMessage.created_at >= cutoff)
        )
        n = (await session.execute(stmt)).scalar() or 0
    return int(n)


async def channel_outgoing_count_within(channel_id: str, seconds: int) -> int:
    """Count ``direction='out'`` rows for one channel within ``seconds`` window."""
    cutoff = datetime.now(UTC) - timedelta(seconds=max(1, seconds))
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        stmt = (
            select(func.count())
            .select_from(MessengerMessage)
            .where(MessengerMessage.direction == "out")
            .where(MessengerMessage.channel_id == channel_id)
            .where(MessengerMessage.created_at >= cutoff)
        )
        n = (await session.execute(stmt)).scalar() or 0
    return int(n)


async def is_globally_rate_limited(settings: Settings) -> tuple[bool, int]:
    """``(limited, used_count)`` against ``messenger_bot_rate_limit_per_hour``."""
    used = await global_outgoing_count_last_hour()
    limit = settings.messenger_bot_rate_limit_per_hour
    return used >= limit, used


async def is_channel_rate_limited(channel_id: str, settings: Settings) -> bool:
    """Per-channel cooldown — refuse if ANY outgoing happened in the window."""
    cooldown = settings.messenger_bot_per_channel_cooldown_sec
    n = await channel_outgoing_count_within(channel_id, cooldown)
    return n > 0

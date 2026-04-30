"""Tests for account_tick_iteration — proactive refresh path."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.services.health_checker.account_tick import account_tick_iteration


@pytest.mark.asyncio
async def test_active_account_near_expiry_triggers_refresh():
    """state=active and expires_at < now+30min → refresh-cycle is triggered."""
    now = datetime(2026, 4, 30, 18, 0, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        {
            "id": "acc-1",
            "nickname": "Clone",
            "state": "active",
            "expires_at": (now + timedelta(minutes=10)).isoformat(),
            "consecutive_cooldowns": 0,
        }
    ]

    tg_calls: list[str] = []

    async def fake_tg(msg: str) -> None:
        tg_calls.append(msg)

    await account_tick_iteration(pool=pool, now=now, tg=fake_tg)
    pool.trigger_refresh_cycle.assert_awaited_once_with("acc-1")
    assert tg_calls == []


@pytest.mark.asyncio
async def test_active_account_already_expired_triggers_refresh():
    """state=active and expires_at < now (already expired — today's case) → refresh."""
    now = datetime(2026, 4, 30, 18, 0, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        {
            "id": "acc-1",
            "state": "active",
            "expires_at": (now - timedelta(hours=7)).isoformat(),
            "consecutive_cooldowns": 0,
        }
    ]

    async def noop(_): pass
    await account_tick_iteration(pool=pool, now=now, tg=noop)
    pool.trigger_refresh_cycle.assert_awaited_once_with("acc-1")


@pytest.mark.asyncio
async def test_active_account_fresh_does_not_refresh():
    """state=active with TTL > 30min → no refresh."""
    now = datetime(2026, 4, 30, 18, 0, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        {
            "id": "acc-1",
            "state": "active",
            "expires_at": (now + timedelta(hours=10)).isoformat(),
            "consecutive_cooldowns": 0,
        }
    ]

    async def noop(_): pass
    await account_tick_iteration(pool=pool, now=now, tg=noop)
    pool.trigger_refresh_cycle.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_account_no_session_triggers_refresh():
    """state=active but expires_at is None (no active session) → refresh."""
    now = datetime(2026, 4, 30, 18, 0, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        {"id": "acc-1", "state": "active", "expires_at": None, "consecutive_cooldowns": 0}
    ]

    async def noop(_): pass
    await account_tick_iteration(pool=pool, now=now, tg=noop)
    pool.trigger_refresh_cycle.assert_awaited_once_with("acc-1")

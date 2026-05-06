"""Tests for cooldown auto-recovery in account_tick."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.health_checker.account_tick import account_tick_iteration


def _make_pool(accounts: list[dict]):
    pool = MagicMock()
    pool.list_all_accounts = AsyncMock(return_value=accounts)
    pool.patch_state = AsyncMock()
    return pool


@pytest.mark.asyncio
async def test_recovers_cooldown_with_fresh_session_to_active():
    """Cooldown expired AND session still fresh → patch_state('active')."""
    now = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
    fresh = (now + timedelta(hours=12)).isoformat()
    cooldown_past = (now - timedelta(hours=24)).isoformat()

    pool = _make_pool([
        {"id": "acc-x", "nickname": "auto-431483569", "android_user_id": 0,
         "state": "cooldown", "cooldown_until": cooldown_past,
         "expires_at": fresh, "consecutive_cooldowns": 1},
    ])
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    pool.patch_state.assert_awaited_once()
    args, kwargs = pool.patch_state.call_args
    assert args[0] == "acc-x"
    assert args[1] == "active"


@pytest.mark.asyncio
async def test_recovers_cooldown_with_stale_session_to_needs_refresh():
    """Cooldown expired AND session stale → patch_state('needs_refresh')."""
    now = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
    stale = (now - timedelta(minutes=1)).isoformat()
    cooldown_past = (now - timedelta(hours=1)).isoformat()

    pool = _make_pool([
        {"id": "acc-y", "nickname": "Clone", "android_user_id": 10,
         "state": "cooldown", "cooldown_until": cooldown_past,
         "expires_at": stale, "consecutive_cooldowns": 2},
    ])
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    pool.patch_state.assert_awaited_once()
    args, _ = pool.patch_state.call_args
    assert args[0] == "acc-y"
    assert args[1] == "needs_refresh"


@pytest.mark.asyncio
async def test_does_not_recover_active_cooldown():
    """Cooldown still in future → no state change."""
    now = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
    cooldown_future = (now + timedelta(minutes=20)).isoformat()
    fresh = (now + timedelta(hours=12)).isoformat()

    pool = _make_pool([
        {"id": "acc-z", "nickname": "n", "android_user_id": 0,
         "state": "cooldown", "cooldown_until": cooldown_future,
         "expires_at": fresh, "consecutive_cooldowns": 1},
    ])
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    pool.patch_state.assert_not_awaited()


@pytest.mark.asyncio
async def test_does_not_touch_active_or_dead_accounts():
    """state in (active, dead, needs_refresh, waiting_refresh) → no recovery."""
    now = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)
    fresh = (now + timedelta(hours=12)).isoformat()

    pool = _make_pool([
        {"id": "a", "nickname": "n", "android_user_id": 0, "state": "active",
         "expires_at": fresh, "consecutive_cooldowns": 0},
        {"id": "b", "nickname": "n", "android_user_id": 0, "state": "dead",
         "expires_at": None, "consecutive_cooldowns": 5},
    ])
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    pool.patch_state.assert_not_awaited()

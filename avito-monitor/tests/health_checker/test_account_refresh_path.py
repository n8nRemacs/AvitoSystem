"""Tests for account-aware tick in health_checker."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from app.services.health_checker.account_tick import account_tick_iteration

NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_cooldown_expired_triggers_refresh_cycle():
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "cooldown",
        "cooldown_until": (NOW - timedelta(seconds=10)).isoformat(),
    }]
    pool.trigger_refresh_cycle = AsyncMock()

    await account_tick_iteration(pool=pool, now=NOW, tg=AsyncMock())

    pool.trigger_refresh_cycle.assert_called_once_with("acc-1")


@pytest.mark.asyncio
async def test_cooldown_not_expired_does_nothing():
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "cooldown",
        "cooldown_until": (NOW + timedelta(minutes=10)).isoformat(),
    }]
    pool.trigger_refresh_cycle = AsyncMock()

    await account_tick_iteration(pool=pool, now=NOW, tg=AsyncMock())
    pool.trigger_refresh_cycle.assert_not_called()


@pytest.mark.asyncio
async def test_waiting_refresh_5min_marks_dead_and_alerts():
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "waiting_refresh", "nickname": "Clone",
        "android_user_id": 10,
        "waiting_since": (NOW - timedelta(minutes=5, seconds=10)).isoformat(),
    }]
    pool.patch_state = AsyncMock()
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=NOW, tg=tg)

    pool.patch_state.assert_called_once_with("acc-1", "dead", reason="waiting_refresh timeout 5m")
    tg.assert_awaited_once()
    msg = tg.await_args.args[0]
    assert "Clone" in msg
    assert "10" in msg


@pytest.mark.asyncio
async def test_waiting_refresh_within_window_no_action():
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "waiting_refresh",
        "waiting_since": (NOW - timedelta(minutes=4)).isoformat(),
    }]
    pool.patch_state = AsyncMock()

    await account_tick_iteration(pool=pool, now=NOW, tg=AsyncMock())
    pool.patch_state.assert_not_called()


@pytest.mark.asyncio
async def test_active_with_expiry_under_3min_triggers_proactive_refresh():
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "active",
        "expires_at": (NOW + timedelta(minutes=2)).isoformat(),
    }]
    pool.trigger_refresh_cycle = AsyncMock()

    await account_tick_iteration(pool=pool, now=NOW, tg=AsyncMock())
    pool.trigger_refresh_cycle.assert_called_once_with("acc-1")


@pytest.mark.asyncio
async def test_active_with_expiry_far_does_nothing():
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "active",
        "expires_at": (NOW + timedelta(hours=2)).isoformat(),
    }]
    pool.trigger_refresh_cycle = AsyncMock()

    await account_tick_iteration(pool=pool, now=NOW, tg=AsyncMock())
    pool.trigger_refresh_cycle.assert_not_called()


@pytest.mark.asyncio
async def test_dead_state_does_nothing():
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "dead",
    }]
    pool.trigger_refresh_cycle = AsyncMock()
    pool.patch_state = AsyncMock()

    await account_tick_iteration(pool=pool, now=NOW, tg=AsyncMock())
    pool.trigger_refresh_cycle.assert_not_called()
    pool.patch_state.assert_not_called()

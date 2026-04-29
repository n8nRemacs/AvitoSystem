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


@pytest.mark.asyncio
async def test_consecutive_5_alert_emitted_once():
    """First call sends alert; second call (same state) does NOT re-emit."""
    # Reset module-level set between tests
    from app.services.health_checker import account_tick as mod
    mod._alerted_24h.clear()

    pool = AsyncMock()
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "cooldown", "nickname": "Clone",
        "consecutive_cooldowns": 5,
        "cooldown_until": (NOW + timedelta(hours=24)).isoformat(),
    }]
    pool.trigger_refresh_cycle = AsyncMock()
    tg = AsyncMock()

    # First tick — alert fires
    await account_tick_iteration(pool=pool, now=NOW, tg=tg)
    assert tg.await_count == 1

    # Second tick — same data, alert does NOT fire again
    await account_tick_iteration(pool=pool, now=NOW, tg=tg)
    assert tg.await_count == 1


@pytest.mark.asyncio
async def test_consecutive_resets_after_recovery():
    """After consecutive_cooldowns drops to 0, alert state resets and can fire again."""
    from app.services.health_checker import account_tick as mod
    mod._alerted_24h.clear()

    pool = AsyncMock()
    pool.trigger_refresh_cycle = AsyncMock()
    tg = AsyncMock()

    # Phase 1: consecutive=5 → alert fires
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "cooldown", "nickname": "Clone",
        "consecutive_cooldowns": 5,
        "cooldown_until": (NOW + timedelta(hours=24)).isoformat(),
    }]
    await account_tick_iteration(pool=pool, now=NOW, tg=tg)
    assert tg.await_count == 1
    assert "acc-1" in mod._alerted_24h

    # Phase 2: consecutive=0 → alert state resets
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "active", "nickname": "Clone",
        "consecutive_cooldowns": 0,
        "expires_at": (NOW + timedelta(hours=23)).isoformat(),
    }]
    await account_tick_iteration(pool=pool, now=NOW, tg=tg)
    assert "acc-1" not in mod._alerted_24h

    # Phase 3: consecutive=5 again → alert fires AGAIN (it was reset)
    pool.list_all_accounts.return_value = [{
        "id": "acc-1", "state": "cooldown", "nickname": "Clone",
        "consecutive_cooldowns": 5,
        "cooldown_until": (NOW + timedelta(hours=24)).isoformat(),
    }]
    await account_tick_iteration(pool=pool, now=NOW, tg=tg)
    assert tg.await_count == 2

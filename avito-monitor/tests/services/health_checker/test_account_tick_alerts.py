"""Tests for one-stale alert logic in account_tick after Phase 4 refactor."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.services.health_checker.account_tick import (
    account_tick_iteration,
    _alerted_stale_accounts,
)


def _account(*, id, nickname, expires_at, state="active", android_user_id=0):
    return {
        "id": id,
        "nickname": nickname,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "state": state,
        "android_user_id": android_user_id,
        "consecutive_cooldowns": 0,
    }


@pytest.fixture(autouse=True)
def reset_alert_state():
    _alerted_stale_accounts.clear()
    yield
    _alerted_stale_accounts.clear()


@pytest.mark.asyncio
async def test_no_alert_when_both_fresh():
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main", expires_at=now + timedelta(hours=10), android_user_id=0),
        _account(id="c", nickname="Clone", expires_at=now + timedelta(hours=8), android_user_id=10),
    ]
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    tg.assert_not_called()
    assert "trigger_refresh_cycle" not in str(pool.method_calls)


@pytest.mark.asyncio
async def test_one_stale_emits_alert_once():
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main", expires_at=now - timedelta(minutes=5), android_user_id=0),
        _account(id="c", nickname="Clone", expires_at=now + timedelta(hours=10), android_user_id=10),
    ]
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)
    await account_tick_iteration(pool=pool, now=now + timedelta(seconds=30), tg=tg)
    await account_tick_iteration(pool=pool, now=now + timedelta(minutes=5), tg=tg)

    # Idempotent: only one TG message emitted total despite 3 ticks
    assert tg.call_count == 1
    msg = tg.call_args.args[0]
    assert "Main" in msg
    assert "user_0" in msg


@pytest.mark.asyncio
async def test_alert_resets_when_account_recovers():
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    tg = AsyncMock()

    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main", expires_at=now - timedelta(minutes=5), android_user_id=0),
        _account(id="c", nickname="Clone", expires_at=now + timedelta(hours=10), android_user_id=10),
    ]
    await account_tick_iteration(pool=pool, now=now, tg=tg)
    assert tg.call_count == 1

    # Main recovers
    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main", expires_at=now + timedelta(hours=23), android_user_id=0),
        _account(id="c", nickname="Clone", expires_at=now + timedelta(hours=10), android_user_id=10),
    ]
    await account_tick_iteration(pool=pool, now=now + timedelta(minutes=10), tg=tg)
    assert tg.call_count == 1  # no new alert during recovery

    # Main goes stale AGAIN (different cycle) — new alert allowed
    # Clone expiry deliberately far enough that it remains fresh at tick time (now + 24h).
    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main",
                 expires_at=now + timedelta(hours=24) - timedelta(minutes=1), android_user_id=0),
        _account(id="c", nickname="Clone",
                 expires_at=now + timedelta(hours=48), android_user_id=10),
    ]
    await account_tick_iteration(pool=pool, now=now + timedelta(hours=24), tg=tg)
    assert tg.call_count == 2


@pytest.mark.asyncio
async def test_both_stale_emits_critical_alert():
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main", expires_at=now - timedelta(minutes=5), android_user_id=0),
        _account(id="c", nickname="Clone", expires_at=now - timedelta(minutes=3), android_user_id=10),
    ]
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    # Three alerts total: per-account stale (Main, Clone) + critical pool-down
    assert tg.call_count == 3
    messages = " ".join(c.args[0] for c in tg.call_args_list)
    assert "Polling DOWN" in messages or "DOWN" in messages
    assert "Main" in messages
    assert "Clone" in messages


@pytest.mark.asyncio
async def test_no_proactive_refresh_call():
    """Phase 4: account_tick must NOT call trigger_refresh_cycle anywhere."""
    now = datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
    pool = AsyncMock()
    pool.list_all_accounts.return_value = [
        _account(id="m", nickname="Main", expires_at=now + timedelta(minutes=10), android_user_id=0),
        _account(id="c", nickname="Clone", expires_at=now - timedelta(minutes=5),
                 android_user_id=10, state="cooldown"),
    ]
    tg = AsyncMock()

    await account_tick_iteration(pool=pool, now=now, tg=tg)

    # Assert that trigger_refresh_cycle was never called regardless of state
    pool.trigger_refresh_cycle.assert_not_called()

"""Smoke tests: account_loop wiring — confirms account_tick_iteration is called."""
import asyncio

import pytest

import app.services.health_checker.account_loop as loop_mod


@pytest.fixture(autouse=True)
def fast_interval(monkeypatch):
    """Override ACCOUNT_TICK_INTERVAL to 0.05 s so tests finish instantly."""
    monkeypatch.setattr(loop_mod, "ACCOUNT_TICK_INTERVAL", 0.05)


@pytest.mark.asyncio
async def test_account_loop_calls_account_tick_iteration(monkeypatch):
    """account_loop must call account_tick_iteration on its first iteration."""
    called_with: list[tuple] = []

    async def fake_tick(*, pool, now, tg):
        called_with.append((pool, now, tg))

    # Patch the name that account_loop.py bound at import time.
    monkeypatch.setattr(loop_mod, "account_tick_iteration", fake_tick)

    stop = asyncio.Event()
    pool = object()
    tg = object()

    async def _stopper():
        await asyncio.sleep(0.15)
        stop.set()

    asyncio.create_task(_stopper())
    await loop_mod.account_loop(pool, tg, stop)

    assert len(called_with) >= 1, "account_tick_iteration was never called"
    assert called_with[0][0] is pool, "pool was not forwarded correctly"
    assert called_with[0][2] is tg, "tg was not forwarded correctly"


@pytest.mark.asyncio
async def test_account_loop_continues_after_tick_exception(monkeypatch):
    """An exception inside a tick must not kill the loop."""
    call_count = 0

    async def flaky_tick(*, pool, now, tg):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated tick failure")

    monkeypatch.setattr(loop_mod, "account_tick_iteration", flaky_tick)

    stop = asyncio.Event()

    async def _stopper():
        await asyncio.sleep(0.3)
        stop.set()

    asyncio.create_task(_stopper())
    await loop_mod.account_loop(object(), object(), stop)

    assert call_count >= 2, (
        f"loop must survive the first tick error; got call_count={call_count}"
    )


@pytest.mark.asyncio
async def test_account_loop_stops_immediately_when_event_preset(monkeypatch):
    """account_loop must exit without any tick when stop_event is already set."""
    called = []

    async def should_not_be_called(**_):
        called.append(True)

    monkeypatch.setattr(loop_mod, "account_tick_iteration", should_not_be_called)

    stop = asyncio.Event()
    stop.set()  # loop checks stop first → exits before calling tick

    await asyncio.wait_for(
        loop_mod.account_loop(object(), object(), stop), timeout=1.0
    )

    assert called == [], "tick must NOT run when stop_event is already set at entry"

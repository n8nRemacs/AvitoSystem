"""Tests for fetch_with_pool helper in app.tasks.polling."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.account_pool import NoAvailableAccountError
from app.tasks.polling import fetch_with_pool
from avito_mcp.integrations.xapi_client import XapiError


# ---------------------------------------------------------------------------
# Helper: build a mock AccountPool that yields accounts from a queue
# ---------------------------------------------------------------------------

def make_pool(accounts: list[dict]):
    """Build a mock pool that yields the given accounts in order via claim_for_poll."""
    pool = MagicMock()
    pool.report = AsyncMock()
    queue = list(accounts)

    @asynccontextmanager
    async def fake_claim():
        if not queue:
            raise NoAvailableAccountError({"error": "pool_drained", "accounts": []})
        acc = queue.pop(0)
        yield acc

    pool.claim_for_poll = fake_claim
    return pool


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_403_retries_with_different_account():
    """On 403 the helper retries with the next account and returns success."""
    pool = make_pool([{"account_id": "A"}, {"account_id": "B"}])
    fetcher = AsyncMock(side_effect=[
        XapiError("firewall", status_code=403),
        {"items": [], "total": 0},
    ])

    result = await fetch_with_pool(fetcher_fn=fetcher, pool=pool, max_attempts=2)

    assert result == {"items": [], "total": 0}
    assert pool.report.await_count == 2
    first_call_args = pool.report.await_args_list[0].args
    second_call_args = pool.report.await_args_list[1].args
    assert first_call_args[:2] == ("A", 403)
    assert second_call_args[:2] == ("B", 200)


@pytest.mark.asyncio
async def test_401_retries_without_sleep(monkeypatch):
    """On 401 the helper retries immediately (no sleep) and returns success."""
    pool = make_pool([{"account_id": "A"}, {"account_id": "B"}])
    fetcher = AsyncMock(side_effect=[
        XapiError("unauthorized", status_code=401),
        {"items": []},
    ])
    sleep_calls: list[float] = []

    async def fast_sleep(d: float) -> None:
        sleep_calls.append(d)

    monkeypatch.setattr("app.tasks.polling.asyncio.sleep", fast_sleep)

    result = await fetch_with_pool(fetcher_fn=fetcher, pool=pool, max_attempts=2)

    assert result == {"items": []}
    assert sleep_calls == []  # no sleep on 401


@pytest.mark.asyncio
async def test_5xx_retries_same_account_after_sleep(monkeypatch):
    """On 5xx the helper sleeps 5 s then retries (pool may give same account back)."""
    pool = make_pool([{"account_id": "A"}, {"account_id": "A"}])

    fetcher = AsyncMock(side_effect=[
        XapiError("server error", status_code=503),
        {"items": []},
    ])
    sleep_calls: list[float] = []

    async def fast_sleep(d: float) -> None:
        sleep_calls.append(d)

    monkeypatch.setattr("app.tasks.polling.asyncio.sleep", fast_sleep)

    result = await fetch_with_pool(fetcher_fn=fetcher, pool=pool, max_attempts=2)

    assert result == {"items": []}
    assert sleep_calls == [5]


@pytest.mark.asyncio
async def test_pool_drained_returns_none():
    """When the pool has no accounts available, fetch_with_pool returns None immediately."""
    pool = make_pool([])
    fetcher = AsyncMock()

    result = await fetch_with_pool(fetcher_fn=fetcher, pool=pool)

    assert result is None
    fetcher.assert_not_called()


@pytest.mark.asyncio
async def test_max_attempts_exhausted_raises_last_error():
    """When all attempts fail with 403, the last XapiError is re-raised."""
    pool = make_pool([{"account_id": "A"}, {"account_id": "B"}])
    fetcher = AsyncMock(side_effect=[
        XapiError("firewall", status_code=403),
        XapiError("firewall", status_code=403),
    ])

    with pytest.raises(XapiError) as exc_info:
        await fetch_with_pool(fetcher_fn=fetcher, pool=pool, max_attempts=2)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_non_retryable_error_raised_immediately():
    """A 404 (non-retryable) is raised on the first attempt, no retry attempted."""
    pool = make_pool([{"account_id": "A"}, {"account_id": "B"}])
    fetcher = AsyncMock(side_effect=[
        XapiError("not found", status_code=404),
    ])

    with pytest.raises(XapiError) as exc_info:
        await fetch_with_pool(fetcher_fn=fetcher, pool=pool, max_attempts=2)

    assert exc_info.value.status_code == 404
    # Only one report call — the failed one
    assert pool.report.await_count == 1
    assert pool.report.await_args_list[0].args[:2] == ("A", 404)
    # Only one fetcher call — no retry
    assert fetcher.await_count == 1


@pytest.mark.asyncio
async def test_success_on_first_attempt():
    """Happy path: single successful fetch, report called with 200."""
    pool = make_pool([{"account_id": "A"}])
    fetcher = AsyncMock(return_value={"items": [1, 2, 3], "total": 3})

    result = await fetch_with_pool(fetcher_fn=fetcher, pool=pool)

    assert result == {"items": [1, 2, 3], "total": 3}
    pool.report.assert_awaited_once_with("A", 200)

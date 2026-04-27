"""Unit tests for the activity-simulator action coroutines.

All upstream xapi calls are mocked via ``respx``; persistence is patched out
so the tests don't need a live Postgres.
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from app.services.activity_simulator import actions as actions_mod
from app.services.activity_simulator.actions import (
    ITEM_ID_CACHE,
    action_get_chats,
    action_get_listing_detail,
    action_get_unread_count,
    action_open_random_chat_and_read,
    run_action,
)
from app.services.health_checker.xapi_client import XapiClient

XAPI_BASE = "http://xapi.test"


def make_client() -> XapiClient:
    return XapiClient(base_url=XAPI_BASE, api_key="test-key")


@pytest.fixture(autouse=True)
def reset_cache_and_persist(monkeypatch):
    """Each test starts with a clean item-id cache and a no-op persister."""
    ITEM_ID_CACHE.clear()
    persisted: list[Any] = []

    async def fake_persist(result):
        persisted.append(result)

    monkeypatch.setattr(actions_mod, "_persist_safely", fake_persist)
    yield persisted
    ITEM_ID_CACHE.clear()


# ----------------------------------------------------------------------
# get_chats
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_get_chats_ok_refills_item_cache() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(
            200,
            json={
                "channels": [
                    {"id": "u2i-1", "context": {"value": {"id": "111"}}},
                    {"id": "u2i-2", "context": {"value": {"id": "222"}}},
                ]
            },
        )
    )
    result = await action_get_chats(make_client())
    assert result.action == "get_chats"
    assert result.status == "ok"
    assert result.details["returned_channels"] == 2
    assert "111" in ITEM_ID_CACHE
    assert "222" in ITEM_ID_CACHE


@respx.mock
@pytest.mark.asyncio
async def test_get_chats_5xx_marks_error() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(503, json={"detail": "boom"})
    )
    result = await action_get_chats(make_client())
    assert result.status == "error"
    assert result.details["status_code"] == 503
    assert "HTTP 503" in result.details.get("error", "")


@respx.mock
@pytest.mark.asyncio
async def test_get_chats_429_marks_rate_limited() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(429, json={"detail": "slow down"})
    )
    result = await action_get_chats(make_client())
    assert result.status == "rate_limited"


# ----------------------------------------------------------------------
# get_unread_count
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_get_unread_count_ok() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/unread-count").mock(
        return_value=httpx.Response(200, json={"count": 7})
    )
    result = await action_get_unread_count(make_client())
    assert result.status == "ok"
    assert result.details["unread_count"] == 7


@respx.mock
@pytest.mark.asyncio
async def test_get_unread_count_5xx_error() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/unread-count").mock(
        return_value=httpx.Response(500, json={"detail": "down"})
    )
    result = await action_get_unread_count(make_client())
    assert result.status == "error"
    assert result.details["status_code"] == 500


# ----------------------------------------------------------------------
# get_listing_detail
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_listing_detail_skips_when_cache_empty(reset_cache_and_persist) -> None:
    """No item_id seen yet => action returns ``skipped``, no row written, no exc."""
    persisted = reset_cache_and_persist
    result = await action_get_listing_detail(make_client())
    assert result.status == "skipped"
    assert result.details["reason"] == "item_id_cache empty"
    # ``run_action`` is what calls _persist; the bare action does not, so
    # persisted is empty either way. We verify the run_action wrapper too.
    persisted.clear()
    result = await run_action("get_listing_detail", make_client())
    assert result.status == "skipped"
    assert persisted == []  # skipped actions must NOT write to activity_log


@respx.mock
@pytest.mark.asyncio
async def test_get_listing_detail_ok_with_cache() -> None:
    ITEM_ID_CACHE.append("123456")
    respx.get(f"{XAPI_BASE}/api/v1/items/123456").mock(
        return_value=httpx.Response(200, json={"id": "123456", "title": "X"})
    )
    result = await action_get_listing_detail(make_client())
    assert result.status == "ok"
    assert result.target == "123456"
    assert result.details["status_code"] == 200


@respx.mock
@pytest.mark.asyncio
async def test_get_listing_detail_5xx_error() -> None:
    ITEM_ID_CACHE.append("999")
    respx.get(f"{XAPI_BASE}/api/v1/items/999").mock(
        return_value=httpx.Response(500, json={"detail": "boom"})
    )
    result = await action_get_listing_detail(make_client())
    assert result.status == "error"
    assert result.target == "999"


# ----------------------------------------------------------------------
# open_random_chat_and_read — chained
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_open_random_chat_and_read_chains_three_calls() -> None:
    list_route = respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(
            200, json={"channels": [{"id": "u2i-abc", "context": {"value": {"id": "555"}}}]}
        )
    )
    msg_route = respx.get(
        f"{XAPI_BASE}/api/v1/messenger/channels/u2i-abc/messages"
    ).mock(return_value=httpx.Response(200, json={"messages": []}))
    read_route = respx.post(
        f"{XAPI_BASE}/api/v1/messenger/channels/u2i-abc/read"
    ).mock(return_value=httpx.Response(200, json={"status": "ok"}))

    result = await action_open_random_chat_and_read(make_client())
    assert result.status == "ok"
    assert result.target == "u2i-abc"
    assert list_route.called
    assert msg_route.called
    assert read_route.called
    assert result.details["read_status_code"] == 200


@respx.mock
@pytest.mark.asyncio
async def test_open_random_chat_and_read_skip_when_no_channels() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(200, json={"channels": []})
    )
    result = await action_open_random_chat_and_read(make_client())
    assert result.status == "skipped"
    assert result.details["reason"] == "no channels"


@respx.mock
@pytest.mark.asyncio
async def test_open_random_chat_and_read_error_on_read_5xx() -> None:
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels").mock(
        return_value=httpx.Response(200, json={"channels": [{"id": "u2i-zzz"}]})
    )
    respx.get(
        f"{XAPI_BASE}/api/v1/messenger/channels/u2i-zzz/messages"
    ).mock(return_value=httpx.Response(200, json={"messages": []}))
    respx.post(
        f"{XAPI_BASE}/api/v1/messenger/channels/u2i-zzz/read"
    ).mock(return_value=httpx.Response(503, json={"detail": "down"}))

    result = await action_open_random_chat_and_read(make_client())
    assert result.status == "error"
    assert result.target == "u2i-zzz"
    assert result.details["read_status_code"] == 503


# ----------------------------------------------------------------------
# run_action wrapper persists
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_run_action_persists_on_ok(reset_cache_and_persist) -> None:
    persisted = reset_cache_and_persist
    respx.get(f"{XAPI_BASE}/api/v1/messenger/unread-count").mock(
        return_value=httpx.Response(200, json={"count": 0})
    )
    result = await run_action("get_unread_count", make_client())
    assert result.status == "ok"
    assert len(persisted) == 1
    assert persisted[0].action == "get_unread_count"


@pytest.mark.asyncio
async def test_run_action_unknown_raises() -> None:
    with pytest.raises(KeyError):
        await run_action("not_a_real_action", make_client())

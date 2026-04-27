"""Unit tests for whitelist (is-my-listing) lookups."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.config import Settings
from app.services.health_checker.xapi_client import XapiClient
from app.services.messenger_bot.whitelist import (
    fetch_item_id_for_channel,
    fetch_own_user_id,
    is_my_listing,
)

XAPI_BASE = "http://xapi.test"


def make_client() -> XapiClient:
    return XapiClient(base_url=XAPI_BASE, api_key="test-key")


def make_settings(**overrides) -> Settings:
    base = {
        "app_secret_key": "x" * 32,
        "database_url": "postgresql+asyncpg://t:t@localhost/t",
        "avito_own_user_id": None,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# fetch_own_user_id — env override / cache / xapi paths
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_own_user_id_uses_env_override():
    s = make_settings(avito_own_user_id=42)
    user_id = await fetch_own_user_id(make_client(), s)
    assert user_id == 42


@respx.mock
@pytest.mark.asyncio
async def test_fetch_own_user_id_resolves_from_xapi():
    respx.get(f"{XAPI_BASE}/api/v1/sessions/current").mock(
        return_value=httpx.Response(200, json={"is_active": True, "user_id": 9001})
    )
    user_id = await fetch_own_user_id(make_client(), make_settings())
    assert user_id == 9001


@respx.mock
@pytest.mark.asyncio
async def test_fetch_own_user_id_returns_none_on_5xx():
    respx.get(f"{XAPI_BASE}/api/v1/sessions/current").mock(
        return_value=httpx.Response(503, json={"detail": "down"})
    )
    user_id = await fetch_own_user_id(make_client(), make_settings())
    assert user_id is None


@respx.mock
@pytest.mark.asyncio
async def test_fetch_own_user_id_caches_result():
    """Second call must NOT hit xapi."""
    route = respx.get(f"{XAPI_BASE}/api/v1/sessions/current").mock(
        return_value=httpx.Response(200, json={"is_active": True, "user_id": 7})
    )
    first = await fetch_own_user_id(make_client(), make_settings())
    second = await fetch_own_user_id(make_client(), make_settings())
    assert first == 7
    assert second == 7
    assert route.call_count == 1  # cached on second call


# ----------------------------------------------------------------------
# fetch_item_id_for_channel
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_fetch_item_id_extracts_from_info():
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels/u2i-abc").mock(
        return_value=httpx.Response(
            200, json={"id": "u2i-abc", "info": {"item_id": 555}}
        )
    )
    item_id = await fetch_item_id_for_channel("u2i-abc", make_client())
    assert item_id == 555


@respx.mock
@pytest.mark.asyncio
async def test_fetch_item_id_returns_none_on_404():
    respx.get(f"{XAPI_BASE}/api/v1/messenger/channels/u2i-zzz").mock(
        return_value=httpx.Response(404, json={"detail": "no channel"})
    )
    item_id = await fetch_item_id_for_channel("u2i-zzz", make_client())
    assert item_id is None


# ----------------------------------------------------------------------
# is_my_listing — yes / no / unknown verdicts
# ----------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_is_my_listing_yes_when_seller_matches():
    respx.get(f"{XAPI_BASE}/api/v1/items/123").mock(
        return_value=httpx.Response(200, json={"id": 123, "seller_id": 7})
    )
    verdict = await is_my_listing(item_id=123, own_user_id=7, client=make_client())
    assert verdict == "yes"


@respx.mock
@pytest.mark.asyncio
async def test_is_my_listing_no_when_different_seller():
    respx.get(f"{XAPI_BASE}/api/v1/items/123").mock(
        return_value=httpx.Response(200, json={"id": 123, "seller_id": 999})
    )
    verdict = await is_my_listing(item_id=123, own_user_id=7, client=make_client())
    assert verdict == "no"


@respx.mock
@pytest.mark.asyncio
async def test_is_my_listing_unknown_when_seller_field_missing():
    respx.get(f"{XAPI_BASE}/api/v1/items/123").mock(
        return_value=httpx.Response(200, json={"id": 123, "title": "X"})
    )
    verdict = await is_my_listing(item_id=123, own_user_id=7, client=make_client())
    assert verdict == "unknown"


@respx.mock
@pytest.mark.asyncio
async def test_is_my_listing_unknown_on_5xx():
    respx.get(f"{XAPI_BASE}/api/v1/items/123").mock(
        return_value=httpx.Response(500, json={"detail": "boom"})
    )
    verdict = await is_my_listing(item_id=123, own_user_id=7, client=make_client())
    assert verdict == "unknown"


@pytest.mark.asyncio
async def test_is_my_listing_unknown_when_inputs_missing():
    verdict = await is_my_listing(item_id=None, own_user_id=7, client=make_client())
    assert verdict == "unknown"
    verdict = await is_my_listing(item_id=123, own_user_id=None, client=make_client())
    assert verdict == "unknown"

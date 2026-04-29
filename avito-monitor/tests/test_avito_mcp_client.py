"""Tests for AvitoMcpClient: account_id pool-aware routing (T17a).

Verifies that:
- AvitoMcpClient accepts an optional ``account_id`` constructor param.
- fetch_subscription_items includes ``account_id`` query param when set.
- fetch_subscription_items omits ``account_id`` query param when not set (backward compat).
"""
from __future__ import annotations

import httpx
import pytest
import respx

from avito_mcp.config import McpSettings
from app.integrations.avito_mcp_client.client import AvitoMcpClient

XAPI_BASE = "http://xapi.test"
_SETTINGS = McpSettings(
    avito_xapi_url=XAPI_BASE,
    avito_xapi_api_key="test-key",
)

_EMPTY_PAGE = {
    "items": [],
    "total": 0,
    "page": 1,
    "has_more": False,
}


# ── fetch_subscription_items: account_id forwarded ───────────────────────

@pytest.mark.asyncio
async def test_fetch_subscription_items_includes_account_id_when_set():
    """When AvitoMcpClient is constructed with account_id, xapi receives it as ?account_id=."""
    with respx.mock(base_url=XAPI_BASE) as m:
        route = m.get("/api/v1/subscriptions/12345/items").mock(
            return_value=httpx.Response(200, json=_EMPTY_PAGE)
        )
        async with AvitoMcpClient(settings=_SETTINGS, account_id="acc-XYZ") as client:
            await client.fetch_subscription_items(12345)

        assert route.called
        sent_url = str(route.calls.last.request.url)
        assert "account_id=acc-XYZ" in sent_url


@pytest.mark.asyncio
async def test_fetch_subscription_items_omits_account_id_when_none():
    """Backward compat: omitting account_id sends no account_id query param."""
    with respx.mock(base_url=XAPI_BASE) as m:
        route = m.get("/api/v1/subscriptions/12345/items").mock(
            return_value=httpx.Response(200, json=_EMPTY_PAGE)
        )
        async with AvitoMcpClient(settings=_SETTINGS) as client:
            await client.fetch_subscription_items(12345)

        assert route.called
        sent_url = str(route.calls.last.request.url)
        assert "account_id" not in sent_url


@pytest.mark.asyncio
async def test_fetch_subscription_items_page_param_still_sent():
    """page param is always forwarded regardless of account_id."""
    with respx.mock(base_url=XAPI_BASE) as m:
        route = m.get("/api/v1/subscriptions/42/items").mock(
            return_value=httpx.Response(200, json=_EMPTY_PAGE)
        )
        async with AvitoMcpClient(settings=_SETTINGS, account_id="acc-A") as client:
            await client.fetch_subscription_items(42, page=3)

        assert route.called
        sent_url = str(route.calls.last.request.url)
        assert "page=3" in sent_url
        assert "account_id=acc-A" in sent_url


# ── constructor backward compat ───────────────────────────────────────────

def test_avito_mcp_client_default_account_id_is_none():
    """Default account_id is None — no regression for existing callers."""
    client = AvitoMcpClient(settings=_SETTINGS)
    assert client._account_id is None


def test_avito_mcp_client_account_id_stored():
    """Explicit account_id is stored on the instance."""
    client = AvitoMcpClient(settings=_SETTINGS, account_id="acc-123")
    assert client._account_id == "acc-123"


def test_avito_mcp_client_settings_only_still_works():
    """Existing call-site: AvitoMcpClient(settings=...) still accepted."""
    client = AvitoMcpClient(settings=_SETTINGS)
    assert client._settings is _SETTINGS
    assert client._account_id is None

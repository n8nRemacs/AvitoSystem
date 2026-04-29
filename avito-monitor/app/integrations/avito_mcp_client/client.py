"""Typed client used by the backend (Block 4 worker) to call avito-mcp tools.

For V1 we keep things simple: the backend and avito-mcp live in the same repo,
so this client just calls the tool ``_impl`` functions directly with a shared
``XapiClient``. That avoids spinning up an extra MCP-over-HTTP hop for every
worker tick.

If/when avito-mcp is split out into its own deployable, swap the body of these
methods for an MCP SDK client over SSE — the public signatures here are stable.
"""
from __future__ import annotations

import httpx

from avito_mcp.config import McpSettings, get_mcp_settings
from avito_mcp.integrations.xapi_client import XapiClient
from avito_mcp.tools.listings import (
    avito_get_listing_images_impl,
    avito_get_listing_impl,
)
from avito_mcp.tools.search import avito_fetch_search_page_impl
from avito_mcp.tools.service import avito_health_check_impl
from shared.models.avito import (
    HealthStatus,
    ListingDetail,
    ListingImage,
    SearchPage,
)


class AvitoMcpClientError(RuntimeError):
    pass


class AvitoMcpClient:
    """Thin async client around the four avito_mcp tools.

    Designed for use as an async context manager so callers can share one
    underlying ``httpx.AsyncClient`` across many tool calls within the same
    worker tick:

    .. code-block:: python

        async with AvitoMcpClient() as client:
            page = await client.fetch_search_page(url)
            for item in page.items:
                detail = await client.get_listing(item.id)
    """

    def __init__(self, settings: McpSettings | None = None) -> None:
        self._settings = settings or get_mcp_settings()
        self._http: httpx.AsyncClient | None = None
        self._xapi: XapiClient | None = None

    async def __aenter__(self) -> AvitoMcpClient:
        self._http = httpx.AsyncClient(
            base_url=self._settings.avito_xapi_url.rstrip("/"),
            timeout=self._settings.avito_xapi_timeout_seconds,
            headers={
                "X-Api-Key": self._settings.avito_xapi_api_key,
                "User-Agent": self._settings.avito_mcp_user_agent,
                "Accept": "application/json",
            },
        )
        self._xapi = XapiClient(self._settings, client=self._http)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._http is not None:
            await self._http.aclose()
        self._http = None
        self._xapi = None

    def _client(self) -> XapiClient:
        if self._xapi is None:
            # Allow non-context-manager usage; will create per-call clients.
            return XapiClient(self._settings)
        return self._xapi

    # --- public API ---------------------------------------------------

    async def fetch_search_page(self, url: str, page: int = 1) -> SearchPage:
        return await avito_fetch_search_page_impl(url, page, client=self._client())

    async def fetch_subscription_items(
        self, filter_id: int, page: int = 1
    ) -> SearchPage:
        from avito_mcp.tools.search import avito_fetch_subscription_items_impl

        return await avito_fetch_subscription_items_impl(
            filter_id, page, client=self._client()
        )

    async def get_listing(self, item_id_or_url: int | str) -> ListingDetail:
        return await avito_get_listing_impl(item_id_or_url, client=self._client())

    async def get_listing_images(self, item_id: int | str) -> list[ListingImage]:
        return await avito_get_listing_images_impl(item_id, client=self._client())

    async def health_check(self) -> HealthStatus:
        return await avito_health_check_impl(client=self._client())

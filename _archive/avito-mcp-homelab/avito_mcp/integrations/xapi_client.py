"""Async HTTP client for avito-xapi (port 8080 by default).

Wraps the three endpoints we need:
- GET /api/v1/search/items     — list search
- GET /api/v1/search/items/{id} — item detail
- GET /api/v1/sessions/current  — session health (used by avito_health_check)
"""
from __future__ import annotations

from typing import Any

import httpx

from avito_mcp.config import McpSettings, get_mcp_settings


class XapiError(RuntimeError):
    """Raised when avito-xapi returns a non-2xx response or is unreachable."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 detail: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class XapiClient:
    """Tiny async client around avito-xapi.

    All methods raise XapiError on transport / HTTP errors; otherwise return the
    decoded JSON dict from xapi (already normalised by xapi's routers).
    """

    def __init__(
        self,
        settings: McpSettings | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_mcp_settings()
        self._client_override = client

    # --- low-level ----------------------------------------------------

    def _make_client(self) -> httpx.AsyncClient:
        if self._client_override is not None:
            return self._client_override
        return httpx.AsyncClient(
            base_url=self.settings.avito_xapi_url.rstrip("/"),
            timeout=self.settings.avito_xapi_timeout_seconds,
            headers={
                "X-Api-Key": self.settings.avito_xapi_api_key,
                "User-Agent": self.settings.avito_mcp_user_agent,
                "Accept": "application/json",
            },
        )

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        client = self._make_client()
        owns_client = self._client_override is None
        try:
            try:
                resp = await client.get(path, params=_clean_params(params or {}))
            except httpx.HTTPError as exc:  # connect, read timeout, DNS
                raise XapiError(f"transport error calling xapi {path}: {exc}") from exc

            if resp.status_code >= 400:
                detail: Any
                try:
                    detail = resp.json()
                except ValueError:
                    detail = resp.text
                raise XapiError(
                    f"xapi {path} -> HTTP {resp.status_code}",
                    status_code=resp.status_code,
                    detail=detail,
                )
            try:
                return resp.json()
            except ValueError as exc:
                raise XapiError(f"xapi {path} returned non-JSON body") from exc
        finally:
            if owns_client:
                await client.aclose()

    # --- public methods ----------------------------------------------

    async def search_items(
        self,
        query: str,
        *,
        price_min: int | None = None,
        price_max: int | None = None,
        location_id: int | None = None,
        category_id: int | None = None,
        sort: str | None = None,
        page: int = 1,
        per_page: int = 30,
        with_delivery: bool | None = None,
    ) -> dict[str, Any]:
        """Call GET /api/v1/search/items. Returns raw normalised dict."""
        params: dict[str, Any] = {
            "query": query,
            "price_min": price_min,
            "price_max": price_max,
            "location_id": location_id,
            "category_id": category_id,
            "sort": sort,
            "page": page,
            "per_page": per_page,
            "with_delivery": with_delivery,
        }
        return await self._get("/api/v1/search/items", params)

    async def get_item(self, item_id: int) -> dict[str, Any]:
        """Call GET /api/v1/search/items/{id}. Returns ItemDetail dict."""
        return await self._get(f"/api/v1/search/items/{int(item_id)}")

    async def health(self) -> dict[str, Any]:
        """Call GET /api/v1/sessions/current. Returns session status dict.

        Note xapi exposes this under /sessions/current (not /sessions/status).
        Output shape: { is_active, ttl_seconds, ttl_human, expires_at, ... }
        """
        return await self._get("/api/v1/sessions/current")

    async def health_root(self) -> dict[str, Any]:
        """Call GET /health (no auth). Used to detect xapi reachability."""
        return await self._get("/health")


def _clean_params(p: dict[str, Any]) -> dict[str, Any]:
    """Drop None values so httpx doesn't send them as the literal string 'None'."""
    return {k: v for k, v in p.items() if v is not None}

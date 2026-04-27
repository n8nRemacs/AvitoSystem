"""HTTP client for avito-xapi backend."""
import httpx
from typing import Any

from config import settings


class XApiClient:
    """Proxy calls to avito-xapi REST API."""

    def __init__(self):
        self._base = settings.xapi_base_url.rstrip("/")
        self._headers = {
            "X-Api-Key": settings.xapi_api_key,
            "Content-Type": "application/json",
        }
        self._http = httpx.AsyncClient(timeout=30.0, headers=self._headers)

    async def close(self):
        await self._http.aclose()

    # ── Search ──────────────────────────────────────────

    async def search_items(
        self,
        query: str,
        price_min: int | None = None,
        price_max: int | None = None,
        location_id: int | None = None,
        category_id: int | None = None,
        sort: str | None = None,
        page: int = 1,
        per_page: int = 30,
        with_delivery: bool | None = None,
        owner: str | None = None,
        search_area: str | None = None,
        radius: int | None = None,
        force_location: bool | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"query": query, "page": page, "per_page": per_page}
        if price_min is not None:
            params["price_min"] = price_min
        if price_max is not None:
            params["price_max"] = price_max
        if location_id is not None:
            params["location_id"] = location_id
        if category_id is not None:
            params["category_id"] = category_id
        if sort:
            params["sort"] = sort
        if with_delivery is not None:
            params["with_delivery"] = with_delivery
        if owner:
            params["owner"] = owner
        if search_area:
            params["search_area"] = search_area
        if radius is not None:
            params["radius"] = radius
        if force_location is not None:
            params["force_location"] = force_location

        resp = await self._http.get(f"{self._base}/search/items", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_item(self, item_id: int) -> dict[str, Any]:
        resp = await self._http.get(f"{self._base}/search/items/{item_id}")
        resp.raise_for_status()
        return resp.json()

    # ── Messenger ───────────────────────────────────────

    async def get_channels(
        self, limit: int = 30, offset_timestamp: int | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if offset_timestamp:
            params["offset_timestamp"] = offset_timestamp
        resp = await self._http.get(f"{self._base}/messenger/channels", params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_messages(
        self, channel_id: str, limit: int = 50, offset_id: str | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if offset_id:
            params["offset_id"] = offset_id
        resp = await self._http.get(
            f"{self._base}/messenger/channels/{channel_id}/messages", params=params
        )
        resp.raise_for_status()
        return resp.json()

    async def send_message(self, channel_id: str, text: str) -> dict[str, Any]:
        resp = await self._http.post(
            f"{self._base}/messenger/channels/{channel_id}/messages",
            json={"text": text},
        )
        resp.raise_for_status()
        return resp.json()

    async def create_channel_by_item(self, item_id: str) -> dict[str, Any]:
        resp = await self._http.post(
            f"{self._base}/messenger/channels/by-item",
            json={"item_id": item_id},
        )
        resp.raise_for_status()
        return resp.json()

    async def mark_read(self, channel_id: str) -> dict[str, Any]:
        resp = await self._http.post(
            f"{self._base}/messenger/channels/{channel_id}/read"
        )
        resp.raise_for_status()
        return resp.json()

    async def get_unread_count(self) -> dict[str, Any]:
        resp = await self._http.get(f"{self._base}/messenger/unread-count")
        resp.raise_for_status()
        return resp.json()

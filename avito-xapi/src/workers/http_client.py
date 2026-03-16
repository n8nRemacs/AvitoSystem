"""All HTTP REST calls to Avito API."""
import uuid
from datetime import datetime, timezone
from typing import Any

from src.workers.base_client import BaseAvitoClient


class AvitoHttpClient(BaseAvitoClient):
    """HTTP client for Avito REST API endpoints."""

    # ── Messenger ────────────────────────────────────────

    async def get_channels(self, limit: int = 30, offset_timestamp: int | None = None,
                           category: int = 1) -> dict[str, Any]:
        await self.rate_limiter.wait_and_acquire()
        payload: dict[str, Any] = {
            "category": category,
            "filters": {"anyTags": [], "excludeTags": []},
            "limit": limit,
        }
        if offset_timestamp:
            payload["offsetTimestamp"] = offset_timestamp

        resp = self.http.post(
            f"{self.BASE_URL}/1/messenger/getChannels",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_channel_by_id(self, channel_id: str) -> dict[str, Any]:
        await self.rate_limiter.wait_and_acquire()
        resp = self.http.post(
            f"{self.BASE_URL}/1/messenger/getChannelById",
            headers=self._headers(),
            json={"channelId": channel_id},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_messages(self, channel_id: str, limit: int = 50,
                           offset_id: str | None = None) -> dict[str, Any]:
        await self.rate_limiter.wait_and_acquire()
        payload: dict[str, Any] = {
            "channelId": channel_id,
            "limit": limit,
            "order": 0,
        }
        if offset_id:
            payload["offsetId"] = offset_id

        resp = self.http.post(
            f"{self.BASE_URL}/1/messenger/getUserVisibleMessages",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def send_text(self, channel_id: str, text: str) -> dict[str, Any]:
        await self.rate_limiter.wait_and_acquire()
        resp = self.http.post(
            f"{self.BASE_URL}/1/messenger/sendTextMessage",
            headers=self._headers(),
            json={
                "channelId": channel_id,
                "text": text,
                "idempotencyKey": str(uuid.uuid4()),
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def mark_read(self, channel_ids: list[str], category: int = 1) -> dict[str, Any]:
        await self.rate_limiter.wait_and_acquire()
        resp = self.http.post(
            f"{self.BASE_URL}/1/messenger/readChats",
            headers=self._headers(),
            json={"channelIds": channel_ids, "category": category},
        )
        resp.raise_for_status()
        return resp.json()

    async def send_typing(self, channel_id: str) -> dict[str, Any]:
        await self.rate_limiter.wait_and_acquire()
        resp = self.http.post(
            f"{self.BASE_URL}/1/messenger/typing",
            headers=self._headers(),
            json={"channelId": channel_id},
        )
        resp.raise_for_status()
        return resp.json()

    async def create_channel_by_item(self, item_id: str) -> dict[str, Any]:
        await self.rate_limiter.wait_and_acquire()
        resp = self.http.post(
            f"{self.BASE_URL}/1/messenger/createItemChannel",
            headers=self._headers(),
            json={"itemId": item_id},
        )
        resp.raise_for_status()
        return resp.json()

    async def create_channel_by_user(self, user_hash: str) -> dict[str, Any]:
        await self.rate_limiter.wait_and_acquire()
        resp = self.http.post(
            f"{self.BASE_URL}/1/messenger/createUserChannel",
            headers=self._headers(),
            json={"userHash": user_hash},
        )
        resp.raise_for_status()
        return resp.json()

    async def get_unread_count(self) -> dict[str, Any]:
        await self.rate_limiter.wait_and_acquire()
        resp = self.http.post(
            f"{self.BASE_URL}/1/messenger/getUnreadCount",
            headers=self._headers(),
            json={},
        )
        resp.raise_for_status()
        return resp.json()

    # ── Calls ────────────────────────────────────────────

    async def get_call_history(self, date_from: str | None = None,
                               date_to: str | None = None,
                               limit: int = 20, offset: int = 0) -> dict[str, Any]:
        await self.rate_limiter.wait_and_acquire()
        now = datetime.now(timezone.utc)
        if not date_to:
            date_to = now.strftime("%Y-%m-%d")
        if not date_from:
            from datetime import timedelta
            date_from = (now - timedelta(days=365)).strftime("%Y-%m-%d")

        # Calltracking uses www.avito.ru
        resp = self.http.post(
            "https://www.avito.ru/web/1/calltracking-pro/history",
            headers=self._headers(),
            json={
                "dateFrom": date_from,
                "dateTo": date_to,
                "limit": limit,
                "offset": offset,
                "sortingField": "createTime",
                "sortingDirection": "desc",
                "newOrRepeated": "all",
                "receivedOrMissed": "all",
                "showSpam": True,
                "itemFilters": {},
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def get_call_recording(self, call_id: str) -> bytes:
        await self.rate_limiter.wait_and_acquire()
        resp = self.http.get(
            f"https://www.avito.ru/web/1/calltracking-pro/audio?historyId={call_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.content

    # ── Search ───────────────────────────────────────────

    async def search_items(self, query: str, price_min: int | None = None,
                           price_max: int | None = None,
                           location_id: int | None = None,
                           category_id: int | None = None,
                           sort: str | None = None,
                           page: int = 1, per_page: int = 30) -> dict[str, Any]:
        await self.rate_limiter.wait_and_acquire()
        params: dict[str, Any] = {
            "query": query,
            "page": page,
            "count": per_page,
        }
        if price_min is not None:
            params["priceMin"] = price_min
        if price_max is not None:
            params["priceMax"] = price_max
        if location_id is not None:
            params["locationId"] = location_id
        if category_id is not None:
            params["categoryId"] = category_id
        if sort:
            params["sort"] = sort

        resp = self.http.get(
            f"{self.BASE_URL}/11/items",
            headers=self._headers(),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_item_details(self, item_id: int) -> dict[str, Any]:
        await self.rate_limiter.wait_and_acquire()
        resp = self.http.get(
            f"{self.BASE_URL}/19/items/{item_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

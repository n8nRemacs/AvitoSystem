"""AccountPool — тонкая обёртка над xapi /api/v1/accounts/* эндпойнтами."""
from contextlib import asynccontextmanager
import logging

import httpx

log = logging.getLogger(__name__)


class NoAvailableAccountError(Exception):
    def __init__(self, detail: dict):
        self.detail = detail
        super().__init__(detail.get("error", "no available account"))


class AccountNotAvailableError(Exception):
    def __init__(self, account_id: str, state: str):
        self.account_id = account_id
        self.state = state
        super().__init__(f"account {account_id} is in state={state}")


class AccountPool:
    def __init__(self, xapi_client: httpx.AsyncClient):
        self.xapi = xapi_client

    @asynccontextmanager
    async def claim_for_poll(self):
        resp = await self.xapi.post("/api/v1/accounts/poll-claim", json={})
        if resp.status_code == 409:
            raise NoAvailableAccountError(resp.json().get("detail", {}))
        resp.raise_for_status()
        yield resp.json()

    async def report(self, account_id: str, status_code: int, body: str | None = None):
        body_excerpt = (body or "")[:1024] or None
        resp = await self.xapi.post(
            f"/api/v1/accounts/{account_id}/report",
            json={"status_code": status_code, "body_excerpt": body_excerpt},
        )
        resp.raise_for_status()

    async def claim_for_sync(self, account_id: str) -> dict:
        resp = await self.xapi.get(f"/api/v1/accounts/{account_id}/session-for-sync")
        if resp.status_code == 409:
            raise AccountNotAvailableError(
                account_id,
                resp.json().get("detail", {}).get("state", "unknown"),
            )
        resp.raise_for_status()
        return resp.json()

    async def list_active_accounts(self) -> list[dict]:
        resp = await self.xapi.get("/api/v1/accounts")
        resp.raise_for_status()
        return [a for a in resp.json() if a.get("state") == "active"]

    async def list_all_accounts(self) -> list[dict]:
        resp = await self.xapi.get("/api/v1/accounts")
        resp.raise_for_status()
        return resp.json()

    async def trigger_refresh_cycle(self, account_id: str) -> dict:
        """Используется monitor health_checker для запуска refresh."""
        resp = await self.xapi.post(f"/api/v1/accounts/{account_id}/refresh-cycle")
        resp.raise_for_status()
        return resp.json()

    async def patch_state(self, account_id: str, state: str, reason: str | None = None):
        resp = await self.xapi.patch(
            f"/api/v1/accounts/{account_id}/state",
            json={"state": state, "reason": reason},
        )
        resp.raise_for_status()

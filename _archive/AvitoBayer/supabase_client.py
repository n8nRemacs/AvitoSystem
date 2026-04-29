"""Lightweight Supabase client for leads, saved_searches, processing_rules."""
import httpx
from typing import Any
from datetime import datetime, timezone

from config import settings


class SupabaseClient:
    """Direct PostgREST client."""

    def __init__(self):
        self._url = settings.supabase_url.rstrip("/")
        self._http = httpx.AsyncClient(timeout=30.0)

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        h = {
            "apikey": settings.supabase_key,
            "Authorization": f"Bearer {settings.supabase_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            h["Prefer"] = prefer
        return h

    def _rest(self, table: str) -> str:
        return f"{self._url}/rest/v1/{table}"

    # ── Saved Searches ──────────────────────────────────

    async def create_search(self, data: dict[str, Any]) -> dict[str, Any]:
        data.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        data.setdefault("is_active", True)
        data.setdefault("search_type", "buy")
        resp = await self._http.post(
            self._rest("saved_searches"),
            json=data,
            headers=self._headers(prefer="return=representation"),
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if isinstance(rows, list) and rows else rows

    async def get_searches(
        self, active_only: bool = True, search_type: str | None = None
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "select": "*,search_processing_rules(*)",
            "order": "created_at.desc",
        }
        if active_only:
            params["is_active"] = "eq.true"
        if search_type:
            params["search_type"] = f"eq.{search_type}"
        resp = await self._http.get(
            self._rest("saved_searches"), params=params, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    async def get_search(self, search_id: str) -> dict[str, Any] | None:
        resp = await self._http.get(
            self._rest("saved_searches"),
            params={
                "id": f"eq.{search_id}",
                "select": "*,search_processing_rules(*)",
                "limit": "1",
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else None

    async def update_search(self, search_id: str, data: dict[str, Any]) -> dict[str, Any]:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        resp = await self._http.patch(
            self._rest("saved_searches"),
            params={"id": f"eq.{search_id}"},
            json=data,
            headers=self._headers(prefer="return=representation"),
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if isinstance(rows, list) and rows else rows

    async def delete_search(self, search_id: str) -> bool:
        resp = await self._http.delete(
            self._rest("saved_searches"),
            params={"id": f"eq.{search_id}"},
            headers=self._headers(),
        )
        resp.raise_for_status()
        return True

    # ── Processing Rules ────────────────────────────────

    async def get_rules(self, search_type: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, str] = {"select": "*", "order": "created_at.desc"}
        if search_type:
            params["search_type"] = f"eq.{search_type}"
        resp = await self._http.get(
            self._rest("search_processing_rules"),
            params=params,
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def create_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        data.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        resp = await self._http.post(
            self._rest("search_processing_rules"),
            json=data,
            headers=self._headers(prefer="return=representation"),
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if isinstance(rows, list) and rows else rows

    async def update_rule(self, rule_id: str, data: dict[str, Any]) -> dict[str, Any]:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        resp = await self._http.patch(
            self._rest("search_processing_rules"),
            params={"id": f"eq.{rule_id}"},
            json=data,
            headers=self._headers(prefer="return=representation"),
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if isinstance(rows, list) and rows else rows

    # ── Search Runs (history) ───────────────────────────

    async def create_run(self, data: dict[str, Any]) -> dict[str, Any]:
        data.setdefault("run_at", datetime.now(timezone.utc).isoformat())
        resp = await self._http.post(
            self._rest("search_runs"),
            json=data,
            headers=self._headers(prefer="return=representation"),
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if isinstance(rows, list) and rows else rows

    async def get_runs(
        self, search_id: str, limit: int = 20
    ) -> list[dict[str, Any]]:
        resp = await self._http.get(
            self._rest("search_runs"),
            params={
                "search_id": f"eq.{search_id}",
                "select": "*",
                "order": "run_at.desc",
                "limit": str(limit),
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    # ── Leads ───────────────────────────────────────────

    async def create_lead(self, data: dict[str, Any]) -> dict[str, Any]:
        data.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        data.setdefault("status", "new")
        resp = await self._http.post(
            self._rest("leads"),
            json=data,
            headers=self._headers(prefer="return=representation"),
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if isinstance(rows, list) and rows else rows

    async def get_leads(
        self, status: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "select": "*",
            "order": "created_at.desc",
            "limit": str(limit),
            "offset": str(offset),
        }
        if status:
            params["status"] = f"eq.{status}"
        resp = await self._http.get(
            self._rest("leads"), params=params, headers=self._headers()
        )
        resp.raise_for_status()
        return resp.json()

    async def update_lead(self, lead_id: str, data: dict[str, Any]) -> dict[str, Any]:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        resp = await self._http.patch(
            self._rest("leads"),
            params={"id": f"eq.{lead_id}"},
            json=data,
            headers=self._headers(prefer="return=representation"),
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if isinstance(rows, list) and rows else rows

    async def close(self):
        await self._http.aclose()

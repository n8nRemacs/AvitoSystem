"""
Lightweight Supabase PostgREST wrapper.
Uses httpx instead of the heavy supabase-py SDK to avoid build issues on Python 3.14.
Provides the same table().select().eq().execute() interface used throughout the app.
"""
import httpx
from dataclasses import dataclass, field
from typing import Any
from src.config import settings


@dataclass
class QueryResult:
    data: list[dict[str, Any]]
    count: int | None = None


class QueryBuilder:
    """Chainable PostgREST query builder mimicking supabase-py API."""

    def __init__(self, client: httpx.Client, table: str, base_url: str, headers: dict):
        self._client = client
        self._table = table
        self._base_url = f"{base_url}/rest/v1/{table}"
        self._headers = headers
        self._params: dict[str, str] = {}
        self._method = "GET"
        self._body: Any = None
        self._select_columns = "*"

    def select(self, columns: str = "*") -> "QueryBuilder":
        self._method = "GET"
        self._select_columns = columns
        self._params["select"] = columns
        return self

    def insert(self, data: dict | list) -> "QueryBuilder":
        self._method = "POST"
        self._body = data
        self._headers["Prefer"] = "return=representation"
        return self

    def update(self, data: dict) -> "QueryBuilder":
        self._method = "PATCH"
        self._body = data
        self._headers["Prefer"] = "return=representation"
        return self

    def delete(self) -> "QueryBuilder":
        self._method = "DELETE"
        self._headers["Prefer"] = "return=representation"
        return self

    def eq(self, column: str, value: Any) -> "QueryBuilder":
        self._params[column] = f"eq.{value}"
        return self

    def neq(self, column: str, value: Any) -> "QueryBuilder":
        self._params[column] = f"neq.{value}"
        return self

    def in_(self, column: str, values: list) -> "QueryBuilder":
        # Empty list: skip filter — caller should guard if they care
        if not values:
            return self
        # PostgREST IN filter: col=in.(v1,v2,...)
        joined = ",".join(str(v) for v in values)
        self._params[column] = f"in.({joined})"
        return self

    def is_(self, column: str, value: Any) -> "QueryBuilder":
        # PostgREST IS filter (e.g. WHERE col IS NULL). Pass value="null" for IS NULL.
        rendered = "null" if value is None else str(value).lower()
        self._params[column] = f"is.{rendered}"
        return self

    def order(self, column: str, *, desc: bool = False, nullsfirst: bool = False) -> "QueryBuilder":
        direction = "desc" if desc else "asc"
        suffix = ".nullsfirst" if nullsfirst else ""
        self._params["order"] = f"{column}.{direction}{suffix}"
        return self

    def limit(self, count: int) -> "QueryBuilder":
        self._params["limit"] = str(count)
        return self

    def execute(self) -> QueryResult:
        if self._method == "GET":
            resp = self._client.get(self._base_url, params=self._params, headers=self._headers)
        elif self._method == "POST":
            resp = self._client.post(self._base_url, json=self._body, params=self._params, headers=self._headers)
        elif self._method == "PATCH":
            resp = self._client.patch(self._base_url, json=self._body, params=self._params, headers=self._headers)
        elif self._method == "DELETE":
            resp = self._client.delete(self._base_url, params=self._params, headers=self._headers)
        else:
            raise ValueError(f"Unknown method: {self._method}")

        resp.raise_for_status()

        try:
            data = resp.json()
        except Exception:
            data = []

        if isinstance(data, dict):
            data = [data]

        return QueryResult(data=data if isinstance(data, list) else [])


class SupabaseClient:
    """Minimal Supabase client using PostgREST."""

    def __init__(self, url: str, key: str):
        self._url = url.rstrip("/")
        self._key = key
        self._client = httpx.Client(timeout=30.0)

    def _headers(self) -> dict:
        return {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }

    def table(self, name: str) -> QueryBuilder:
        return QueryBuilder(self._client, name, self._url, self._headers())


_client: SupabaseClient | None = None


def get_supabase() -> SupabaseClient:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_key)
    return _client


def create_client(url: str, key: str) -> SupabaseClient:
    return SupabaseClient(url, key)

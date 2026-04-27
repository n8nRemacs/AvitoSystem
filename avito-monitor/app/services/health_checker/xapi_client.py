"""Thin async HTTP client for avito-xapi used only by the health-checker.

Distinct from :mod:`avito_mcp.integrations.xapi_client` so the health-checker
service can:

* talk to *raw* xapi endpoints (no MCP-layer normalisation);
* surface ``status_code`` / ``latency_ms`` cleanly to scenarios;
* never raise on non-2xx — scenarios decide what counts as a fail.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

DEFAULT_TIMEOUT = 10.0


@dataclass
class XapiCallResult:
    """Outcome of a single GET to xapi.

    ``ok`` is True iff we got an HTTP response with status < 400.
    On transport errors (connect/read timeout, DNS), ``ok`` is False,
    ``status_code`` is None and ``error`` is the exception message.
    """

    ok: bool
    status_code: int | None
    latency_ms: int
    body: Any | None = None
    error: str | None = None


class XapiClient:
    """Tiny GET-only client around xapi for the health-checker."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._client_override = client

    def _make_client(self) -> httpx.AsyncClient:
        if self._client_override is not None:
            return self._client_override
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={
                "X-Api-Key": self.api_key,
                "User-Agent": "avito-monitor-healthchecker/0.1.0",
                "Accept": "application/json",
            },
        )

    async def get(self, path: str, params: dict[str, Any] | None = None) -> XapiCallResult:
        return await self._request("GET", path, params=params)

    async def post(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> XapiCallResult:
        return await self._request("POST", path, params=params, json_body=json_body)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> XapiCallResult:
        client = self._make_client()
        owns_client = self._client_override is None
        start = time.monotonic()
        try:
            try:
                resp = await client.request(
                    method,
                    path,
                    params=params or None,
                    json=json_body if json_body is not None else None,
                )
            except httpx.HTTPError as exc:
                latency_ms = int((time.monotonic() - start) * 1000)
                return XapiCallResult(
                    ok=False,
                    status_code=None,
                    latency_ms=latency_ms,
                    error=f"{type(exc).__name__}: {exc}",
                )

            latency_ms = int((time.monotonic() - start) * 1000)
            body: Any | None
            try:
                body = resp.json()
            except ValueError:
                body = resp.text

            return XapiCallResult(
                ok=resp.status_code < 400,
                status_code=resp.status_code,
                latency_ms=latency_ms,
                body=body,
                error=None if resp.status_code < 400 else f"HTTP {resp.status_code}",
            )
        finally:
            if owns_client:
                await client.aclose()

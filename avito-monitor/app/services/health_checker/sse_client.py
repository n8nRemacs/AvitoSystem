"""Tiny Server-Sent Events client built on httpx, with no extra dependencies.

Generic enough for both the health-checker (Stage 4) and the messenger-bot
(Stage 6) to reuse — no scenario- or bot-specific logic lives here.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class SseEvent:
    """One parsed SSE event block (``event:`` + ``data:`` + blank line)."""

    event_name: str
    data: dict[str, Any]
    raw_data: str = ""


class SseClient:
    """Minimal async SSE client around ``httpx.AsyncClient.stream``."""

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        *,
        timeout: httpx.Timeout | float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.url = url
        self.headers = dict(headers or {})
        # SSE streams are long-lived: fail fast on connect, never on read.
        self.timeout = timeout if timeout is not None else httpx.Timeout(
            connect=5.0, read=None, write=10.0, pool=5.0
        )
        self._client_override = client

    @asynccontextmanager
    async def stream(self) -> AsyncIterator[AsyncIterator[SseEvent]]:
        """Yield an async iterator of parsed SSE events.

        On context exit the underlying response and (if owned) client are
        closed unconditionally so we never leak connections on early exit.
        """
        owns_client = self._client_override is None
        client = self._client_override or httpx.AsyncClient(timeout=self.timeout)
        try:
            async with client.stream(
                "GET", self.url, headers=self.headers, timeout=self.timeout
            ) as response:
                response.raise_for_status()
                yield _iter_events(response)
        finally:
            if owns_client:
                await client.aclose()


async def _iter_events(response: httpx.Response) -> AsyncIterator[SseEvent]:
    """Parse the SSE wire format line-by-line into ``SseEvent`` objects."""
    event_name = "message"
    data_lines: list[str] = []

    async for raw_line in response.aiter_lines():
        # ``aiter_lines`` strips the trailing newline. A blank line marks the
        # end of an event block.
        if raw_line == "":
            if data_lines:
                raw = "\n".join(data_lines)
                data: dict[str, Any]
                try:
                    parsed = json.loads(raw)
                    data = parsed if isinstance(parsed, dict) else {"value": parsed}
                except (ValueError, TypeError):
                    data = {"value": raw}
                yield SseEvent(event_name=event_name, data=data, raw_data=raw)
            event_name = "message"
            data_lines = []
            continue

        if raw_line.startswith(":"):
            # Comment / keepalive line — ignored per spec.
            continue

        field, _, value = raw_line.partition(":")
        # Per spec: a single leading space in the value is stripped.
        if value.startswith(" "):
            value = value[1:]

        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)
        # Other fields ("id", "retry") are intentionally ignored — not needed.

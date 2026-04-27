"""Entry point for ``python -m avito_mcp``.

Picks the transport based on ``AVITO_MCP_TRANSPORT``:
    stdio  — default; MCP runs over stdin/stdout (for local Claude Code).
    sse    — Server-Sent-Events HTTP transport on ``AVITO_MCP_HTTP_PORT``.
    http   — alias for sse (kept for forward-compat with newer MCP SDK).

For HTTP/SSE we require an ``Authorization: Bearer <token>`` header that
matches ``AVITO_MCP_AUTH_TOKEN`` and refuse to start without one.

The HTTP app also exposes two additional routes alongside the FastMCP-provided
``/sse``:
    GET  /healthz  — unauthenticated; returns status, version, uptime, tool count.
    POST /restart  — bearer-auth; replies 200 then exits the process so docker
                     ``restart: unless-stopped`` respawns the container.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp

from avito_mcp import __version__
from avito_mcp.config import get_mcp_settings
from avito_mcp.server import mcp

log = logging.getLogger("avito_mcp")

# Captured once on process start; reused by /healthz to compute uptime.
_STARTED_AT_MONO = time.monotonic()
_STARTED_AT_ISO = datetime.now(timezone.utc).isoformat()


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Reject any request missing or with a wrong Bearer token.

    ``/healthz`` is intentionally unauthenticated so docker / load balancers
    can probe liveness without holding the token.
    """

    # Paths that are always allowed without auth.
    _PUBLIC_PATHS = frozenset({"/healthz"})

    def __init__(self, app: ASGIApp, *, expected_token: str) -> None:
        super().__init__(app)
        self._expected = expected_token

    async def dispatch(self, request, call_next):  # type: ignore[override]
        if request.url.path in self._PUBLIC_PATHS:
            return await call_next(request)

        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if not auth or not auth.lower().startswith("bearer "):
            return JSONResponse(
                {"error": "missing_authorization", "detail": "Bearer token required"},
                status_code=401,
            )
        token = auth.split(" ", 1)[1].strip()
        if token != self._expected:
            return JSONResponse(
                {"error": "invalid_token"},
                status_code=403,
            )
        return await call_next(request)


async def _healthz(_request: Request) -> JSONResponse:
    """Liveness probe with version + uptime + tool count.

    Unauthenticated by design (allow-listed in BearerAuthMiddleware).
    """
    try:
        tools = await mcp.list_tools()
        tools_registered = len(tools)
    except Exception:  # pragma: no cover — defensive; list_tools is in-memory
        tools_registered = 0

    uptime_sec = int(time.monotonic() - _STARTED_AT_MONO)
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "uptime_sec": uptime_sec,
            "tools_registered": tools_registered,
            "started_at": _STARTED_AT_ISO,
        }
    )


async def _delayed_exit(delay_seconds: float = 0.5) -> None:
    """Sleep briefly so the HTTP response flushes, then hard-exit.

    Using ``os._exit`` instead of ``sys.exit`` to bypass any uvicorn graceful
    shutdown hook — we *want* the supervisor (docker) to respawn us cleanly.
    """
    await asyncio.sleep(delay_seconds)
    log.warning("avito-mcp /restart triggered — exiting now for supervisor respawn")
    os._exit(0)


async def _restart(_request: Request) -> JSONResponse:
    """POST /restart — schedule a process exit and reply immediately.

    Bearer auth is enforced by BearerAuthMiddleware (this path is NOT in the
    allow-list).
    """
    asyncio.create_task(_delayed_exit())
    return JSONResponse(
        {
            "restarting": True,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )


def _build_http_app() -> Starlette:
    """Build the Starlette app: FastMCP /sse routes + /healthz + /restart."""
    settings = get_mcp_settings()
    sse_app = mcp.sse_app()

    extra_routes = [
        Route("/healthz", _healthz, methods=["GET"]),
        Route("/restart", _restart, methods=["POST"]),
    ]

    return Starlette(
        routes=[*sse_app.routes, *extra_routes],
        middleware=[
            Middleware(
                BearerAuthMiddleware,
                expected_token=settings.avito_mcp_auth_token,
            ),
        ],
    )


def _run_stdio() -> None:
    log.info("starting avito-mcp on stdio transport")
    mcp.run(transport="stdio")


def _run_http() -> None:
    settings = get_mcp_settings()
    if not settings.avito_mcp_auth_token:
        print(
            "ERROR: AVITO_MCP_AUTH_TOKEN must be set when transport is http/sse.",
            file=sys.stderr,
        )
        sys.exit(2)

    app = _build_http_app()

    log.info(
        "starting avito-mcp on HTTP+SSE transport at %s:%d",
        settings.avito_mcp_http_host,
        settings.avito_mcp_http_port,
    )
    uvicorn.run(
        app,
        host=settings.avito_mcp_http_host,
        port=settings.avito_mcp_http_port,
        log_level="info",
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = get_mcp_settings()
    transport = settings.avito_mcp_transport.lower()
    if transport in ("http", "sse"):
        _run_http()
    elif transport == "stdio":
        _run_stdio()
    else:
        print(f"ERROR: unknown AVITO_MCP_TRANSPORT={transport!r}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()

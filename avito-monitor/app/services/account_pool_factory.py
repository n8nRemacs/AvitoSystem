"""Shared AccountPool factory — used by both polling task and web UI.

A single process-lifetime httpx.AsyncClient is reused across all poll ticks
so that HTTP connection pooling to xapi actually works.  Do not close the
client from calling code; it lives for the life of the process.
"""
from __future__ import annotations

import httpx

from app.services.account_pool import AccountPool

_POOL: AccountPool | None = None
_CLIENT: httpx.AsyncClient | None = None


def get_account_pool() -> AccountPool:
    """Return a singleton AccountPool backed by a long-lived httpx client.

    Thread-safe under asyncio (single-threaded event loop); safe to call from
    any coroutine.  First call initialises the client and pool; subsequent
    calls return the same objects.
    """
    global _POOL, _CLIENT
    if _POOL is None:
        from app.config import get_settings

        s = get_settings()
        _CLIENT = httpx.AsyncClient(
            base_url=s.avito_xapi_url,
            headers={"X-Api-Key": s.avito_xapi_api_key},
            timeout=httpx.Timeout(30.0),
        )
        _POOL = AccountPool(xapi_client=_CLIENT)
    return _POOL


async def close_account_pool() -> None:
    """Graceful shutdown / test teardown — closes the underlying httpx client."""
    global _POOL, _CLIENT
    if _CLIENT is not None:
        await _CLIENT.aclose()
        _CLIENT = None
        _POOL = None

"""Best-effort whitelist: "is this chat about MY listing?".

xapi has no flat "list my listings" endpoint, so we approximate via:

* Own user_id from ``GET /api/v1/sessions/current`` (cached process-lifetime,
  doesn't change). Settings can override via ``AVITO_OWN_USER_ID``.
* Listing seller from ``GET /api/v1/items/{item_id}`` (``seller_id``).

If either lookup is uncertain (5xx, missing field, transport error) we
return ``"unknown"`` and the caller defaults to ALLOW. Better to over-reply
during V2 soak than to silently miss real leads.

Channel → item_id resolution comes from ``GET /api/v1/messenger/channels/{id}``
which surfaces ``info.item_id``.
"""
from __future__ import annotations

from typing import Literal

import structlog

from app.config import Settings, get_settings
from app.services.health_checker.xapi_client import XapiClient

log = structlog.get_logger(__name__)

WhitelistVerdict = Literal["yes", "no", "unknown"]


# Process-lifetime cache for the own user_id. Avito user_id is stable per
# session; cleared on container restart.
_OWN_USER_ID_CACHE: int | None = None


def reset_cache_for_tests() -> None:
    """Clear the in-process cache; not used in production."""
    global _OWN_USER_ID_CACHE
    _OWN_USER_ID_CACHE = None


async def fetch_own_user_id(client: XapiClient, settings: Settings | None = None) -> int | None:
    """Return the configured / cached / xapi-derived own user_id.

    Resolution order:

    1. ``settings.avito_own_user_id`` if set (env override).
    2. Process-lifetime cache.
    3. ``GET /api/v1/sessions/current`` → ``user_id``. On any failure, returns
       ``None`` and the caller treats whitelist as ``unknown``.
    """
    global _OWN_USER_ID_CACHE
    s = settings or get_settings()

    # 1. explicit env override wins (and warms the cache).
    if s.avito_own_user_id is not None:
        _OWN_USER_ID_CACHE = int(s.avito_own_user_id)
        return _OWN_USER_ID_CACHE

    # 2. cached.
    if _OWN_USER_ID_CACHE is not None:
        return _OWN_USER_ID_CACHE

    # 3. resolve from xapi.
    call = await client.get("/api/v1/sessions/current")
    if not call.ok or not isinstance(call.body, dict):
        log.warning(
            "messenger_bot.own_user_id.lookup_failed",
            status_code=call.status_code,
            error=call.error,
        )
        return None

    raw = call.body.get("user_id")
    if raw is None:
        log.warning("messenger_bot.own_user_id.missing_field", body_keys=list(call.body.keys()))
        return None
    try:
        _OWN_USER_ID_CACHE = int(raw)
    except (TypeError, ValueError):
        log.warning("messenger_bot.own_user_id.not_int", raw=raw)
        return None
    return _OWN_USER_ID_CACHE


async def fetch_item_id_for_channel(channel_id: str, client: XapiClient) -> int | None:
    """Resolve ``channel_id`` → ``item_id`` via xapi.

    xapi normalises into ``info.item_id``. Returns ``None`` on any failure;
    the caller treats whitelist as ``unknown`` in that case.
    """
    call = await client.get(f"/api/v1/messenger/channels/{channel_id}")
    if not call.ok or not isinstance(call.body, dict):
        log.warning(
            "messenger_bot.channel_lookup.failed",
            channel_id=channel_id,
            status_code=call.status_code,
            error=call.error,
        )
        return None
    info = call.body.get("info")
    if isinstance(info, dict):
        item_id = info.get("item_id") or info.get("itemId")
        if isinstance(item_id, (int, str)) and str(item_id).isdigit():
            return int(item_id)
    # fallback: top-level
    raw = call.body.get("item_id") or call.body.get("itemId")
    if isinstance(raw, (int, str)) and str(raw).isdigit():
        return int(raw)
    return None


async def is_my_listing(
    item_id: int | None,
    own_user_id: int | None,
    client: XapiClient,
) -> WhitelistVerdict:
    """Compare item.seller_id == own_user_id.

    * ``"yes"`` — IDs match.
    * ``"no"``  — both known, and they differ.
    * ``"unknown"`` — anything else (lookup error, missing field, no own_user_id).
    """
    if item_id is None or own_user_id is None:
        return "unknown"
    call = await client.get(f"/api/v1/items/{item_id}")
    if not call.ok or not isinstance(call.body, dict):
        log.warning(
            "messenger_bot.item_lookup.failed",
            item_id=item_id,
            status_code=call.status_code,
            error=call.error,
        )
        return "unknown"
    seller_id = call.body.get("seller_id") or call.body.get("sellerId") or call.body.get("userId")
    if seller_id is None:
        return "unknown"
    try:
        return "yes" if int(seller_id) == int(own_user_id) else "no"
    except (TypeError, ValueError):
        return "unknown"

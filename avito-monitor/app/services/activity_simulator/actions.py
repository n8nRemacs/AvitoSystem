"""Individual simulator actions.

Each action is one xapi call (or a short chain) plus one row written to
``activity_log``. Actions never raise — failures land in the log row with
``status='error'`` (or ``'rate_limited'`` on HTTP 429).

Action mix per TZ §2 L3:
    * 60% ``get_chats``
    * 20% ``get_unread_count``
    * 10% ``get_listing_detail`` (uses the channel-derived item_id cache)
    * 10% ``open_random_chat_and_read`` (chats → messages → mark-read POST)

The mark-read POST is idempotent (Scenario F uses it for the same reason);
no other state-mutating endpoint is touched.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Any

import structlog

from app.db.base import get_sessionmaker
from app.db.models import ActivityLog
from app.services.health_checker.xapi_client import XapiCallResult, XapiClient

log = structlog.get_logger(__name__)

ITEM_ID_CACHE_MAX = 5

# Singleton cache of recent channel item_ids seen via ``get_chats``. Used by
# ``get_listing_detail`` to pick a real (non-404) item the user is talking about.
ITEM_ID_CACHE: deque[str] = deque(maxlen=ITEM_ID_CACHE_MAX)


@dataclass
class ActionResult:
    """Outcome of one simulator action; mirrors an ``activity_log`` row."""

    action: str
    status: str  # 'ok' | 'error' | 'rate_limited' | 'skipped'
    latency_ms: int
    target: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "target": self.target,
            "details": self.details,
        }


def _classify(call: XapiCallResult) -> str:
    """Map an xapi call outcome onto the activity_log status enum."""
    if call.ok:
        return "ok"
    if call.status_code == 429:
        return "rate_limited"
    return "error"


def _extract_channels(body: object) -> list[dict]:
    """Pull a list of channel dicts out of the xapi list response."""
    if isinstance(body, dict):
        for key in ("channels", "items", "data"):
            value = body.get(key)
            if isinstance(value, list):
                return [c for c in value if isinstance(c, dict)]
    if isinstance(body, list):
        return [c for c in body if isinstance(c, dict)]
    return []


def _channel_item_id(channel: dict) -> str | None:
    """Pull the linked item_id out of a single channel dict.

    xapi shapes vary: ``context.value.id`` (mobile API) or top-level ``item_id``.
    """
    candidates: list[Any] = []
    ctx = channel.get("context")
    if isinstance(ctx, dict):
        val = ctx.get("value")
        if isinstance(val, dict):
            candidates.append(val.get("id"))
            candidates.append(val.get("item_id"))
    candidates.extend([channel.get("item_id"), channel.get("itemId")])
    for cand in candidates:
        if isinstance(cand, (str, int)) and str(cand):
            return str(cand)
    return None


def _refill_item_cache_from_channels(channels: list[dict]) -> None:
    """Push any new item_ids onto ITEM_ID_CACHE without duplicates."""
    for ch in channels:
        item_id = _channel_item_id(ch)
        if item_id and item_id not in ITEM_ID_CACHE:
            ITEM_ID_CACHE.append(item_id)


async def _persist(result: ActionResult) -> None:
    """Insert one row into ``activity_log`` (source='simulator')."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = ActivityLog(
            source="simulator",
            action=result.action,
            target=result.target,
            status=result.status,
            latency_ms=result.latency_ms,
            details=result.details or None,
        )
        session.add(row)
        await session.commit()


async def _persist_safely(result: ActionResult) -> None:
    """Same as ``_persist`` but never crashes the scheduler loop."""
    try:
        await _persist(result)
    except Exception:
        log.exception("simulator.persist_failed", action=result.action, status=result.status)


# ----------------------------------------------------------------------
# action: get_chats
# ----------------------------------------------------------------------

async def action_get_chats(client: XapiClient) -> ActionResult:
    """GET /messenger/channels?limit=20 + opportunistically refill item_id cache."""
    call = await client.get("/api/v1/messenger/channels", params={"limit": 20})
    channels = _extract_channels(call.body) if call.ok else []
    if channels:
        _refill_item_cache_from_channels(channels)
    details: dict[str, Any] = {
        "endpoint": "/api/v1/messenger/channels?limit=20",
        "status_code": call.status_code,
        "returned_channels": len(channels),
        "item_id_cache_size": len(ITEM_ID_CACHE),
    }
    if not call.ok:
        details["error"] = call.error or f"HTTP {call.status_code}"
    return ActionResult(
        action="get_chats",
        status=_classify(call),
        latency_ms=call.latency_ms,
        target=None,
        details=details,
    )


# ----------------------------------------------------------------------
# action: get_unread_count
# ----------------------------------------------------------------------

async def action_get_unread_count(client: XapiClient) -> ActionResult:
    call = await client.get("/api/v1/messenger/unread-count")
    details: dict[str, Any] = {
        "endpoint": "/api/v1/messenger/unread-count",
        "status_code": call.status_code,
    }
    if call.ok and isinstance(call.body, dict):
        details["unread_count"] = call.body.get("count")
    if not call.ok:
        details["error"] = call.error or f"HTTP {call.status_code}"
    return ActionResult(
        action="get_unread_count",
        status=_classify(call),
        latency_ms=call.latency_ms,
        target=None,
        details=details,
    )


# ----------------------------------------------------------------------
# action: get_listing_detail
# ----------------------------------------------------------------------

async def action_get_listing_detail(client: XapiClient) -> ActionResult:
    """Pick a random item_id from cache, GET /items/{id}.

    If the cache is empty, returns a ``skipped`` result and does NOT write a
    log row — the caller should pick another action variant.
    """
    if not ITEM_ID_CACHE:
        return ActionResult(
            action="get_listing_detail",
            status="skipped",
            latency_ms=0,
            details={"reason": "item_id_cache empty"},
        )
    # ``random.choice`` over a deque is O(n) but n <= 5 so fine.
    item_id = random.choice(list(ITEM_ID_CACHE))  # noqa: S311 — non-crypto pick
    call = await client.get(f"/api/v1/items/{item_id}")
    details: dict[str, Any] = {
        "endpoint": f"/api/v1/items/{item_id}",
        "status_code": call.status_code,
    }
    if not call.ok:
        details["error"] = call.error or f"HTTP {call.status_code}"
    return ActionResult(
        action="get_listing_detail",
        status=_classify(call),
        latency_ms=call.latency_ms,
        target=item_id,
        details=details,
    )


# ----------------------------------------------------------------------
# action: open_random_chat_and_read
# ----------------------------------------------------------------------

async def action_open_random_chat_and_read(client: XapiClient) -> ActionResult:
    """3-call sequence imitating "open a chat and look at it".

    1. GET /messenger/channels?limit=20 — pick a random channel
    2. GET /messenger/channels/{id}/messages?limit=20
    3. POST /messenger/channels/{id}/read   (idempotent on already-read chats)

    All three latencies are summed; status is the worst of the three. If step
    1 returns no channels, the action is recorded as ``skipped``.
    """
    list_call = await client.get("/api/v1/messenger/channels", params={"limit": 20})
    channels = _extract_channels(list_call.body) if list_call.ok else []
    if channels:
        _refill_item_cache_from_channels(channels)

    if not list_call.ok:
        return ActionResult(
            action="open_random_chat_and_read",
            status=_classify(list_call),
            latency_ms=list_call.latency_ms,
            details={
                "step": "list",
                "status_code": list_call.status_code,
                "error": list_call.error or f"HTTP {list_call.status_code}",
            },
        )
    if not channels:
        return ActionResult(
            action="open_random_chat_and_read",
            status="skipped",
            latency_ms=list_call.latency_ms,
            details={"reason": "no channels"},
        )

    chosen = random.choice(channels)  # noqa: S311 — non-crypto pick
    channel_id = chosen.get("id") or chosen.get("channel_id")
    if not isinstance(channel_id, str) or not channel_id:
        return ActionResult(
            action="open_random_chat_and_read",
            status="error",
            latency_ms=list_call.latency_ms,
            details={"reason": "channel without id"},
        )

    msg_call = await client.get(
        f"/api/v1/messenger/channels/{channel_id}/messages",
        params={"limit": 20},
    )
    read_call = await client.post(
        f"/api/v1/messenger/channels/{channel_id}/read",
        json_body={},
    )

    total_latency = list_call.latency_ms + msg_call.latency_ms + read_call.latency_ms
    statuses = [_classify(c) for c in (list_call, msg_call, read_call)]
    # Status precedence: error > rate_limited > ok.
    if "error" in statuses:
        status = "error"
    elif "rate_limited" in statuses:
        status = "rate_limited"
    else:
        status = "ok"

    details: dict[str, Any] = {
        "list_status_code": list_call.status_code,
        "messages_status_code": msg_call.status_code,
        "read_status_code": read_call.status_code,
        "channel_count": len(channels),
    }
    for label, call in (
        ("list_error", list_call),
        ("messages_error", msg_call),
        ("read_error", read_call),
    ):
        if not call.ok:
            details[label] = call.error or f"HTTP {call.status_code}"

    return ActionResult(
        action="open_random_chat_and_read",
        status=status,
        latency_ms=total_latency,
        target=channel_id,
        details=details,
    )


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------

ACTIONS = {
    "get_chats": action_get_chats,
    "get_unread_count": action_get_unread_count,
    "get_listing_detail": action_get_listing_detail,
    "open_random_chat_and_read": action_open_random_chat_and_read,
}


async def run_action(name: str, client: XapiClient) -> ActionResult:
    """Run one named action with a top-level except-guard, then persist if applicable.

    Returns the ActionResult. Skipped actions do not write to ``activity_log``.
    """
    fn = ACTIONS.get(name)
    if fn is None:
        raise KeyError(f"unknown action {name!r}; known: {sorted(ACTIONS)}")
    try:
        result = await fn(client)
    except Exception as exc:
        log.exception("simulator.action.crashed", action=name)
        result = ActionResult(
            action=name,
            status="error",
            latency_ms=0,
            details={"error": f"{type(exc).__name__}: {exc}"},
        )
    if result.status != "skipped":
        await _persist_safely(result)
    log.info(
        "simulator.action.completed",
        action=result.action,
        status=result.status,
        latency_ms=result.latency_ms,
        target=result.target,
    )
    return result

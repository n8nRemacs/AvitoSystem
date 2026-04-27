"""SSE listener loop for the messenger-bot.

Holds one long-lived ``GET /api/v1/messenger/realtime/events`` connection,
parses inbound events with :class:`SseClient`, and dispatches each event to
:func:`handle_event_safe` as a fire-and-forget task — pulling from the SSE
stream is decoupled from event handling so a slow xapi POST never starves
the listener.

Reconnect on any error with exponential backoff capped at 60s. Reset backoff
on a clean stream exit. The state machine is reflected in :data:`SSE_STATE`
which the ``/healthz`` sidecar surfaces.
"""
from __future__ import annotations

import asyncio
from typing import Literal

import structlog

from app.config import Settings, get_settings
from app.services.health_checker.sse_client import SseClient
from app.services.health_checker.xapi_client import XapiClient
from app.services.messenger_bot.handler import handle_event_safe

log = structlog.get_logger(__name__)


SseState = Literal["initial", "connecting", "connected", "reconnecting", "closed"]
SSE_STATE: SseState = "initial"
RECONNECT_ATTEMPTS: int = 0
INITIAL_BACKOFF_SEC: float = 1.0
MAX_BACKOFF_SEC: float = 60.0


def make_xapi_client(settings: Settings | None = None) -> XapiClient:
    s = settings or get_settings()
    return XapiClient(base_url=s.avito_xapi_url, api_key=s.avito_xapi_api_key)


def _set_state(state: SseState) -> None:
    global SSE_STATE
    SSE_STATE = state
    log.info("messenger_bot.sse_state", state=state)


async def listen_forever(settings: Settings | None = None) -> None:
    """Forever-loop: open SSE → dispatch events → reconnect on failure."""
    global RECONNECT_ATTEMPTS
    settings = settings or get_settings()

    url = f"{settings.avito_xapi_url.rstrip('/')}/api/v1/messenger/realtime/events"
    headers = {
        "X-Api-Key": settings.avito_xapi_api_key,
        "User-Agent": "avito-monitor-messengerbot/0.1.0",
        "Accept": "text/event-stream",
    }

    backoff = INITIAL_BACKOFF_SEC
    while True:
        _set_state("connecting")
        try:
            async with SseClient(url, headers).stream() as stream:
                _set_state("connected")
                backoff = INITIAL_BACKOFF_SEC  # reset on successful connect
                async for evt in stream:
                    # Fire-and-forget so a slow handler never blocks the
                    # SSE pull. ``handle_event_safe`` swallows everything.
                    client = make_xapi_client(settings)
                    asyncio.create_task(  # noqa: RUF006 — intentional fire-and-forget
                        handle_event_safe(evt, client=client, settings=settings),
                        name=f"bot-handle-{evt.event_name}",
                    )
        except asyncio.CancelledError:
            _set_state("closed")
            raise
        except Exception as exc:
            RECONNECT_ATTEMPTS += 1
            log.warning(
                "messenger_bot.sse.broken",
                error=f"{type(exc).__name__}: {exc}",
                backoff_sec=round(backoff, 2),
                attempt=RECONNECT_ATTEMPTS,
            )
            _set_state("reconnecting")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF_SEC)


async def start_listener(settings: Settings | None = None) -> list[asyncio.Task]:
    """Spawn the single SSE listener task; caller is responsible for cancellation."""
    settings = settings or get_settings()
    task = asyncio.create_task(listen_forever(settings), name="bot-sse-listener")
    return [task]

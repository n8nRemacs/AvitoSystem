"""SSE endpoint for real-time messenger events.

Bridges WsManager (WebSocket from Avito) → Server-Sent Events to frontend/clients.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.dependencies import get_current_tenant
from src.middleware.auth import require_feature
from src.models.tenant import TenantContext
from src.workers.ws_manager import ws_manager

logger = logging.getLogger("xapi.realtime")

router = APIRouter(prefix="/api/v1/messenger/realtime", tags=["Realtime"])

SSE_KEEPALIVE_SEC = 30


async def _sse_generator(tenant_id: str):
    """Async generator yielding SSE-formatted events from WsManager."""
    queue = None
    try:
        queue = await ws_manager.subscribe(tenant_id)

        # Send initial connected event
        yield _format_sse("connected", {"event": "connected", "tenant_id": tenant_id,
                                         "timestamp": datetime.now(timezone.utc).isoformat()})

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_SEC)
                event_type = event.get("event", "message")
                yield _format_sse(event_type, event)
            except asyncio.TimeoutError:
                # Send keepalive to prevent proxy/nginx timeout
                yield _format_sse("keepalive", {"event": "keepalive",
                                                 "timestamp": datetime.now(timezone.utc).isoformat()})
            except asyncio.CancelledError:
                break
    except (ValueError, ConnectionError):
        raise
    finally:
        if queue is not None:
            await ws_manager.unsubscribe(tenant_id, queue)


def _format_sse(event_type: str, data: dict) -> str:
    """Format dict as SSE text block."""
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


@router.get("/events")
async def sse_events(request: Request, ctx: TenantContext = Depends(get_current_tenant)):
    """SSE stream of real-time messenger events.

    Connects to Avito WebSocket per-tenant and relays push events.
    Supports api_key in query string for EventSource compatibility.
    """
    require_feature(request, "avito.messenger")
    tenant_id = ctx.tenant.id

    try:
        generator = _sse_generator(tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConnectionError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # nginx: disable proxy buffering
        },
    )


@router.get("/status")
async def realtime_status(request: Request, ctx: TenantContext = Depends(get_current_tenant)):
    """Get WebSocket connection status for the current tenant."""
    require_feature(request, "avito.messenger")
    return ws_manager.get_status(ctx.tenant.id)


@router.post("/stop")
async def realtime_stop(request: Request, ctx: TenantContext = Depends(get_current_tenant)):
    """Force-stop the WebSocket connection for the current tenant."""
    require_feature(request, "avito.messenger")
    await ws_manager._stop_connection(ctx.tenant.id)
    return {"status": "ok", "detail": "Connection stopped"}

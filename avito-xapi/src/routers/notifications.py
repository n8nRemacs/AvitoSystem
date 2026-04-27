"""V2.1 Notification interception channel.

The AvitoSessionManager APK runs a NotificationListenerService that picks up
Android FCM notifications from com.avito.android (or any other package the
user enables) and forwards them here. Each notification is persisted into
``avito_notifications`` and broadcast as a ``notification_intercepted`` event
into the tenant's SSE fan-out so the messenger-bot can react in real-time
even when the xapi↔Avito WebSocket is wedged.

Endpoints:
- POST /api/v1/notifications        ingest one notification
- GET  /api/v1/notifications/stats  freshness/volume metrics for scenario I
"""
from datetime import datetime, timedelta, timezone
import logging

from fastapi import APIRouter, Depends, Request

from src.dependencies import get_current_tenant
from src.middleware.auth import require_feature
from src.models.tenant import TenantContext
from src.models.notification import (
    NotificationIngestRequest,
    NotificationIngestResponse,
    NotificationStats,
)
from src.storage.supabase import get_supabase
from src.workers.ws_manager import ws_manager

logger = logging.getLogger("xapi.notifications")

router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


@router.post("", response_model=NotificationIngestResponse, status_code=201)
async def ingest_notification(
    body: NotificationIngestRequest,
    request: Request,
    ctx: TenantContext = Depends(get_current_tenant),
) -> NotificationIngestResponse:
    """Accept one intercepted Android notification.

    Persists it durably (so it survives bot restarts and SSE gaps), then
    best-effort broadcasts a ``notification_intercepted`` event to any SSE
    subscriber for the tenant.
    """
    require_feature(request, "avito.messenger")

    sb = get_supabase()

    row = {
        "tenant_id": ctx.tenant.id,
        "source": body.source,
        "package_name": body.package_name,
        "notification_id": body.notification_id,
        "tag": body.tag,
        "title": body.title,
        "body": body.body,
        "big_text": body.big_text,
        "sub_text": body.sub_text,
        "extras": body.extras,
        "posted_at": body.posted_at.isoformat() if body.posted_at else None,
    }

    insert_resp = sb.table("avito_notifications").insert(row).execute()
    if not insert_resp.data:
        logger.error("notifications.insert_returned_no_row tenant=%s", ctx.tenant.id)
        # PostgREST always returns inserted rows when Prefer=return=representation
        # (set inside QueryBuilder.insert). An empty result here is unexpected
        # but should not block ingestion: surface a synthetic id of 0 and skip
        # broadcast.
        return NotificationIngestResponse(
            status="persisted_no_id", notification_id=0, broadcast=False
        )

    inserted = insert_resp.data[0]
    db_id = int(inserted["id"])

    # Best-effort broadcast — durable copy is already in DB, so SSE failure is
    # non-fatal. The bot can do a catch-up query on reconnect (Task #14).
    payload = {
        "db_id": db_id,
        "source": body.source,
        "package_name": body.package_name,
        "notification_id": body.notification_id,
        "tag": body.tag,
        "title": body.title,
        "body": body.body,
        "big_text": body.big_text,
        "sub_text": body.sub_text,
        "posted_at": body.posted_at.isoformat() if body.posted_at else None,
    }
    broadcast_ok = ws_manager.broadcast_to_tenant(
        ctx.tenant.id, "notification_intercepted", payload
    )

    logger.info(
        "notifications.ingest tenant=%s db_id=%s pkg=%s tag=%s broadcast=%s",
        ctx.tenant.id, db_id, body.package_name, body.tag, broadcast_ok,
    )

    return NotificationIngestResponse(
        status="ok", notification_id=db_id, broadcast=broadcast_ok
    )


@router.get("/stats", response_model=NotificationStats)
async def notification_stats(
    request: Request,
    ctx: TenantContext = Depends(get_current_tenant),
) -> NotificationStats:
    """Volume + freshness metrics for the current tenant.

    Used by health-checker scenario I to verify the phone NotificationListener
    pipeline is alive. PASS condition is "last_received_at within N hours".
    """
    require_feature(request, "avito.messenger")

    sb = get_supabase()

    # Pull the last ~500 rows for this tenant — enough to compute the few
    # aggregates we expose without paging through the whole table.
    resp = (
        sb.table("avito_notifications")
        .select("id,source,package_name,received_at")
        .eq("tenant_id", ctx.tenant.id)
        .order("received_at", desc=True)
        .limit(500)
        .execute()
    )

    rows = resp.data or []
    if not rows:
        return NotificationStats()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    by_source: dict[str, int] = {}
    by_package: dict[str, int] = {}
    last_24h = 0
    last_received_at: datetime | None = None

    for r in rows:
        src = r.get("source") or "unknown"
        by_source[src] = by_source.get(src, 0) + 1
        pkg = r.get("package_name") or "unknown"
        by_package[pkg] = by_package.get(pkg, 0) + 1

        ts_raw = r.get("received_at")
        if ts_raw:
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                if last_received_at is None or ts > last_received_at:
                    last_received_at = ts
                if ts >= cutoff:
                    last_24h += 1
            except ValueError:
                pass

    return NotificationStats(
        total=len(rows),
        last_24h=last_24h,
        last_received_at=last_received_at,
        by_source=by_source,
        by_package=by_package,
    )

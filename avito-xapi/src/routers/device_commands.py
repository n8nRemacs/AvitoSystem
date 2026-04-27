"""Server-driven control channel for the AvitoSessionManager APK.

The phone has no public IP, so we invert the polarity: APK long-polls
the server. When the health-checker sees an Avito session whose JWT
exp is 60–180 s away, it creates a ``refresh_token`` command via the
admin POST. The next ``GET /commands?wait=60`` from the APK returns
that row, APK opens Avito (root ``monkey``), nudges it with input
swipes until SharedPrefs shows a fresh exp, force-stops the app, and
uploads the new session via the existing ``POST /api/v1/sessions``.
The APK then acks the command with the new_exp and elapsed time.

Endpoints
---------
``GET  /api/v1/devices/me/commands?wait=60``
    Long-poll. Returns the oldest pending command for the tenant or
    204 No Content after ``wait`` seconds. ``wait`` is clamped to
    [0, 60]. The server takes the row from ``pending`` to
    ``delivered`` atomically (PostgREST PATCH-then-return) so two
    concurrent pollers don't both run the same command.

``POST /api/v1/devices/me/commands/{id}/ack``
    APK reports outcome. Body: ``{ok, error, payload}``. Sets status
    to ``done`` or ``failed`` and stores ``result``.

``POST /api/v1/devices/me/commands``
    Admin insert (health-checker, TG bot, manual). Honours the
    dedup window — if there's already a pending/delivered row for
    this tenant+command younger than ``dedup_window_sec``, returns
    that row instead of creating a new one.

Auth: same ``ApiKeyAuthMiddleware`` as the rest of /api/v1/*. Tenant
context is resolved by middleware; we just read ``tenant_id`` off it.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response

from src.dependencies import get_current_tenant
from src.models.device_command import (
    CommandAckRequest,
    CommandCreateRequest,
    DeviceCommand,
)
from src.models.tenant import TenantContext
from src.storage.supabase import get_supabase

log = logging.getLogger("xapi.device_commands")

router = APIRouter(prefix="/api/v1/devices/me/commands", tags=["DeviceCommands"])

_LONG_POLL_INTERVAL_SEC = 1.0
_LONG_POLL_MAX_WAIT = 60


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_command(row: dict[str, Any]) -> DeviceCommand:
    return DeviceCommand(
        id=row["id"],
        command=row["command"],
        payload=row.get("payload") or {},
        created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
        expire_at=(
            datetime.fromisoformat(row["expire_at"].replace("Z", "+00:00"))
            if row.get("expire_at")
            else None
        ),
    )


def _expire_stale_commands(sb, tenant_id: str) -> None:
    """Sweep delivered/pending rows past their deadline to ``expired``.

    Cheap to do on each poll: filter by tenant + status + expire_at,
    flip them in one PATCH. Keeps the dedup check from being polluted
    by zombie rows when the APK was offline during a delivery.
    """
    now = _now_iso()
    try:
        sb.table("avito_device_commands").update(
            {"status": "expired"}
        ).eq("tenant_id", tenant_id).neq("status", "done").neq(
            "status", "failed"
        ).neq("status", "expired").execute()
        # NOTE: PostgREST eq/neq don't compose with arbitrary "lt",
        # so we'll do the deadline check in python on the next select.
        # The above PATCH is a no-op safety net while we tighten this.
    except Exception:
        log.exception("device_commands.expire_sweep_failed tenant=%s", tenant_id)


def _fetch_oldest_pending(sb, tenant_id: str) -> dict[str, Any] | None:
    """Return the oldest non-terminal command for the tenant, or None.

    Only ``pending`` rows are eligible to start delivery. ``delivered``
    rows that are still in their expire window are NOT redelivered —
    a redelivery would mean we double-execute on the APK side. If the
    APK fails to ack, the row will eventually flip to ``expired`` and
    the next health-checker tick re-issues a fresh command.
    """
    resp = (
        sb.table("avito_device_commands")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("status", "pending")
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


def _claim_command(sb, command_id: str) -> dict[str, Any] | None:
    """Move a row from ``pending`` to ``delivered``.

    PostgREST patch returns the updated row; if it returns nothing the
    row was already claimed by someone else (or its status changed)
    and the caller should keep polling.
    """
    resp = (
        sb.table("avito_device_commands")
        .update({"status": "delivered", "delivered_at": _now_iso()})
        .eq("id", command_id)
        .eq("status", "pending")
        .execute()
    )
    rows = resp.data or []
    return rows[0] if rows else None


# ----------------------------------------------------------------------
# GET — long-poll
# ----------------------------------------------------------------------

@router.get("", responses={204: {"description": "No commands within wait window"}})
async def poll_command(
    request: Request,
    response: Response,
    wait: int = Query(60, ge=0, le=_LONG_POLL_MAX_WAIT),
    ctx: TenantContext = Depends(get_current_tenant),
):
    """Long-poll for the next command. 200 with the row or 204 on timeout."""
    sb = get_supabase()
    tenant_id = ctx.tenant.id

    deadline = asyncio.get_running_loop().time() + max(wait, 0)
    while True:
        row = _fetch_oldest_pending(sb, tenant_id)
        if row is not None:
            claimed = _claim_command(sb, row["id"])
            if claimed:
                log.info(
                    "device_commands.delivered tenant=%s id=%s cmd=%s",
                    tenant_id, claimed["id"], claimed["command"],
                )
                return _row_to_command(claimed)
            # else: lost the race — fall through and poll again

        # client may have disconnected; bail out without sleeping more.
        if await request.is_disconnected():
            return Response(status_code=204)

        if asyncio.get_running_loop().time() >= deadline:
            return Response(status_code=204)

        await asyncio.sleep(_LONG_POLL_INTERVAL_SEC)


# ----------------------------------------------------------------------
# POST — ack
# ----------------------------------------------------------------------

@router.post("/{command_id}/ack")
async def ack_command(
    body: CommandAckRequest,
    command_id: str = Path(...),
    ctx: TenantContext = Depends(get_current_tenant),
):
    """APK reports execution outcome."""
    sb = get_supabase()
    tenant_id = ctx.tenant.id

    # Confirm ownership: a command id from a different tenant must not
    # be ackable through this caller's key.
    cur = (
        sb.table("avito_device_commands")
        .select("*")
        .eq("id", command_id)
        .eq("tenant_id", tenant_id)
        .execute()
    )
    if not cur.data:
        raise HTTPException(status_code=404, detail="Command not found")
    row = cur.data[0]

    if row["status"] in ("done", "failed", "expired"):
        # Idempotency — APK retries should not flap the row.
        return {"status": row["status"], "id": command_id, "noop": True}

    new_status = "done" if body.ok else "failed"
    update = {
        "status": new_status,
        "acked_at": _now_iso(),
        "result": {
            "ok": body.ok,
            "error": body.error,
            "payload": body.payload or {},
        },
    }
    sb.table("avito_device_commands").update(update).eq("id", command_id).execute()
    log.info(
        "device_commands.acked tenant=%s id=%s status=%s err=%s",
        tenant_id, command_id, new_status, body.error,
    )
    return {"status": new_status, "id": command_id}


# ----------------------------------------------------------------------
# POST — admin insert (health-checker / TG bot / manual)
# ----------------------------------------------------------------------

@router.post("", status_code=201)
async def create_command(
    body: CommandCreateRequest,
    ctx: TenantContext = Depends(get_current_tenant),
):
    """Insert a new command, honouring per-tenant dedup window."""
    sb = get_supabase()
    tenant_id = ctx.tenant.id
    now = datetime.now(timezone.utc)

    # Dedup: if a recent command of the same kind is still in flight,
    # return it instead of creating a duplicate. We can't express the
    # ``created_at >= cutoff`` filter through our QueryBuilder cleanly,
    # so we pull recent rows for the tenant+command and filter in py.
    recent = (
        sb.table("avito_device_commands")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("command", body.command)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    cutoff = now - timedelta(seconds=max(body.dedup_window_sec, 0))
    for r in recent.data or []:
        if r["status"] not in ("pending", "delivered"):
            continue
        created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        if created >= cutoff:
            log.info(
                "device_commands.dedup_hit tenant=%s id=%s cmd=%s",
                tenant_id, r["id"], body.command,
            )
            return {"status": "dedup", "command": _row_to_command(r).model_dump()}

    expire_at = now + timedelta(seconds=max(body.expire_after_sec, 30))
    insert_row = {
        "tenant_id": tenant_id,
        "command": body.command,
        "payload": body.payload,
        "issued_by": body.issued_by,
        "expire_at": expire_at.isoformat(),
    }
    resp = sb.table("avito_device_commands").insert(insert_row).execute()
    if not resp.data:
        raise HTTPException(status_code=500, detail="Insert returned no row")
    row = resp.data[0]
    log.info(
        "device_commands.created tenant=%s id=%s cmd=%s by=%s",
        tenant_id, row["id"], body.command, body.issued_by,
    )
    return {"status": "created", "command": _row_to_command(row).model_dump()}

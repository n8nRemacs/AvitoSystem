from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request

from src.dependencies import get_current_tenant
from src.middleware.auth import require_feature
from src.models.tenant import TenantContext
from src.models.session import (
    SessionUploadRequest, SessionStatus, TokenInfo,
    SessionHistoryItem, SessionHistoryResponse, AlertInfo, AlertsResponse,
)
from src.storage.supabase import get_supabase
from src.workers import jwt_parser
from src.workers.session_reader import load_active_session, load_session_history
from src.workers.token_monitor import get_alerts_for_session

router = APIRouter(prefix="/api/v1/sessions", tags=["Sessions"])


def _ttl_human(seconds: int) -> str:
    if seconds <= 0:
        return "expired"
    h, rem = divmod(seconds, 3600)
    m, _ = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


@router.post("", status_code=201)
async def upload_session(body: SessionUploadRequest, request: Request,
                         ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.sessions")

    # Validate JWT
    try:
        payload = jwt_parser.decode_jwt_payload(body.session_token)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid session_token: not a valid JWT")

    user_id = payload.get("user_id") or payload.get("sub")
    exp = payload.get("exp")
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat() if exp else None

    sb = get_supabase()

    # Deactivate previous active sessions for this tenant
    sb.table("avito_sessions").update({"is_active": False}).eq(
        "tenant_id", ctx.tenant.id
    ).eq("is_active", True).execute()

    # Build tokens JSONB
    tokens = {
        "session_token": body.session_token,
        "refresh_token": body.refresh_token,
        "device_id": body.device_id,
        "fingerprint": body.fingerprint,
        "remote_device_id": body.remote_device_id,
        "user_hash": body.user_hash,
        "cookies": body.cookies or {},
    }

    row = {
        "tenant_id": ctx.tenant.id,
        "tokens": tokens,
        "fingerprint": body.fingerprint,
        "device_id": body.device_id,
        "user_id": user_id,
        "source": body.source,
        "is_active": True,
        "expires_at": expires_at,
    }

    resp = sb.table("avito_sessions").insert(row).execute()

    # Audit log
    sb.table("audit_log").insert({
        "tenant_id": ctx.tenant.id,
        "action": "session.upload",
        "details": {"source": body.source, "user_id": user_id},
    }).execute()

    return {"status": "ok", "session_id": resp.data[0]["id"], "user_id": user_id}


@router.get("/current", response_model=SessionStatus)
async def get_current_session(request: Request,
                              ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.sessions")

    session = load_active_session(ctx.tenant.id)
    if not session:
        return SessionStatus(is_active=False)

    ttl = jwt_parser.time_left(session.session_token)

    return SessionStatus(
        is_active=True,
        user_id=session.user_id,
        source=session.source,
        ttl_seconds=ttl,
        ttl_human=_ttl_human(ttl),
        expires_at=session.expires_at,
        created_at=session.created_at,
        device_id=session.device_id,
        fingerprint_preview=session.fingerprint[:20] + "..." if session.fingerprint else None,
    )


@router.delete("")
async def delete_session(request: Request,
                         ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.sessions")

    sb = get_supabase()
    sb.table("avito_sessions").update({"is_active": False}).eq(
        "tenant_id", ctx.tenant.id
    ).eq("is_active", True).execute()

    sb.table("audit_log").insert({
        "tenant_id": ctx.tenant.id,
        "action": "session.deleted",
    }).execute()

    return {"status": "ok"}


@router.get("/history", response_model=SessionHistoryResponse)
async def get_session_history(request: Request,
                              ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.sessions")

    sessions = load_session_history(ctx.tenant.id)
    items = [
        SessionHistoryItem(
            id=s.id,
            user_id=s.user_id,
            source=s.source,
            is_active=s.is_active,
            created_at=s.created_at,
            expires_at=s.expires_at,
        )
        for s in sessions
    ]
    return SessionHistoryResponse(sessions=items, total=len(items))


@router.get("/token-details", response_model=TokenInfo)
async def get_token_details(request: Request,
                            ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.sessions")

    session = load_active_session(ctx.tenant.id)
    if not session:
        raise HTTPException(status_code=404, detail="No active session")

    try:
        header = jwt_parser.decode_jwt_header(session.session_token)
        payload = jwt_parser.decode_jwt_payload(session.session_token)
    except Exception:
        raise HTTPException(status_code=422, detail="Cannot decode token")

    exp = payload.get("exp")
    iat = payload.get("iat")

    return TokenInfo(
        header=header,
        payload=payload,
        expires_at=datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None,
        issued_at=datetime.fromtimestamp(iat, tz=timezone.utc) if iat else None,
        user_id=payload.get("user_id") or payload.get("sub"),
        ttl_seconds=jwt_parser.time_left(session.session_token),
        is_expired=jwt_parser.is_expired(session.session_token),
    )


@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(request: Request,
                     ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.sessions")

    session = load_active_session(ctx.tenant.id)
    if not session:
        return AlertsResponse(alerts=[
            AlertInfo(level="expired", message="No active session. Upload tokens or authorize.", ttl_seconds=None)
        ])

    raw_alerts = get_alerts_for_session(session)
    alerts = [AlertInfo(**a) for a in raw_alerts]
    return AlertsResponse(alerts=alerts)

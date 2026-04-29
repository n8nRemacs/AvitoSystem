import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.dependencies import get_current_tenant
from src.middleware.auth import require_feature
from src.models.tenant import TenantContext
from src.storage.supabase import get_supabase
from src.workers import jwt_parser

router = APIRouter(prefix="/api/v1/farm", tags=["Token Farm"])


# ── Request/Response models ────────────────────────────

class TokenUploadRequest(BaseModel):
    device_id: str
    android_profile_id: int
    session_token: str
    refresh_token: str | None = None
    fingerprint: str | None = None
    cookies: dict[str, str] | None = None


class HeartbeatRequest(BaseModel):
    device_id: str


class DeviceCreateRequest(BaseModel):
    name: str
    model: str | None = None
    serial: str | None = None
    max_profiles: int = 100
    api_key: str | None = None


class BindingCreateRequest(BaseModel):
    tenant_id: str
    farm_device_id: str
    android_profile_id: int
    avito_user_id: int | None = None
    avito_login: str | None = None


class DeviceResponse(BaseModel):
    id: str
    name: str
    model: str | None = None
    serial: str | None = None
    max_profiles: int = 100
    status: str = "online"
    last_heartbeat: str | None = None
    profile_count: int = 0


class BindingResponse(BaseModel):
    id: str
    tenant_id: str
    farm_device_id: str
    android_profile_id: int
    avito_user_id: int | None = None
    avito_login: str | None = None
    status: str = "active"
    last_refresh_at: str | None = None
    next_refresh_at: str | None = None


class ScheduleItem(BaseModel):
    binding_id: str
    android_profile_id: int
    avito_user_id: int | None = None
    next_refresh_at: str | None = None
    ttl_seconds: int | None = None


# ── Farm Agent endpoints ───────────────────────────────

@router.post("/tokens")
async def upload_farm_token(body: TokenUploadRequest, request: Request,
                            ctx: TenantContext = Depends(get_current_tenant)):
    """Farm Agent uploads a freshly intercepted token."""
    require_feature(request, "avito.farm")
    sb = get_supabase()

    # Find the binding
    binding_resp = sb.table("account_bindings").select("*").eq(
        "android_profile_id", body.android_profile_id
    ).execute()

    # Find matching device
    device_bindings = [b for b in binding_resp.data if True]  # filter later if needed
    if not device_bindings:
        raise HTTPException(status_code=404, detail="No binding found for this profile")

    binding = device_bindings[0]
    tenant_id = binding["tenant_id"]

    # Parse JWT
    try:
        payload = jwt_parser.decode_jwt_payload(body.session_token)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid session_token")

    user_id = payload.get("u") or payload.get("user_id") or payload.get("sub")
    exp = payload.get("exp")
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).isoformat() if exp else None

    # Deactivate old sessions for this tenant
    sb.table("avito_sessions").update({"is_active": False}).eq(
        "tenant_id", tenant_id
    ).eq("is_active", True).execute()

    # Insert new session
    tokens = {
        "session_token": body.session_token,
        "refresh_token": body.refresh_token,
        "fingerprint": body.fingerprint,
        "cookies": body.cookies or {},
    }

    sb.table("avito_sessions").insert({
        "tenant_id": tenant_id,
        "tokens": tokens,
        "fingerprint": body.fingerprint,
        "device_id": body.device_id,
        "user_id": user_id,
        "source": "farm",
        "is_active": True,
        "expires_at": expires_at,
    }).execute()

    # Update binding
    sb.table("account_bindings").update({
        "last_refresh_at": datetime.now(timezone.utc).isoformat(),
        "avito_user_id": user_id,
    }).eq("id", binding["id"]).execute()

    # Audit
    sb.table("audit_log").insert({
        "tenant_id": tenant_id,
        "action": "farm.token_upload",
        "details": {"device_id": body.device_id, "profile_id": body.android_profile_id},
    }).execute()

    return {"status": "ok", "tenant_id": tenant_id, "user_id": user_id}


@router.get("/schedule")
async def get_schedule(request: Request,
                       ctx: TenantContext = Depends(get_current_tenant)):
    """Get refresh schedule for farm devices."""
    require_feature(request, "avito.farm")
    sb = get_supabase()

    bindings = sb.table("account_bindings").select("*").eq("status", "active").execute()

    schedule = []
    for b in bindings.data:
        # Get active session for this tenant to check TTL
        session_resp = sb.table("avito_sessions").select("tokens").eq(
            "tenant_id", b["tenant_id"]
        ).eq("is_active", True).limit(1).execute()

        ttl = None
        if session_resp.data:
            token = session_resp.data[0].get("tokens", {}).get("session_token", "")
            if token:
                ttl = jwt_parser.time_left(token)

        schedule.append(ScheduleItem(
            binding_id=b["id"],
            android_profile_id=b["android_profile_id"],
            avito_user_id=b.get("avito_user_id"),
            next_refresh_at=b.get("next_refresh_at"),
            ttl_seconds=ttl,
        ))

    return {"schedule": schedule}


@router.post("/heartbeat")
async def heartbeat(body: HeartbeatRequest):
    """Heartbeat from farm device."""
    sb = get_supabase()
    sb.table("farm_devices").update({
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        "status": "online",
    }).eq("name", body.device_id).execute()
    return {"status": "ok"}


# ── Admin endpoints ────────────────────────────────────

@router.get("/devices")
async def list_devices(request: Request,
                       ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.farm")
    sb = get_supabase()
    devices = sb.table("farm_devices").select("*").execute()

    result = []
    for d in devices.data:
        # Count bindings
        bindings = sb.table("account_bindings").select("id").eq(
            "farm_device_id", d["id"]
        ).execute()

        result.append(DeviceResponse(
            id=d["id"],
            name=d["name"],
            model=d.get("model"),
            serial=d.get("serial"),
            max_profiles=d.get("max_profiles", 100),
            status=d.get("status", "offline"),
            last_heartbeat=d.get("last_heartbeat"),
            profile_count=len(bindings.data),
        ))

    return {"devices": result}


@router.post("/devices", status_code=201)
async def create_device(body: DeviceCreateRequest, request: Request,
                        ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.farm")
    sb = get_supabase()

    row = {
        "name": body.name,
        "model": body.model,
        "serial": body.serial,
        "max_profiles": body.max_profiles,
    }
    if body.api_key:
        row["api_key_hash"] = hashlib.sha256(body.api_key.encode()).hexdigest()

    resp = sb.table("farm_devices").insert(row).execute()
    return {"status": "ok", "device": resp.data[0]}


@router.get("/bindings")
async def list_bindings(request: Request,
                        ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.farm")
    sb = get_supabase()
    bindings = sb.table("account_bindings").select("*").execute()
    result = [BindingResponse(**b) for b in bindings.data]
    return {"bindings": result}


@router.post("/bindings", status_code=201)
async def create_binding(body: BindingCreateRequest, request: Request,
                         ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.farm")
    sb = get_supabase()

    row = {
        "tenant_id": body.tenant_id,
        "farm_device_id": body.farm_device_id,
        "android_profile_id": body.android_profile_id,
        "avito_user_id": body.avito_user_id,
        "avito_login": body.avito_login,
    }

    resp = sb.table("account_bindings").insert(row).execute()
    return {"status": "ok", "binding": resp.data[0]}


@router.delete("/bindings/{binding_id}")
async def delete_binding(binding_id: str, request: Request,
                         ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.farm")
    sb = get_supabase()
    sb.table("account_bindings").delete().eq("id", binding_id).execute()
    return {"status": "ok"}

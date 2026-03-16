import hashlib
import logging
from datetime import datetime, timezone

import jwt as pyjwt

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings
from src.storage.supabase import get_supabase
from src.models.tenant import Tenant, Toolkit, ApiKeyInfo, TenantContext

logger = logging.getLogger("xapi")


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


def _resolve_tenant_context(tenant_row: dict, sb, api_key_info: ApiKeyInfo | None = None) -> TenantContext | JSONResponse:
    """Shared logic to build TenantContext from a tenant DB row."""
    if not tenant_row["is_active"]:
        return _error(403, "Tenant is deactivated")

    # Check subscription
    sub_until = tenant_row.get("subscription_until")
    if sub_until:
        exp = datetime.fromisoformat(sub_until.replace("Z", "+00:00"))
        if exp < datetime.now(timezone.utc):
            return _error(403, "Subscription expired")

    # Lookup toolkit
    toolkit: Toolkit | None = None
    if tenant_row.get("toolkit_id"):
        tk_resp = sb.table("toolkits").select("*").eq("id", tenant_row["toolkit_id"]).execute()
        if tk_resp.data:
            tk_row = tk_resp.data[0]
            toolkit = Toolkit(
                id=tk_row["id"],
                supervisor_id=tk_row["supervisor_id"],
                name=tk_row["name"],
                features=tk_row["features"] if isinstance(tk_row["features"], list) else [],
                limits=tk_row.get("limits") or {},
                price_monthly=tk_row.get("price_monthly"),
                is_active=tk_row.get("is_active", True),
            )

    tenant = Tenant(
        id=tenant_row["id"],
        supervisor_id=tenant_row["supervisor_id"],
        toolkit_id=tenant_row.get("toolkit_id"),
        name=tenant_row["name"],
        email=tenant_row.get("email"),
        is_active=tenant_row["is_active"],
        subscription_until=tenant_row.get("subscription_until"),
        settings=tenant_row.get("settings") or {},
    )

    # If no api_key_info provided (JWT auth), create a placeholder
    if api_key_info is None:
        api_key_info = ApiKeyInfo(
            id="jwt-session",
            tenant_id=tenant_row["id"],
            name="JWT Session",
            is_active=True,
        )

    return TenantContext(
        tenant=tenant,
        toolkit=toolkit,
        api_key=api_key_info,
    )


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Resolve API key or JWT Bearer -> tenant -> toolkit on every /api/v1/* request."""

    SKIP_PATHS = {"/health", "/ready", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip auth for non-API paths and health checks
        if not path.startswith("/api/v1") or any(path == p for p in self.SKIP_PATHS):
            return await call_next(request)

        sb = get_supabase()

        # Try JWT Bearer first (if jwt_secret is configured)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer ") and settings.jwt_secret:
            token = auth_header[7:]
            try:
                payload = pyjwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
            except pyjwt.ExpiredSignatureError:
                return _error(401, "JWT token expired")
            except pyjwt.InvalidTokenError:
                # Not a valid JWT — fall through to API key check
                pass
            else:
                if payload.get("type") == "access" and payload.get("tenant_id"):
                    tenant_id = payload["tenant_id"]
                    tenant_resp = sb.table("tenants").select("*").eq("id", tenant_id).execute()
                    if not tenant_resp.data:
                        return _error(401, "Tenant not found")

                    result = _resolve_tenant_context(tenant_resp.data[0], sb)
                    if isinstance(result, JSONResponse):
                        return result

                    request.state.tenant_context = result
                    return await call_next(request)

        # Fall back to API key auth
        api_key = request.headers.get("X-Api-Key") or request.query_params.get("api_key")
        if not api_key:
            return _error(401, "Missing X-Api-Key header or Authorization: Bearer token")

        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        # Lookup API key
        key_resp = sb.table("api_keys").select("*").eq("key_hash", key_hash).eq("is_active", True).execute()
        if not key_resp.data:
            return _error(401, "Invalid API key")

        key_row = key_resp.data[0]

        # Lookup tenant
        tenant_resp = sb.table("tenants").select("*").eq("id", key_row["tenant_id"]).execute()
        if not tenant_resp.data:
            return _error(401, "Tenant not found")

        api_key_info = ApiKeyInfo(
            id=key_row["id"],
            tenant_id=key_row["tenant_id"],
            name=key_row.get("name"),
            is_active=key_row["is_active"],
        )

        result = _resolve_tenant_context(tenant_resp.data[0], sb, api_key_info)
        if isinstance(result, JSONResponse):
            return result

        request.state.tenant_context = result

        # Update last_used_at (fire and forget)
        try:
            sb.table("api_keys").update({"last_used_at": datetime.now(timezone.utc).isoformat()}).eq("id", key_row["id"]).execute()
        except Exception:
            pass

        return await call_next(request)


def require_feature(request: Request, feature: str) -> None:
    """Check that the tenant's toolkit includes a specific feature."""
    ctx: TenantContext = getattr(request.state, "tenant_context", None)
    if ctx is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if ctx.toolkit is None:
        raise HTTPException(status_code=403, detail="No toolkit assigned")
    if feature not in ctx.toolkit.features:
        raise HTTPException(status_code=403, detail=f"Feature '{feature}' not available in your toolkit")

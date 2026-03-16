from fastapi import Request, HTTPException
from src.models.tenant import TenantContext


def get_current_tenant(request: Request) -> TenantContext:
    """Extract resolved tenant context from request state (set by auth middleware)."""
    ctx: TenantContext | None = getattr(request.state, "tenant_context", None)
    if ctx is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return ctx

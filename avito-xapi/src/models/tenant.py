from pydantic import BaseModel
from datetime import datetime
from typing import Any


class Supervisor(BaseModel):
    id: str
    name: str
    email: str | None = None
    is_active: bool = True
    settings: dict[str, Any] = {}


class Toolkit(BaseModel):
    id: str
    supervisor_id: str
    name: str
    features: list[str]
    limits: dict[str, Any] = {}
    price_monthly: float | None = None
    is_active: bool = True


class Tenant(BaseModel):
    id: str
    supervisor_id: str
    toolkit_id: str | None = None
    name: str
    email: str | None = None
    is_active: bool = True
    subscription_until: datetime | None = None
    settings: dict[str, Any] = {}


class ApiKeyInfo(BaseModel):
    id: str
    tenant_id: str
    name: str | None = None
    is_active: bool = True


class TenantContext(BaseModel):
    """Resolved tenant context attached to each request."""
    tenant: Tenant
    toolkit: Toolkit | None = None
    api_key: ApiKeyInfo

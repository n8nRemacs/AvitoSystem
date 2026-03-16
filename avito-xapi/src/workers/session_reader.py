from dataclasses import dataclass
from typing import Any
from src.storage.supabase import get_supabase


@dataclass
class SessionData:
    """Loaded Avito session from Supabase."""
    id: str
    tenant_id: str
    session_token: str
    refresh_token: str | None
    device_id: str | None
    fingerprint: str | None
    remote_device_id: str | None
    user_hash: str | None
    user_id: int | None
    cookies: dict[str, str] | None
    source: str
    is_active: bool
    expires_at: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "SessionData":
        tokens = row.get("tokens", {})
        return cls(
            id=row["id"],
            tenant_id=row["tenant_id"],
            session_token=tokens.get("session_token", ""),
            refresh_token=tokens.get("refresh_token"),
            device_id=row.get("device_id") or tokens.get("device_id"),
            fingerprint=row.get("fingerprint") or tokens.get("fingerprint"),
            remote_device_id=tokens.get("remote_device_id"),
            user_hash=tokens.get("user_hash"),
            user_id=row.get("user_id"),
            cookies=tokens.get("cookies"),
            source=row["source"],
            is_active=row.get("is_active", True),
            expires_at=row.get("expires_at"),
            created_at=row["created_at"],
        )


def load_active_session(tenant_id: str) -> SessionData | None:
    """Load the current active session for a tenant from Supabase."""
    sb = get_supabase()
    resp = (
        sb.table("avito_sessions")
        .select("*")
        .eq("tenant_id", tenant_id)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return SessionData.from_row(resp.data[0])


def load_session_history(tenant_id: str, limit: int = 50) -> list[SessionData]:
    """Load session history for a tenant."""
    sb = get_supabase()
    resp = (
        sb.table("avito_sessions")
        .select("*")
        .eq("tenant_id", tenant_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [SessionData.from_row(row) for row in resp.data]

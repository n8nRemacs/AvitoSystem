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
            id=row.get("id", ""),
            tenant_id=row.get("tenant_id", ""),
            session_token=tokens.get("session_token", ""),
            refresh_token=tokens.get("refresh_token"),
            device_id=row.get("device_id") or tokens.get("device_id"),
            fingerprint=row.get("fingerprint") or tokens.get("fingerprint"),
            remote_device_id=tokens.get("remote_device_id"),
            user_hash=tokens.get("user_hash"),
            user_id=row.get("user_id"),
            cookies=tokens.get("cookies"),
            source=row.get("source", ""),
            is_active=row.get("is_active", True),
            expires_at=row.get("expires_at"),
            created_at=row.get("created_at", ""),
        )


def _row_to_session_data(row: dict[str, Any]) -> SessionData:
    """Convert a raw Supabase row dict to SessionData.

    Extracted as a private helper so both load_session_for_account
    and load_active_session can reuse conversion logic without duplication.
    """
    return SessionData.from_row(row)


async def load_session_for_account(sb: Any, account_id: str) -> SessionData | None:
    """Pool-aware session loader: returns the active session for a specific account.

    Queries avito_sessions WHERE account_id = account_id AND is_active = True LIMIT 1.
    Returns SessionData if found, None otherwise.
    """
    resp = (
        sb.table("avito_sessions")
        .select("*")
        .eq("account_id", account_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return _row_to_session_data(resp.data[0])


async def load_active_session(sb: Any = None, tenant_id: str | None = None) -> SessionData | None:
    """Load the most recent active session from Supabase.

    # DEPRECATED: Use load_session_for_account(sb, account_id) for pool-aware loading.
    Legacy wrapper for non-pool code paths. Returns any active session
    (any account), ordered by created_at DESC LIMIT 1.

    Backward-compat note: if called as load_active_session(tenant_id_str),
    the positional arg is detected and treated as tenant_id with internal get_supabase().
    """
    # Backward-compat shim: old callers pass tenant_id as first positional arg (a str)
    if isinstance(sb, str):
        # sb is actually tenant_id; get real sb from singleton
        _sb = get_supabase()
        _tenant_id = sb
        resp = (
            _sb.table("avito_sessions")
            .select("*")
            .eq("tenant_id", _tenant_id)
            .eq("is_active", True)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not resp.data:
            return None
        return _row_to_session_data(resp.data[0])

    # New async pool-aware path: sb is a real client
    if sb is None:
        sb = get_supabase()

    resp = (
        sb.table("avito_sessions")
        .select("*")
        .eq("is_active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not resp.data:
        return None
    return _row_to_session_data(resp.data[0])


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
    return [_row_to_session_data(row) for row in resp.data]

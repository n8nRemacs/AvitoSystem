from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Literal


class SessionUploadRequest(BaseModel):
    """Request body for uploading an Avito session."""
    session_token: str
    refresh_token: str | None = None
    device_id: str | None = None
    fingerprint: str | None = None
    remote_device_id: str | None = None
    user_hash: str | None = None
    cookies: dict[str, str] | None = None
    source: Literal["android", "redroid", "manual", "farm", "browser"] = "manual"


class SessionStatus(BaseModel):
    """Current session status."""
    is_active: bool
    user_id: int | None = None
    source: str | None = None
    ttl_seconds: int | None = None
    ttl_human: str | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None
    device_id: str | None = None
    fingerprint_preview: str | None = None


class TokenInfo(BaseModel):
    """Decoded JWT token details."""
    header: dict[str, Any] = {}
    payload: dict[str, Any] = {}
    expires_at: datetime | None = None
    issued_at: datetime | None = None
    user_id: int | None = None
    ttl_seconds: int | None = None
    is_expired: bool = True


class SessionHistoryItem(BaseModel):
    """Single entry in session history."""
    id: str
    user_id: int | None = None
    source: str
    is_active: bool
    created_at: datetime
    expires_at: datetime | None = None


class SessionHistoryResponse(BaseModel):
    """Session history list."""
    sessions: list[SessionHistoryItem]
    total: int


class AlertInfo(BaseModel):
    """Token alert."""
    level: Literal["warning", "critical", "expired"]
    message: str
    ttl_seconds: int | None = None


class AlertsResponse(BaseModel):
    """Current alerts."""
    alerts: list[AlertInfo]

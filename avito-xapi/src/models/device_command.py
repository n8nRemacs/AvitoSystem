"""Pydantic schemas for the device-command channel.

See ``supabase/migrations/006_avito_device_commands.sql`` for the
backing table and the rationale behind each field.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DeviceCommand(BaseModel):
    """One command row, returned to the APK via long-poll."""

    id: str
    command: str = Field(..., description="e.g. 'refresh_token'")
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    expire_at: datetime | None = None


class CommandAckRequest(BaseModel):
    """APK posts this after attempting to execute a command."""

    ok: bool
    error: str | None = None
    payload: dict[str, Any] | None = None


class CommandCreateRequest(BaseModel):
    """Server-side admin insert (health-checker, manual TG admin, ...).

    ``dedup_window_sec`` short-circuits the insert if a row with the
    same (tenant, command) was created within that window and is still
    pending/delivered. Default 5 min mirrors the health-checker's
    re-check cadence.
    """

    command: str
    payload: dict[str, Any] = Field(default_factory=dict)
    dedup_window_sec: int = 300
    expire_after_sec: int = 180
    issued_by: str | None = None

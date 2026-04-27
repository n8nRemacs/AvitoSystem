"""Pydantic models for the V2.1 notification interception channel."""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class NotificationIngestRequest(BaseModel):
    """Payload posted by AvitoSessionManager APK when it intercepts an
    Android notification from com.avito.android (or any package the user
    chooses to forward)."""

    source: str = "android_notification"
    package_name: str | None = None

    notification_id: int | None = None
    tag: str | None = None

    title: str | None = None
    body: str | None = Field(default=None, alias="text")
    big_text: str | None = None
    sub_text: str | None = None

    posted_at: datetime | None = None
    extras: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class NotificationIngestResponse(BaseModel):
    status: str = "ok"
    notification_id: int
    broadcast: bool


class NotificationStats(BaseModel):
    total: int = 0
    last_24h: int = 0
    last_received_at: datetime | None = None
    by_source: dict[str, int] = Field(default_factory=dict)
    by_package: dict[str, int] = Field(default_factory=dict)

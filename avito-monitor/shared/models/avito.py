"""Pydantic models shared between avito_mcp and the main backend.

These wrap the normalized response of avito-xapi (`/api/v1/search/items` and
`/api/v1/search/items/{id}`) and are the public schema returned by avito-mcp tools.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ListingImage(BaseModel):
    """Single image attached to a listing."""

    url: str
    width: int | None = None
    height: int | None = None
    index: int | None = None


class ListingShort(BaseModel):
    """Compact listing record returned in search results."""

    model_config = ConfigDict(extra="ignore")

    id: int
    title: str
    price: int | None = None
    price_text: str | None = None
    currency: str = "RUB"
    region: str | None = None
    address: str | None = None
    url: str | None = None
    images: list[ListingImage] = Field(default_factory=list)
    seller_id: int | str | None = None
    seller_type: str | None = None  # "private" | "company" | None
    first_seen: str | None = None  # ISO timestamp from avito (createdAt/time)


class ListingDetail(ListingShort):
    """Full listing detail; superset of ListingShort + description / params."""

    description: str | None = None
    category: str | None = None
    seller_name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    raw_data: dict[str, Any] = Field(default_factory=dict)


class SearchPage(BaseModel):
    """Single page of a search query."""

    items: list[ListingShort]
    total: int | None = None
    page: int = 1
    has_more: bool = False
    source_url: str | None = None
    applied_query: str | None = None


class HealthStatus(BaseModel):
    """Result of avito_health_check()."""

    xapi_reachable: bool
    avito_reachable: bool  # we proxy via xapi, so True iff xapi has an active session
    session_active: bool = False
    session_ttl_hours: float | None = None
    session_ttl_human: str | None = None
    last_error: str | None = None

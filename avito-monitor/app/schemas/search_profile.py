from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ParsedUrlPreview(BaseModel):
    region_slug: str | None = None
    region_name: str | None = None
    category_human: str | None = None
    brand: str | None = None
    model: str | None = None
    query: str | None = None
    pmin: int | None = None
    pmax: int | None = None
    sort: int | None = None
    only_with_delivery: bool | None = None
    suggested_name: str
    suggested_search_min: int | None = None
    suggested_search_max: int | None = None


class SearchProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    avito_search_url: str = Field(min_length=1)

    region_slug: str | None = None
    only_with_delivery: bool | None = None
    sort: int | None = None

    search_min_price: int | None = Field(None, ge=0)
    search_max_price: int | None = Field(None, ge=0)
    alert_min_price: int | None = Field(None, ge=0)
    alert_max_price: int | None = Field(None, ge=0)

    custom_criteria: str | None = None
    allowed_conditions: list[str] = Field(default_factory=lambda: ["working"])
    llm_classify_model: str | None = None
    llm_match_model: str | None = None
    analyze_photos: bool = False

    poll_interval_minutes: int = Field(15, ge=1, le=1440)
    active_hours: dict[str, Any] | None = None
    is_active: bool = True

    blocked_sellers: list[str] = Field(default_factory=list)
    notification_settings: dict[str, Any] = Field(default_factory=dict)
    notification_channels: list[str] = Field(default_factory=lambda: ["telegram"])


class SearchProfileCreate(SearchProfileBase):
    pass


class SearchProfileUpdate(BaseModel):
    """All fields optional for PATCH."""
    name: str | None = None
    avito_search_url: str | None = None
    region_slug: str | None = None
    only_with_delivery: bool | None = None
    sort: int | None = None
    search_min_price: int | None = None
    search_max_price: int | None = None
    alert_min_price: int | None = None
    alert_max_price: int | None = None
    custom_criteria: str | None = None
    allowed_conditions: list[str] | None = None
    llm_classify_model: str | None = None
    llm_match_model: str | None = None
    analyze_photos: bool | None = None
    poll_interval_minutes: int | None = None
    active_hours: dict[str, Any] | None = None
    is_active: bool | None = None
    blocked_sellers: list[str] | None = None
    notification_settings: dict[str, Any] | None = None
    notification_channels: list[str] | None = None


class SearchProfileRead(SearchProfileBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    parsed_brand: str | None = None
    parsed_model: str | None = None
    parsed_category: str | None = None
    created_at: datetime
    updated_at: datetime

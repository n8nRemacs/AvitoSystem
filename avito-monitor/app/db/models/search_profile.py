import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class SearchProfile(Base, TimestampMixin):
    __tablename__ = "search_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    name: Mapped[str] = mapped_column(String(255))
    avito_search_url: Mapped[str] = mapped_column(Text)

    # parsed denormalization (filled by URL parser)
    parsed_brand: Mapped[str | None] = mapped_column(String(128))
    parsed_model: Mapped[str | None] = mapped_column(String(255))
    parsed_category: Mapped[str | None] = mapped_column(String(255))

    # overlay
    region_slug: Mapped[str | None] = mapped_column(String(64))
    only_with_delivery: Mapped[bool | None] = mapped_column(Boolean)
    sort: Mapped[int | None] = mapped_column(Integer)

    # dual price range (ADR-008)
    search_min_price: Mapped[int | None] = mapped_column(Integer)
    search_max_price: Mapped[int | None] = mapped_column(Integer)
    alert_min_price: Mapped[int | None] = mapped_column(Integer)
    alert_max_price: Mapped[int | None] = mapped_column(Integer)

    # LLM (ADR-010 — legacy, kept read-only through Phase B–C)
    custom_criteria: Mapped[str | None] = mapped_column(Text)
    allowed_conditions: Mapped[list[str]] = mapped_column(
        JSONB, default=lambda: ["working"]
    )
    llm_classify_model: Mapped[str | None] = mapped_column(String(128))
    llm_match_model: Mapped[str | None] = mapped_column(String(128))
    analyze_photos: Mapped[bool] = mapped_column(Boolean, default=False)

    # V2 LLM pipeline (flag-based evaluation, hot-switchable strategy)
    evaluate_strategy: Mapped[str] = mapped_column(
        String(16), default="per_criterion"
    )
    confidence_threshold: Mapped[float] = mapped_column(
        Numeric(4, 3), default=0.7
    )
    # sha256 of (sorted criteria keys + versions + params + prompt version);
    # cheap to compare during polling to know if cached evaluations are stale.
    criteria_set_hash: Mapped[str | None] = mapped_column(String(64))
    bucket_routing: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # schedule
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    active_hours: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # blocking + notif config
    blocked_sellers: Mapped[list[str]] = mapped_column(JSONB, default=list)
    notification_settings: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    notification_channels: Mapped[list[str]] = mapped_column(
        JSONB, default=lambda: ["telegram"]
    )

    # autosearch sync (ADR-011)
    avito_autosearch_id: Mapped[str | None] = mapped_column(Text)
    import_source: Mapped[str] = mapped_column(String(32), default="manual_url")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Polling humanization: timestamp of the most recent full-pagination
    # tick. NULL = never paginated → next tick MUST do a full walk.
    # Otherwise we only fetch page=1 unless >1h has passed since this.
    last_full_poll_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # parsed structured search params from Avito mobile API
    # (categoryId, locationId, params[N][N]=…, priceMin/Max, sort, withDeliveryOnly)
    search_params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # account pool: который Avito-аккаунт является «владельцем» этого autosearch
    # на стороне Avito. UUID на avito_accounts.id в Supabase (cross-DB → no FK).
    # Используется sync /5/subscriptions (per-account) и V2 messenger flow.
    owner_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True
    )

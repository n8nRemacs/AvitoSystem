"""Per (profile, listing) bucket verdict from the V2 LLM pipeline.

One row per evaluation run. Holds the structured per-criterion flags
and per-info-field extractions, plus the bucket Python computed from
them. The actual LLM call results live in ``llm_analyses`` (granular
per-criterion rows) — we keep an aggregate snapshot here so the UI
can render a profile's listing list without joining N rows per item.
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ProfileListingEvaluation(Base, TimestampMixin):
    __tablename__ = "profile_listing_evaluations"
    __table_args__ = (
        Index(
            "ix_profile_listing_evaluations_profile_listing",
            "profile_id",
            "listing_id",
        ),
        Index(
            "ix_profile_listing_evaluations_profile_bucket",
            "profile_id",
            "bucket",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="CASCADE"),
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
    )

    bucket: Mapped[str] = mapped_column(String(8))  # green / grey / red
    confidence_threshold: Mapped[float] = mapped_column(Numeric(4, 3), default=0.7)
    criteria_flags: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    info_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    red_criterion_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    criteria_set_hash: Mapped[str] = mapped_column(String(64))

    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

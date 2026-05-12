"""SQLAlchemy model for the listing_features table.

One row per (listing, feature_key). Written by the defect-feature parser
(Avito-parameter matcher / LLM section parser / seller-dialog inbound
broad-scan in Phase 2). UPSERT on (listing_id, feature_key) — last
write wins so a freshly re-parsed listing supersedes stale rows.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ListingFeature(Base):
    __tablename__ = "listing_features"
    __table_args__ = (
        UniqueConstraint("listing_id", "feature_key",
                         name="uq_listing_features_listing_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    # state ∈ {'ok', 'defect', 'unknown'}
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    # source ∈ {'avito_parameters', 'llm', 'description_kw', 'seller_dialog'}
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )

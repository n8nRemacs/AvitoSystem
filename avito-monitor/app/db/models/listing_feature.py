"""SQLAlchemy model for the listing_features table.

One row per (listing, feature_key). Written by the defect-feature parser
(Avito-parameter matcher / LLM section parser / seller-dialog inbound
broad-scan in Phase 2). UPSERT on (listing_id, feature_key) — last
write wins so a freshly re-parsed listing supersedes stale rows.

Phase 2.1: `kind` column discriminates feature type:
  - 'defect'       — condition/lock defects; state NOT NULL (DB CHECK constraint)
  - 'price_signal' — battery_health, repaired_components; value NOT NULL, state NULL
  - 'info_api'     — memory_gb, color, vendor_model; value NOT NULL, state NULL
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
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
    # Phase 2.1: kind discriminates defect / price_signal / info_api rows.
    kind: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="defect",
    )
    # state ∈ {'ok', 'defect', 'unknown'} — required for kind='defect', NULL otherwise.
    state: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Phase 2.1: value stores structured payload for price_signal / info_api kinds.
    # SQLite tests use TEXT (JSONB is Postgres-only; conftest uses hand-written DDL).
    value: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # source ∈ {'avito_parameters', 'llm', 'avito_params', 'description_kw', 'seller_dialog'}
    # NOT NULL in DB (0015 added) — all writers must set this. Phase 2.1
    # price_signal → 'llm', info_api → 'avito_params'.
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )

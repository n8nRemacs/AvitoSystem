"""SQLAlchemy model for the profile_feature_rules table.

One row per (profile, feature_key). Operator-edited through the
/profiles/{id}/feature-rules page. Drives per-profile bucketing.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProfileFeatureRule(Base):
    __tablename__ = "profile_feature_rules"
    __table_args__ = (
        UniqueConstraint("profile_id", "feature_key",
                         name="uq_profile_feature_rules_profile_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    rule: Mapped[str] = mapped_column(String(16), nullable=False)
    # rule ∈ {'green', 'red', 'ignore'}
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )

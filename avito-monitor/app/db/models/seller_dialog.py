"""Seller-side dialog state machine — Phase A skeleton.

One row per (profile, listing) tracking the current pipeline stage. Later
phases will extend with SLA timers, target/final price, shipping method,
return reason, extracted data JSONB, etc.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SellerDialog(Base):
    __tablename__ = "seller_dialogs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["profile_id", "listing_id"],
            ["profile_listings.profile_id", "profile_listings.listing_id"],
            ondelete="CASCADE",
            name="fk_seller_dialogs_profile_listing",
        ),
        UniqueConstraint(
            "profile_id", "listing_id",
            name="uq_seller_dialogs_profile_listing",
        ),
        CheckConstraint(
            "stage IN ('contact','questions_setup','questions','price_negotiation',"
            "'price_changed','purchased','shipped','received','closed','rejected')",
            name="ck_seller_dialogs_stage",
        ),
        Index("ix_seller_dialogs_channel_id", "channel_id"),
        Index("ix_seller_dialogs_stage", "stage"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel_id: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    operator_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_reason: Mapped[str | None] = mapped_column(String(32))
    recap_text: Mapped[str | None] = mapped_column(Text)
    recap_msg_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("messenger_messages.id"),
    )
    recap_status: Mapped[str | None] = mapped_column(String(16))

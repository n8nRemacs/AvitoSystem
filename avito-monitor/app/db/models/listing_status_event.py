"""Append-only audit log of listing price + status transitions.

One row per observed change — produced by the polling worker when it spots
a price update, a reservation flip, or captures the ``reserved_at_price``
snapshot. Kept deliberately simple and free-form (TEXT old/new) so the same
table covers both prices (decimal strings) and statuses (enum strings)
without a polymorphic schema.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ListingStatusEvent(Base):
    __tablename__ = "listing_status_events"
    __table_args__ = (
        Index(
            "ix_listing_status_events_listing_at",
            "listing_id",
            "at",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 'status_change' | 'price_change' | 'reservation_capture'
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

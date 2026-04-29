import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserListingBlacklist(Base):
    """Per-user global blacklist of listings.

    A row is created when the user rejects a listing in /listings; from then on
    the polling pipeline must not surface that listing in any of the user's
    profiles, even if the profile criteria change. See ADR-011.
    """

    __tablename__ = "user_listing_blacklist"
    __table_args__ = (
        Index("ix_user_listing_blacklist_user_id", "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    reason: Mapped[str] = mapped_column(String(32), default="rejected")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

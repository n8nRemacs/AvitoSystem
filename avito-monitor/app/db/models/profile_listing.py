import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.enums import ProcessingStatus, UserAction


class ProfileListing(Base):
    """M:N link between SearchProfile and Listing with processing metadata."""

    __tablename__ = "profile_listings"
    __table_args__ = (
        Index("ix_profile_listings_profile_discovered", "profile_id", "discovered_at"),
        Index("ix_profile_listings_profile_status", "profile_id", "processing_status"),
        Index("ix_profile_listings_profile_alert", "profile_id", "in_alert_zone"),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        primary_key=True,
    )

    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processing_status: Mapped[str] = mapped_column(
        String(32), default=ProcessingStatus.FETCHED.value
    )
    in_alert_zone: Mapped[bool] = mapped_column(Boolean, default=False)
    condition_classification_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_analyses.id", ondelete="SET NULL")
    )
    match_result_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("llm_analyses.id", ondelete="SET NULL")
    )
    user_action: Mapped[str | None] = mapped_column(
        String(16), default=UserAction.PENDING.value
    )

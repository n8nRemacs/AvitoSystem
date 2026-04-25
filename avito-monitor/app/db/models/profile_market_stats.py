import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ProfileMarketStats(Base, TimestampMixin):
    """Aggregated market metrics per profile per period (ADR-009)."""

    __tablename__ = "profile_market_stats"
    __table_args__ = (
        UniqueConstraint(
            "profile_id", "granularity", "period_start",
            name="uq_profile_market_stats_period",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    granularity: Mapped[str] = mapped_column(String(8))  # day / week / month
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    listings_count: Mapped[int] = mapped_column(Integer, default=0)
    new_listings_count: Mapped[int] = mapped_column(Integer, default=0)
    disappeared_listings_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_listing_lifetime_hours: Mapped[float | None] = mapped_column(Numeric(10, 2))

    price_median_raw: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_median_clean: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_mean: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_min: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_max: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_p25_clean: Mapped[float | None] = mapped_column(Numeric(12, 2))
    price_p75_clean: Mapped[float | None] = mapped_column(Numeric(12, 2))

    working_share: Mapped[float | None] = mapped_column(Numeric(5, 4))
    condition_distribution: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PriceAnalysis(Base, TimestampMixin):
    """User-defined price-intelligence query (the *what*).

    Each row holds the reference (own listing URL or manual data) plus
    the search params used to find competitors. Re-running the analysis
    creates a new ``PriceAnalysisRun``.
    """

    __tablename__ = "price_analyses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255))

    # reference: either a URL (we'll fetch via avito-mcp) or manually filled JSON
    reference_listing_url: Mapped[str | None] = mapped_column(Text)
    reference_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # competitor search overlay
    search_region: Mapped[str | None] = mapped_column(String(64))
    search_radius_km: Mapped[int | None] = mapped_column(Integer)
    competitor_filters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    max_competitors: Mapped[int] = mapped_column(Integer, default=30)

    llm_model: Mapped[str | None] = mapped_column(String(128))
    # schedule: cron string for periodic re-runs (V1: just stored, scheduler in V2)
    schedule: Mapped[str | None] = mapped_column(Text)

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PriceAnalysisRun(Base, TimestampMixin):
    """One execution of a :class:`PriceAnalysis` (the *when*).

    The full per-competitor breakdown lives in ``competitor_data`` (a
    JSONB list). The aggregate report (price-range, top-5 cheaper /
    pricier, recommendation, conclusion) lives in ``report``.
    """

    __tablename__ = "price_analysis_runs"
    __table_args__ = (
        Index(
            "ix_price_analysis_runs_analysis_started",
            "analysis_id",
            "started_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("price_analyses.id", ondelete="CASCADE"),
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running")

    report: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    competitor_data: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    competitors_found: Mapped[int] = mapped_column(Integer, default=0)
    comparable_count: Mapped[int] = mapped_column(Integer, default=0)

    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    error_message: Mapped[str | None] = mapped_column(Text)

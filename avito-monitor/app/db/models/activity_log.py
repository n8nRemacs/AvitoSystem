from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ActivityLog(Base):
    """V2 reliability — every messenger-touching action (simulator, bot, health, manual)."""

    __tablename__ = "activity_log"
    __table_args__ = (
        Index("ix_activity_log_ts", "ts"),
        Index("ix_activity_log_source_ts", "source", "ts"),
    )

    id: Mapped[int] = mapped_column(BigInteger, autoincrement=True, primary_key=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source: Mapped[str | None] = mapped_column(Text)  # 'simulator' | 'bot' | 'health_checker' | 'manual'
    action: Mapped[str | None] = mapped_column(Text)
    target: Mapped[str | None] = mapped_column(Text)  # channel_id / item_id
    status: Mapped[str | None] = mapped_column(Text)  # 'ok' | 'error' | 'rate_limited'
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

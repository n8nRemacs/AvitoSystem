import uuid
from typing import Any

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class LLMAnalysis(Base, TimestampMixin):
    __tablename__ = "llm_analyses"
    __table_args__ = (
        Index("ix_llm_analyses_cache_key", "cache_key"),
        Index("ix_llm_analyses_listing_type", "listing_id", "type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listings.id", ondelete="CASCADE")
    )
    type: Mapped[str] = mapped_column(String(16))  # condition / match / compare
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    cache_key: Mapped[str] = mapped_column(String(128))

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    result: Mapped[dict[str, Any]] = mapped_column(JSONB)

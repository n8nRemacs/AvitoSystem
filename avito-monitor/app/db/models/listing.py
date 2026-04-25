import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.models.enums import ConditionClass, ListingStatus, SellerType


class Listing(Base, TimestampMixin):
    __tablename__ = "listings"
    __table_args__ = (
        Index("ix_listings_status_first_seen", "status", "first_seen_at"),
        Index("ix_listings_condition_class", "condition_class"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    avito_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)

    title: Mapped[str] = mapped_column(String(512))
    price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    initial_price: Mapped[float | None] = mapped_column(Numeric(12, 2))
    last_price_change_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    currency: Mapped[str] = mapped_column(String(8), default="RUB")

    region: Mapped[str | None] = mapped_column(String(128))
    url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    images: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    seller_id: Mapped[str | None] = mapped_column(String(64))
    seller_type: Mapped[str | None] = mapped_column(
        String(16),
        default=SellerType.PRIVATE.value,
    )
    seller_info: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # LLM classification (filled by Block 4)
    condition_class: Mapped[str] = mapped_column(
        String(32), default=ConditionClass.UNKNOWN.value
    )
    condition_confidence: Mapped[float | None] = mapped_column(Float)
    condition_reasoning: Mapped[str | None] = mapped_column(Text)

    avito_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    avito_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(
        String(16), default=ListingStatus.ACTIVE.value
    )
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

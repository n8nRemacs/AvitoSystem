from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessengerChat(Base):
    """V2 reliability — local cache of Avito messenger chats (channels)."""

    __tablename__ = "messenger_chats"
    __table_args__ = (
        Index("ix_messenger_chats_last_message_at", "last_message_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # avito channel_id (u2i-...)
    contact_id: Mapped[str | None] = mapped_column(Text)
    contact_name: Mapped[str | None] = mapped_column(Text)
    item_id: Mapped[int | None] = mapped_column(BigInteger)
    is_my_listing: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

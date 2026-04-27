from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessengerMessage(Base):
    """V2 reliability — local cache of Avito messenger messages."""

    __tablename__ = "messenger_messages"
    __table_args__ = (
        Index("ix_messenger_messages_channel_created", "channel_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # avito message_id
    channel_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("messenger_chats.id", ondelete="CASCADE"),
        nullable=False,
    )
    direction: Mapped[str | None] = mapped_column(Text)  # 'in' | 'out'
    author_id: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(Text)  # 'text' | 'image' | 'voice' | 'system'
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

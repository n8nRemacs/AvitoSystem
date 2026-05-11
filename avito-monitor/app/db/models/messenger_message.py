import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MessengerMessage(Base):
    """V2 reliability + V1 seller-dialog — local cache of Avito messenger messages.

    ``dialog_id`` discriminates the two flows:
      - NULL = reliability-bot message (auto-reply to inbound on someone else's lot)
      - NOT NULL = seller-dialog message (our outbound greeting, q&a, or
        seller's reply to it)
    """

    __tablename__ = "messenger_messages"
    __table_args__ = (
        Index("ix_messenger_messages_channel_created", "channel_id", "created_at"),
        Index("ix_messenger_messages_dialog_id", "dialog_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # avito message_id
    channel_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("messenger_chats.id", ondelete="CASCADE"),
        nullable=False,
    )
    dialog_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("seller_dialogs.id", ondelete="SET NULL"),
        nullable=True,
    )
    direction: Mapped[str | None] = mapped_column(Text)  # 'in' | 'out'
    author_id: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(Text)  # 'text' | 'image' | 'voice' | 'system'
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

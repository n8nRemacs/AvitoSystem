from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatDialogState(Base):
    """V2 reliability — per-channel dialog FSM state.

    V2.0 states: 'replied_with_template' | 'no_action'.
    V2.1+ adds: 'qualifying' | 'qualified' | 'cold' | 'handoff' | 'closed'.
    """

    __tablename__ = "chat_dialog_state"

    channel_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("messenger_chats.id", ondelete="CASCADE"),
        primary_key=True,
    )
    state: Mapped[str] = mapped_column(Text, nullable=False)
    bot_replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bot_reply_message_id: Mapped[str | None] = mapped_column(Text)
    last_qualified_lead_score: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class SellerDialogTopic(Base):
    """Per-dialog state of a topic — pending/asked/answered/skipped."""

    __tablename__ = "seller_dialog_topics"
    __table_args__ = (
        Index("ix_seller_dialog_topics_dialog", "dialog_id"),
        Index("ix_seller_dialog_topics_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
    )
    dialog_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("seller_dialogs.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_key: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("dialog_topics.key"),
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    question_text: Mapped[str | None] = mapped_column(Text)
    question_msg_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("messenger_messages.id"),
    )
    answer_text: Mapped[str | None] = mapped_column(Text)
    answer_msg_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("messenger_messages.id"),
    )
    asked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

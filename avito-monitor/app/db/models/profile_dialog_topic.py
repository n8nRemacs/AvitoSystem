import uuid
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ProfileDialogTopic(Base):
    """Which baseline topics a profile includes."""

    __tablename__ = "profile_dialog_topics"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    topic_key: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("dialog_topics.key", ondelete="CASCADE"),
        primary_key=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=0)

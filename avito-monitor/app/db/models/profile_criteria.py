"""Per-profile selection of library templates + custom criteria/info-fields.

A row is either a reference to a global :class:`CriteriaTemplate` (with
optional filled-in ``params``) OR a fully custom criterion/info-field
defined inline (``custom_*`` columns). Exactly one of these two shapes
is populated per row.
"""
import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ProfileCriterion(Base, TimestampMixin):
    __tablename__ = "profile_criteria"
    __table_args__ = (
        Index("ix_profile_criteria_profile", "profile_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="CASCADE"),
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("criteria_templates.id", ondelete="RESTRICT"),
    )

    # custom_* are filled when this is a per-profile criterion (template_id NULL)
    custom_key: Mapped[str | None] = mapped_column(String(64))
    custom_title_ru: Mapped[str | None] = mapped_column(String(255))
    custom_kind: Mapped[str | None] = mapped_column(String(16))
    custom_prompt_fragment: Mapped[str | None] = mapped_column(Text)

    # filled-in template params (e.g. {"gb": 256} for memory_gte)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    is_hard: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

"""Global criterion / info-field library (V2 LLM pipeline).

Source of truth is ``app/data/criteria_templates.yaml`` — the seed
migration upserts rows from there. Bumping ``version`` invalidates any
``llm_analyses`` rows whose cache_key embedded the old version, so a
template prompt change automatically forces a re-grading.
"""
import uuid
from typing import Any

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class CriteriaTemplate(Base, TimestampMixin):
    __tablename__ = "criteria_templates"
    __table_args__ = (UniqueConstraint("key", name="uq_criteria_templates_key"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    key: Mapped[str] = mapped_column(String(64))
    title_ru: Mapped[str] = mapped_column(String(255))
    description_ru: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))  # CriteriaTemplateKind
    prompt_fragment: Mapped[str | None] = mapped_column(Text)
    api_path: Mapped[str | None] = mapped_column(String(255))
    params_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    output_schema: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

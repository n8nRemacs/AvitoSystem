"""DeviceFeatureBinding — links a device_node to a feature_node with severity."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, String,
    UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeviceFeatureBinding(Base):
    __tablename__ = "device_feature_bindings"
    __table_args__ = (
        UniqueConstraint(
            "device_node_id", "feature_node_id",
            name="uq_dfb_device_feature",
        ),
        CheckConstraint(
            "defect_action IN ('block', 'info')",
            name="ck_dfb_defect_action",
        ),
        CheckConstraint(
            "unknown_action IN ('ask', 'skip')",
            name="ck_dfb_unknown_action",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    device_node_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("device_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_node_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("feature_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    defect_action: Mapped[str] = mapped_column(String(16), nullable=False)
    unknown_action: Mapped[str] = mapped_column(String(16), nullable=False)
    disabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False,
    )

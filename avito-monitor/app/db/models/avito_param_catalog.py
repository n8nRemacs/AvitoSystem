"""Numeric (param_id, value) catalog for Avito mobile-API structured search.

Populated from blob_decoder, subscription deeplinks, manual JSON snapshots, or
the (still-locked) /16/dicts/parameters endpoint. The URL parser looks this
table up to convert a human-readable profile name ("iPhone 12 Pro Max") into
the precise mobile-API ``params[110617][0]=491590`` filter, replacing the
fuzzy text+post-filter shim.

Spec — DOCS/REFERENCE/10-blob-decoder.md and the 0010 migration.
"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AvitoParamCatalog(Base):
    __tablename__ = "avito_param_catalog"
    __table_args__ = (
        UniqueConstraint(
            "category_id",
            "param_id",
            "param_value",
            name="uq_avito_param_catalog_natural",
        ),
        Index(
            "ix_avito_param_catalog_lookup",
            "category_id",
            "param_kind",
            "human_name",
        ),
        Index(
            "ix_avito_param_catalog_parent",
            "category_id",
            "parent_param_id",
            "parent_value",
            postgresql_where="parent_param_id IS NOT NULL",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False)
    param_id: Mapped[int] = mapped_column(Integer, nullable=False)
    param_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    human_name: Mapped[str] = mapped_column(Text, nullable=False)
    param_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_param_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_value: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

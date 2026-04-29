"""autosearch_sync — extend search_profiles + user_listing_blacklist (ADR-011)

Adds Avito autosearch (mobile API "subscriptions") sync support:
  - search_profiles.avito_autosearch_id  (Long filterId from Avito mobile API)
  - search_profiles.import_source        ('manual_url' | 'autosearch_sync')
  - search_profiles.archived_at          (soft-delete when autosearch removed on Avito)
  - search_profiles.last_synced_at       (sync run timestamp)
  - new table user_listing_blacklist     (reject ✗ propagates per-user globally)

Revision ID: 0004_autosearch_sync
Revises: 0003_price_intel
Create Date: 2026-04-28 11:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0004_autosearch_sync"
down_revision: Union[str, None] = "0003_price_intel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "search_profiles",
        sa.Column("avito_autosearch_id", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_search_profiles_avito_autosearch_id",
        "search_profiles",
        ["avito_autosearch_id"],
        unique=True,
        postgresql_where=sa.text("avito_autosearch_id IS NOT NULL"),
    )

    op.add_column(
        "search_profiles",
        sa.Column(
            "import_source",
            sa.String(32),
            nullable=False,
            server_default="manual_url",
        ),
    )
    op.create_check_constraint(
        "ck_search_profiles_import_source",
        "search_profiles",
        "import_source IN ('manual_url', 'autosearch_sync')",
    )

    op.add_column(
        "search_profiles",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_search_profiles_archived_at",
        "search_profiles",
        ["archived_at"],
    )

    op.add_column(
        "search_profiles",
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )

    # search_params: structured filter dict for autosearch-synced profiles
    # (parsed from Avito mobile API ``/2/subscriptions/{id}.result.deepLink``).
    # Manual-URL profiles leave it NULL — they go through the legacy URL
    # parser pipeline.
    op.add_column(
        "search_profiles",
        sa.Column("search_params", postgresql.JSONB, nullable=True),
    )

    op.create_table(
        "user_listing_blacklist",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.String(32), nullable=False, server_default="rejected"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "listing_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "reason IN ('rejected', 'manually_hidden')",
            name="ck_user_listing_blacklist_reason",
        ),
    )
    op.create_index(
        "ix_user_listing_blacklist_user_id",
        "user_listing_blacklist",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_listing_blacklist_user_id", table_name="user_listing_blacklist")
    op.drop_table("user_listing_blacklist")

    op.drop_column("search_profiles", "search_params")
    op.drop_column("search_profiles", "last_synced_at")
    op.drop_index("ix_search_profiles_archived_at", table_name="search_profiles")
    op.drop_column("search_profiles", "archived_at")
    op.drop_constraint("ck_search_profiles_import_source", "search_profiles", type_="check")
    op.drop_column("search_profiles", "import_source")
    op.drop_index("ix_search_profiles_avito_autosearch_id", table_name="search_profiles")
    op.drop_column("search_profiles", "avito_autosearch_id")

"""search_profile_owner_account — owner_account_id FK to Supabase avito_accounts

Adds owner_account_id (UUID) to search_profiles. No real FK constraint:
avito_accounts lives in Supabase (separate DB), cross-DB FK невозможен.
Резолв в коде через AccountPool client.

Used for:
  - autosearch_sync: per-account loop (каждый account pull'ит свои /5/subscriptions)
  - V2 messenger flow: ответы клиенту через того аккаунта, под которым autosearch создан

Revision ID: 0005_owner_account
Revises: 0004_autosearch_sync
Create Date: 2026-04-29 11:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0005_owner_account"
down_revision: Union[str, None] = "0004_autosearch_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "search_profiles",
        sa.Column("owner_account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "idx_search_profiles_owner",
        "search_profiles",
        ["owner_account_id"],
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_search_profiles_owner", table_name="search_profiles")
    op.drop_column("search_profiles", "owner_account_id")

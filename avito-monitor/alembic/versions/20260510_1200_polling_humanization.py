"""polling_humanization — track per-profile last full pagination

Adds ``search_profiles.last_full_poll_at`` so the polling worker can decide
whether the current tick should walk all pages (rare, ≤1/hour per profile)
or only fetch page=1 (the common case). Combined with random session
breaks and active-hours guard, this lets the bot mimic a real buyer
scrolling Avito instead of the previous always-full-paginate behaviour.

Revision ID: 0011_polling_humanization
Revises: 0010_avito_param_catalog
Create Date: 2026-05-10 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0011_polling_humanization"
down_revision: Union[str, None] = "0010_avito_param_catalog"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "search_profiles",
        sa.Column(
            "last_full_poll_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("search_profiles", "last_full_poll_at")

"""v2_relax_blacklist_reason — allow auto_red:* reasons + widen column

The V2 evaluator writes ``auto_red:<criterion_key>`` into
``user_listing_blacklist.reason`` so future polls skip the listing
across every profile of the same user (ADR-011 reuse). The original
CHECK constraint only allowed ``rejected`` / ``manually_hidden`` and
the column was VARCHAR(32) — both too tight for the new pattern.

Widens the column to VARCHAR(96) and replaces the CHECK with a
prefix-match expression that admits both legacy values and any
``auto_red:<key>`` string the criteria library may emit.

Revision ID: 0008_v2_relax_blacklist_reason
Revises: 0007_v2_seed_criteria_library
Create Date: 2026-05-05 11:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0008_v2_relax_blacklist_reason"
down_revision: Union[str, None] = "0007_v2_seed_criteria_library"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Both names use raw SQL (op.execute) to bypass SQLAlchemy's
# NAMING_CONVENTION truncation, which would otherwise emit a hashed
# name that doesn't match the existing constraint.
_OLD_CHECK = "ck_user_listing_blacklist_ck_user_listing_blacklist_reason"
_NEW_CHECK = "ck_user_listing_blacklist_reason"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE user_listing_blacklist "
        "ALTER COLUMN reason TYPE VARCHAR(96)"
    )
    op.execute(
        f"ALTER TABLE user_listing_blacklist DROP CONSTRAINT IF EXISTS {_OLD_CHECK}"
    )
    op.execute(
        f"ALTER TABLE user_listing_blacklist ADD CONSTRAINT {_NEW_CHECK} "
        "CHECK (reason IN ('rejected', 'manually_hidden') OR reason LIKE 'auto_red:%')"
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE user_listing_blacklist DROP CONSTRAINT IF EXISTS {_NEW_CHECK}"
    )
    op.execute(
        "DELETE FROM user_listing_blacklist "
        "WHERE reason NOT IN ('rejected', 'manually_hidden')"
    )
    op.execute(
        f"ALTER TABLE user_listing_blacklist ADD CONSTRAINT {_OLD_CHECK} "
        "CHECK (reason::text = ANY (ARRAY['rejected', 'manually_hidden']::text[]))"
    )
    op.execute(
        "ALTER TABLE user_listing_blacklist "
        "ALTER COLUMN reason TYPE VARCHAR(32)"
    )

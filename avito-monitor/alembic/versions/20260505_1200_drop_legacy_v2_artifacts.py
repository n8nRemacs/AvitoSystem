"""drop_legacy_v2_artifacts — Phase C destructive cleanup

Drops ADR-010 legacy columns and artefacts that are no longer used
after Phase B soak. All profiles must be running on V2 evaluate_listing
before applying this migration.

DO NOT APPLY until at least one live profile has run V2 for 3-4 days
without false positives. Apply via: ``alembic upgrade head``

Revision ID: 0009_drop_legacy_v2_artifacts
Revises: 0008_v2_relax_blacklist_reason
Create Date: 2026-05-05 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0009_drop_legacy_v2_artifacts"
down_revision: Union[str, None] = "0008_v2_relax_blacklist_reason"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# FK constraint names as created by 0002_search_profiles (no explicit name
# was given, so SQLAlchemy's NAMING_CONVENTION generated them). We use raw
# SQL to drop them to avoid NAMING_CONVENTION truncation mismatches.
_FK_CONDITION_CLASSIFICATION = (
    "fk_profile_listings_condition_classification_id_llm_analyses"
)
_FK_MATCH_RESULT = "fk_profile_listings_match_result_id_llm_analyses"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Data migration: normalise processing_status values that no longer
    # exist in V2 → collapse all legacy intermediate states to 'evaluated'
    # so the dashboard filter works correctly.
    # ------------------------------------------------------------------
    op.execute(
        """
        UPDATE profile_listings
        SET processing_status = 'evaluated'
        WHERE processing_status IN ('classified', 'market_data', 'pending_match')
        """
    )

    # ------------------------------------------------------------------
    # Purge legacy LLM cache rows.  V2 uses 'criterion_eval' and
    # 'info_llm_extract'; 'condition' and 'match' entries are orphaned
    # and should not contribute to budget totals going forward.
    # ------------------------------------------------------------------
    op.execute(
        "DELETE FROM llm_analyses WHERE type IN ('condition', 'match')"
    )

    # ------------------------------------------------------------------
    # profile_listings: drop FKs first (raw SQL avoids NAMING_CONVENTION
    # truncation), then drop the columns.
    # ------------------------------------------------------------------
    op.execute(
        f"ALTER TABLE profile_listings "
        f"DROP CONSTRAINT IF EXISTS {_FK_CONDITION_CLASSIFICATION}"
    )
    op.execute(
        f"ALTER TABLE profile_listings "
        f"DROP CONSTRAINT IF EXISTS {_FK_MATCH_RESULT}"
    )
    op.drop_column("profile_listings", "condition_classification_id")
    op.drop_column("profile_listings", "match_result_id")

    # ------------------------------------------------------------------
    # search_profiles: drop legacy ADR-010 columns.
    # listings.condition_class is intentionally KEPT — _derive_condition_class
    # still writes it from V2 criteria flags for dashboard compatibility.
    # ------------------------------------------------------------------
    op.drop_column("search_profiles", "custom_criteria")
    op.drop_column("search_profiles", "allowed_conditions")
    op.drop_column("search_profiles", "llm_classify_model")
    op.drop_column("search_profiles", "llm_match_model")
    op.drop_column("search_profiles", "analyze_photos")


def downgrade() -> None:
    # Best-effort: re-add columns with defaults. The FK constraints and the
    # deleted llm_analyses rows are NOT restored (data is gone).

    # search_profiles
    op.add_column(
        "search_profiles",
        sa.Column(
            "analyze_photos",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "search_profiles",
        sa.Column("llm_match_model", sa.String(128)),
    )
    op.add_column(
        "search_profiles",
        sa.Column("llm_classify_model", sa.String(128)),
    )
    op.add_column(
        "search_profiles",
        sa.Column(
            "allowed_conditions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[\"working\"]'::jsonb"),
        ),
    )
    op.add_column(
        "search_profiles",
        sa.Column("custom_criteria", sa.Text()),
    )

    # profile_listings
    op.add_column(
        "profile_listings",
        sa.Column(
            "match_result_id",
            postgresql.UUID(as_uuid=True),
        ),
    )
    op.add_column(
        "profile_listings",
        sa.Column(
            "condition_classification_id",
            postgresql.UUID(as_uuid=True),
        ),
    )

    # processing_status: leave 'evaluated' rows as-is — reverting to
    # 'classified'/'pending_match'/'market_data' without the original data
    # would be incorrect.

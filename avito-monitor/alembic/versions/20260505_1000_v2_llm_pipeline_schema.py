"""v2_llm_pipeline_schema — flag-based evaluation tables (non-destructive)

Adds three new tables and extra columns on search_profiles + profile_listings
to support the V2 LLM pipeline (criteria-flag → green/grey/red bucket).
Legacy ADR-010 columns (custom_criteria, allowed_conditions) are KEPT as
read-only fallback through Phase B–C; a separate destructive migration
drops them in Phase C once all profiles have migrated.

Revision ID: 0006_v2_llm_pipeline
Revises: 0005_owner_account
Create Date: 2026-05-05 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0006_v2_llm_pipeline"
down_revision: Union[str, None] = "0005_owner_account"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ----- criteria_templates (global library) ------------------------
    op.create_table(
        "criteria_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("title_ru", sa.String(255), nullable=False),
        sa.Column("description_ru", sa.Text()),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("prompt_fragment", sa.Text()),
        sa.Column("api_path", sa.String(255)),
        sa.Column("params_schema", postgresql.JSONB()),
        sa.Column("output_schema", postgresql.JSONB()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("key", name="uq_criteria_templates_key"),
    )

    # ----- profile_criteria (per-profile selection + custom) ----------
    op.create_table(
        "profile_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("search_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("criteria_templates.id", ondelete="RESTRICT"),
        ),
        sa.Column("custom_key", sa.String(64)),
        sa.Column("custom_title_ru", sa.String(255)),
        sa.Column("custom_kind", sa.String(16)),
        sa.Column("custom_prompt_fragment", sa.Text()),
        sa.Column("params", postgresql.JSONB()),
        sa.Column(
            "is_hard", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "sort_order", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_profile_criteria_profile", "profile_criteria", ["profile_id"]
    )

    # ----- profile_listing_evaluations (per-profile bucket verdict) ---
    op.create_table(
        "profile_listing_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("search_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bucket", sa.String(8), nullable=False),
        sa.Column(
            "confidence_threshold",
            sa.Numeric(4, 3),
            nullable=False,
            server_default="0.7",
        ),
        sa.Column(
            "criteria_flags",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "info_fields",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "red_criterion_keys",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("criteria_set_hash", sa.String(64), nullable=False),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_profile_listing_evaluations_profile_listing",
        "profile_listing_evaluations",
        ["profile_id", "listing_id"],
    )
    op.create_index(
        "ix_profile_listing_evaluations_profile_bucket",
        "profile_listing_evaluations",
        ["profile_id", "bucket"],
    )

    # ----- search_profiles new columns --------------------------------
    op.add_column(
        "search_profiles",
        sa.Column(
            "evaluate_strategy",
            sa.String(16),
            nullable=False,
            server_default="per_listing",
        ),
    )
    op.add_column(
        "search_profiles",
        sa.Column(
            "confidence_threshold",
            sa.Numeric(4, 3),
            nullable=False,
            server_default="0.7",
        ),
    )
    op.add_column(
        "search_profiles",
        sa.Column("criteria_set_hash", sa.String(64)),
    )
    op.add_column(
        "search_profiles",
        sa.Column("bucket_routing", postgresql.JSONB()),
    )

    # ----- profile_listings new columns -------------------------------
    op.add_column(
        "profile_listings", sa.Column("bucket", sa.String(8))
    )
    op.add_column(
        "profile_listings",
        sa.Column(
            "latest_evaluation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "profile_listing_evaluations.id", ondelete="SET NULL"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("profile_listings", "latest_evaluation_id")
    op.drop_column("profile_listings", "bucket")

    op.drop_column("search_profiles", "bucket_routing")
    op.drop_column("search_profiles", "criteria_set_hash")
    op.drop_column("search_profiles", "confidence_threshold")
    op.drop_column("search_profiles", "evaluate_strategy")

    op.drop_index(
        "ix_profile_listing_evaluations_profile_bucket",
        table_name="profile_listing_evaluations",
    )
    op.drop_index(
        "ix_profile_listing_evaluations_profile_listing",
        table_name="profile_listing_evaluations",
    )
    op.drop_table("profile_listing_evaluations")

    op.drop_index("ix_profile_criteria_profile", table_name="profile_criteria")
    op.drop_table("profile_criteria")

    op.drop_constraint(
        "uq_criteria_templates_key", "criteria_templates", type_="unique"
    )
    op.drop_table("criteria_templates")

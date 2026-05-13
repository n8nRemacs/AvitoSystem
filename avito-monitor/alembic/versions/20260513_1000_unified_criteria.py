"""unified_criteria — extend listing_features kind/value + drop V2 tables

Revision ID: 0016_unified_criteria
Revises: 0015_defect_checklist
Create Date: 2026-05-13 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0016_unified_criteria"
down_revision: Union[str, None] = "0015_defect_checklist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Extend listing_features — add kind + value columns
    op.add_column(
        "listing_features",
        sa.Column(
            "kind",
            sa.String(length=32),
            nullable=False,
            server_default="defect",
        ),
    )
    op.add_column(
        "listing_features",
        sa.Column("value", postgresql.JSONB(), nullable=True),
    )
    # state was NOT NULL — relax to allow NULL for non-defect kinds
    op.alter_column("listing_features", "state", nullable=True)

    # 2) CHECK constraint: defect rows must have state; non-defect may omit state
    op.create_check_constraint(
        "lf_kind_shape_chk",
        "listing_features",
        "(kind = 'defect' AND state IS NOT NULL) OR "
        "(kind IN ('price_signal', 'info_api'))",
    )

    # 3) Drop V2-related FK columns on profile_listings (if still present —
    #    0009_drop_legacy_v2_artifacts may have already removed them).
    bind = op.get_bind()
    pl_cols = {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'profile_listings'"
            )
        )
    }
    for col in ("match_result_id", "condition_classification_id"):
        if col in pl_cols:
            op.drop_column("profile_listings", col)

    # 4) Drop V2 tables in child-first FK order.
    #    Guard with IF EXISTS in case 0009 / future migrations already removed them.
    existing_tables = {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        )
    }
    for tbl in (
        "profile_listing_evaluations",
        "llm_analyses",
        "profile_criteria",
        "criteria_templates",
    ):
        if tbl in existing_tables:
            op.drop_table(tbl)


def downgrade() -> None:
    """Reverse: re-create V2 tables (EMPTY) + drop kind/value, restore state NOT NULL.

    NOTE: V2 data is UNRECOVERABLE via downgrade alone. Production rollback
    requires pg_restore from a pre-migration pg_dump (per spec §9 mitigation).

    Tables are re-created with their original schemas from:
    - criteria_templates, profile_criteria, profile_listing_evaluations →
        0006_v2_llm_pipeline (20260505_1000_v2_llm_pipeline_schema.py)
    - llm_analyses → 0002_search_profiles (20260425_1300_search_profiles_and_co.py)
    """

    # 1) Re-create V2 tables in dependency order (parents first).

    # criteria_templates — global criteria library (0006_v2_llm_pipeline)
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
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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

    # llm_analyses — LLM cache (0002_search_profiles)
    op.create_table(
        "llm_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True)),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True)),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(32)),
        sa.Column("cache_key", sa.String(128), nullable=False),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("result", postgresql.JSONB(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_analyses")),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            ondelete="CASCADE",
            name=op.f("fk_llm_analyses_listing_id_listings"),
        ),
    )
    op.create_index("ix_llm_analyses_cache_key", "llm_analyses", ["cache_key"])
    op.create_index(
        "ix_llm_analyses_listing_type", "llm_analyses", ["listing_id", "type"]
    )

    # profile_criteria — per-profile criterion selection (0006_v2_llm_pipeline)
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
        sa.Column("is_hard", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
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

    # profile_listing_evaluations — per-profile bucket verdict (0006_v2_llm_pipeline)
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

    # 2) profile_listings FK columns (match_result_id / condition_classification_id)
    #    were dropped in 0009_drop_legacy_v2_artifacts before this migration.
    #    We do NOT re-add them here — restoring them without the FK target rows
    #    would leave orphaned UUID columns with no referential meaning. The
    #    0009 downgrade handles that level of rollback if needed.

    # 3) Reverse listing_features changes
    op.drop_constraint("lf_kind_shape_chk", "listing_features", type_="check")
    op.drop_column("listing_features", "value")
    op.drop_column("listing_features", "kind")
    # Restore state NOT NULL — will fail if any non-defect rows exist with NULL
    # state. Clean those up manually before downgrading in practice.
    op.alter_column("listing_features", "state", nullable=False)

"""price_intelligence — price_analyses + price_analysis_runs (Block 7)

Revision ID: 0003_price_intel
Revises: 09484d8d5eb7
Create Date: 2026-04-27 15:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_price_intel"
down_revision: Union[str, None] = "09484d8d5eb7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ts_columns():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    # price_analyses ----------------------------------------------------
    op.create_table(
        "price_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("reference_listing_url", sa.Text),
        sa.Column("reference_data", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("search_region", sa.String(64)),
        sa.Column("search_radius_km", sa.Integer),
        sa.Column("competitor_filters", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("max_competitors", sa.Integer, nullable=False,
                  server_default="30"),
        sa.Column("llm_model", sa.String(128)),
        sa.Column("schedule", sa.Text),
        *_ts_columns(),

        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_analyses")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_price_analyses_user_id", "price_analyses", ["user_id"])

    # price_analysis_runs -----------------------------------------------
    op.create_table(
        "price_analysis_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="running"),
        sa.Column("report", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("competitor_data", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("competitors_found", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("comparable_count", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("error_message", sa.Text),
        *_ts_columns(),

        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_analysis_runs")),
        sa.ForeignKeyConstraint(["analysis_id"], ["price_analyses.id"],
                                ondelete="CASCADE"),
    )
    op.create_index(
        "ix_price_analysis_runs_analysis_started",
        "price_analysis_runs",
        ["analysis_id", "started_at"],
    )


def downgrade() -> None:
    op.drop_table("price_analysis_runs")
    op.drop_table("price_analyses")

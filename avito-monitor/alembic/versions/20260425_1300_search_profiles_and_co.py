"""search_profiles + listings + co (Block 2)

Revision ID: 0002_search_profiles
Revises: 0001_initial
Create Date: 2026-04-25 13:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_search_profiles"
down_revision: Union[str, None] = "0001_initial"
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
    # search_profiles ----------------------------------------------------
    op.create_table(
        "search_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("avito_search_url", sa.Text, nullable=False),

        sa.Column("parsed_brand", sa.String(128)),
        sa.Column("parsed_model", sa.String(255)),
        sa.Column("parsed_category", sa.String(255)),

        sa.Column("region_slug", sa.String(64)),
        sa.Column("only_with_delivery", sa.Boolean),
        sa.Column("sort", sa.Integer),

        sa.Column("search_min_price", sa.Integer),
        sa.Column("search_max_price", sa.Integer),
        sa.Column("alert_min_price", sa.Integer),
        sa.Column("alert_max_price", sa.Integer),

        sa.Column("custom_criteria", sa.Text),
        sa.Column("allowed_conditions", postgresql.JSONB,
                  nullable=False, server_default=sa.text("'[\"working\"]'::jsonb")),
        sa.Column("llm_classify_model", sa.String(128)),
        sa.Column("llm_match_model", sa.String(128)),
        sa.Column("analyze_photos", sa.Boolean, nullable=False, server_default=sa.false()),

        sa.Column("poll_interval_minutes", sa.Integer, nullable=False, server_default="15"),
        sa.Column("active_hours", postgresql.JSONB),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),

        sa.Column("blocked_sellers", postgresql.JSONB,
                  nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("notification_settings", postgresql.JSONB,
                  nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("notification_channels", postgresql.JSONB,
                  nullable=False, server_default=sa.text("'[\"telegram\"]'::jsonb")),
        *_ts_columns(),

        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_profiles")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name=op.f("fk_search_profiles_user_id_users"),
        ),
    )
    op.create_index("ix_search_profiles_user_id", "search_profiles", ["user_id"])
    op.create_index("ix_search_profiles_is_active", "search_profiles", ["is_active"])

    # listings -----------------------------------------------------------
    op.create_table(
        "listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("avito_id", sa.BigInteger, nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("price", sa.Numeric(12, 2)),
        sa.Column("initial_price", sa.Numeric(12, 2)),
        sa.Column("last_price_change_at", sa.DateTime(timezone=True)),
        sa.Column("currency", sa.String(8), nullable=False, server_default="RUB"),
        sa.Column("region", sa.String(128)),
        sa.Column("url", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("images", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("parameters", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("seller_id", sa.String(64)),
        sa.Column("seller_type", sa.String(16), server_default="private"),
        sa.Column("seller_info", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("condition_class", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("condition_confidence", sa.Float),
        sa.Column("condition_reasoning", sa.Text),
        sa.Column("avito_created_at", sa.DateTime(timezone=True)),
        sa.Column("avito_updated_at", sa.DateTime(timezone=True)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("raw_data", postgresql.JSONB),
        *_ts_columns(),

        sa.PrimaryKeyConstraint("id", name=op.f("pk_listings")),
        sa.UniqueConstraint("avito_id", name=op.f("uq_listings_avito_id")),
    )
    op.create_index("ix_listings_avito_id", "listings", ["avito_id"])
    op.create_index("ix_listings_status_first_seen", "listings", ["status", "first_seen_at"])
    op.create_index("ix_listings_condition_class", "listings", ["condition_class"])

    # llm_analyses (created before profile_listings because referenced) -
    op.create_table(
        "llm_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True)),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True)),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("prompt_version", sa.String(32)),
        sa.Column("cache_key", sa.String(128), nullable=False),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("result", postgresql.JSONB, nullable=False),
        *_ts_columns(),

        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_analyses")),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], ondelete="CASCADE",
            name=op.f("fk_llm_analyses_listing_id_listings"),
        ),
    )
    op.create_index("ix_llm_analyses_cache_key", "llm_analyses", ["cache_key"])
    op.create_index("ix_llm_analyses_listing_type", "llm_analyses", ["listing_id", "type"])

    # profile_listings ---------------------------------------------------
    op.create_table(
        "profile_listings",
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("processing_status", sa.String(32), nullable=False, server_default="fetched"),
        sa.Column("in_alert_zone", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("condition_classification_id", postgresql.UUID(as_uuid=True)),
        sa.Column("match_result_id", postgresql.UUID(as_uuid=True)),
        sa.Column("user_action", sa.String(16), server_default="pending"),

        sa.PrimaryKeyConstraint("profile_id", "listing_id", name=op.f("pk_profile_listings")),
        sa.ForeignKeyConstraint(["profile_id"], ["search_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["condition_classification_id"], ["llm_analyses.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["match_result_id"], ["llm_analyses.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_profile_listings_profile_discovered", "profile_listings",
                    ["profile_id", "discovered_at"])
    op.create_index("ix_profile_listings_profile_status", "profile_listings",
                    ["profile_id", "processing_status"])
    op.create_index("ix_profile_listings_profile_alert", "profile_listings",
                    ["profile_id", "in_alert_zone"])

    # profile_runs -------------------------------------------------------
    op.create_table(
        "profile_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("listings_seen", sa.Integer, nullable=False, server_default="0"),
        sa.Column("listings_new", sa.Integer, nullable=False, server_default="0"),
        sa.Column("listings_in_alert", sa.Integer, nullable=False, server_default="0"),
        sa.Column("listings_classified", sa.Integer, nullable=False, server_default="0"),
        sa.Column("notifications_sent", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 6)),
        sa.Column("error_message", sa.Text),
        sa.Column("metrics", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_ts_columns(),

        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_runs")),
        sa.ForeignKeyConstraint(["profile_id"], ["search_profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_profile_runs_profile_id", "profile_runs", ["profile_id"])
    op.create_index("ix_profile_runs_profile_started", "profile_runs",
                    ["profile_id", "started_at"])

    # notifications ------------------------------------------------------
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True)),
        sa.Column("related_listing_id", postgresql.UUID(as_uuid=True)),
        sa.Column("type", sa.String(48), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False, server_default="telegram"),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        *_ts_columns(),

        sa.PrimaryKeyConstraint("id", name=op.f("pk_notifications")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["search_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_listing_id"], ["listings.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_status_retry", "notifications", ["status", "retry_count"])

    # profile_market_stats -----------------------------------------------
    op.create_table(
        "profile_market_stats",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("granularity", sa.String(8), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("listings_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("new_listings_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("disappeared_listings_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_listing_lifetime_hours", sa.Numeric(10, 2)),
        sa.Column("price_median_raw", sa.Numeric(12, 2)),
        sa.Column("price_median_clean", sa.Numeric(12, 2)),
        sa.Column("price_mean", sa.Numeric(12, 2)),
        sa.Column("price_min", sa.Numeric(12, 2)),
        sa.Column("price_max", sa.Numeric(12, 2)),
        sa.Column("price_p25_clean", sa.Numeric(12, 2)),
        sa.Column("price_p75_clean", sa.Numeric(12, 2)),
        sa.Column("working_share", sa.Numeric(5, 4)),
        sa.Column("condition_distribution", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        *_ts_columns(),

        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_market_stats")),
        sa.ForeignKeyConstraint(["profile_id"], ["search_profiles.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("profile_id", "granularity", "period_start",
                            name="uq_profile_market_stats_period"),
    )
    op.create_index("ix_profile_market_stats_profile_id", "profile_market_stats", ["profile_id"])

    # audit_log ----------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64)),
        sa.Column("entity_id", sa.String(128)),
        sa.Column("details", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        *_ts_columns(),

        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("profile_market_stats")
    op.drop_table("notifications")
    op.drop_table("profile_runs")
    op.drop_table("profile_listings")
    op.drop_table("llm_analyses")
    op.drop_table("listings")
    op.drop_table("search_profiles")

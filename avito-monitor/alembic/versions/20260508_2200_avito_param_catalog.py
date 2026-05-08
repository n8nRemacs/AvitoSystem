"""avito_param_catalog — structured search parameter catalog

Stores numeric (param_id, value) pairs that the Avito mobile API expects in
``params[<param_id>][0]=<value>``. Populated from three sources:

  - blob_decoder      — decoded f=AS... blob in a web URL
  - subscription_deeplink — pulled from /2/subscriptions/{id}.deepLink
  - manual_json       — initial seed from DOCS/avito_api_snapshots/*.json
  - dicts_endpoint    — /16/dicts/parameters (when we crack POST body, future)

URL parser will look this up to convert "iPhone 12 Pro Max" in a profile into
the precise mobile-API request, replacing the current fuzzy text+post-filter.

Revision ID: 0010_avito_param_catalog
Revises: 0009_drop_legacy_v2_artifacts
Create Date: 2026-05-08 22:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0010_avito_param_catalog"
down_revision: Union[str, None] = "0009_drop_legacy_v2_artifacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "avito_param_catalog",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        # Avito mobile API category id (84 for phones; web uses 87 — kept
        # separately under the same row so both APIs can look up by mobile id).
        sa.Column("category_id", sa.Integer, nullable=False),
        # Numeric param id from Avito (110617=model, 110618=brand, 110680=type
        # for phones — see DOCS/REFERENCE/10-blob-decoder.md).
        sa.Column("param_id", sa.Integer, nullable=False),
        # Numeric value (e.g. 491590 = iPhone 12 Pro Max).
        sa.Column("param_value", sa.BigInteger, nullable=False),
        # Human-readable name as Avito shows it ("iPhone 12 Pro Max", "Apple").
        sa.Column("human_name", sa.Text, nullable=False),
        # 'brand' | 'model' | 'type' | 'memory' | 'color' | 'condition' | etc.
        sa.Column("param_kind", sa.String(32), nullable=False),
        # Hierarchical link: model belongs to brand. Brand rows leave both NULL.
        sa.Column("parent_param_id", sa.Integer, nullable=True),
        sa.Column("parent_value", sa.BigInteger, nullable=True),
        # Where this row came from. Drives trust ranking when the same
        # (category, param_id, value) shows up via multiple paths.
        sa.Column("source", sa.String(32), nullable=False),
        # Free-form provenance — original blob, deeplink, subscription_id,
        # source JSON path, etc.
        sa.Column("source_ref", sa.Text, nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "category_id",
            "param_id",
            "param_value",
            name="uq_avito_param_catalog_natural",
        ),
        sa.CheckConstraint(
            "param_kind IN ('brand','model','type','memory','color',"
            "'condition','seller','delivery','other')",
            name="ck_avito_param_catalog_kind",
        ),
        sa.CheckConstraint(
            "source IN ('manual_json','blob_decoder','subscription_deeplink',"
            "'dicts_endpoint')",
            name="ck_avito_param_catalog_source",
        ),
    )

    # Lookup path used by the URL parser: given category + kind + name,
    # find the numeric value to inject into mobile API.
    op.create_index(
        "ix_avito_param_catalog_lookup",
        "avito_param_catalog",
        ["category_id", "param_kind", "human_name"],
    )

    # Parent-link traversal (find all models of a brand).
    op.create_index(
        "ix_avito_param_catalog_parent",
        "avito_param_catalog",
        ["category_id", "parent_param_id", "parent_value"],
        postgresql_where=sa.text("parent_param_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_avito_param_catalog_parent", table_name="avito_param_catalog"
    )
    op.drop_index(
        "ix_avito_param_catalog_lookup", table_name="avito_param_catalog"
    )
    op.drop_table("avito_param_catalog")

"""defect_catalog — feature_nodes + device_nodes + device_feature_bindings

Revision ID: 0017_defect_catalog
Revises: 0016_unified_criteria
Create Date: 2026-05-14 10:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0017_defect_catalog"
down_revision = "0016_unified_criteria"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feature_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("parent_id", UUID(as_uuid=True),
                  sa.ForeignKey("feature_nodes.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_hint", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("parent_id", "slug", name="uq_feature_nodes_parent_slug"),
        sa.CheckConstraint("kind IN ('node', 'defect')", name="ck_feature_nodes_kind"),
    )
    op.create_index("idx_feature_nodes_parent", "feature_nodes", ["parent_id"])

    op.create_table(
        "device_nodes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("parent_id", UUID(as_uuid=True),
                  sa.ForeignKey("device_nodes.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("parent_id", "slug", name="uq_device_nodes_parent_slug"),
    )
    op.create_index("idx_device_nodes_parent", "device_nodes", ["parent_id"])

    op.create_table(
        "device_feature_bindings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("device_node_id", UUID(as_uuid=True),
                  sa.ForeignKey("device_nodes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("feature_node_id", UUID(as_uuid=True),
                  sa.ForeignKey("feature_nodes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("defect_action", sa.String(16), nullable=False),
        sa.Column("unknown_action", sa.String(16), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("device_node_id", "feature_node_id", name="uq_dfb_device_feature"),
        sa.CheckConstraint("defect_action IN ('block', 'info')", name="ck_dfb_defect_action"),
        sa.CheckConstraint("unknown_action IN ('ask', 'skip')", name="ck_dfb_unknown_action"),
    )
    op.create_index("idx_dfb_device", "device_feature_bindings", ["device_node_id"])
    op.create_index("idx_dfb_feature", "device_feature_bindings", ["feature_node_id"])


def downgrade() -> None:
    op.drop_index("idx_dfb_feature", table_name="device_feature_bindings")
    op.drop_index("idx_dfb_device", table_name="device_feature_bindings")
    op.drop_table("device_feature_bindings")
    op.drop_index("idx_device_nodes_parent", table_name="device_nodes")
    op.drop_table("device_nodes")
    op.drop_index("idx_feature_nodes_parent", table_name="feature_nodes")
    op.drop_table("feature_nodes")

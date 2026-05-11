"""phase_b_topics — dialog topic library + per-dialog topic state + recap.

Revision ID: 0014_phase_b_topics
Revises: 0013_seller_dialogs
Create Date: 2026-05-11 20:00:00
"""
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
import yaml
from alembic import op


revision: str = "0014_phase_b_topics"
down_revision: Union[str, None] = "0013_seller_dialogs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dialog_topics",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("category", sa.String(32), nullable=True),
        sa.Column("default_phrasing", sa.Text, nullable=True),
        sa.Column("expected_format", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(32), nullable=False, server_default="system_seed"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
    )
    op.create_table(
        "profile_dialog_topics",
        sa.Column("profile_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("search_profiles.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("topic_key", sa.String(64),
                  sa.ForeignKey("dialog_topics.key", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("profile_id", "topic_key",
                                name="pk_profile_dialog_topics"),
    )
    op.create_table(
        "seller_dialog_topics",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("dialog_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("seller_dialogs.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("topic_key", sa.String(64),
                  sa.ForeignKey("dialog_topics.key"), nullable=True),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("question_text", sa.Text, nullable=True),
        sa.Column("question_msg_id", sa.Text,
                  sa.ForeignKey("messenger_messages.id"), nullable=True),
        sa.Column("answer_text", sa.Text, nullable=True),
        sa.Column("answer_msg_id", sa.Text,
                  sa.ForeignKey("messenger_messages.id"), nullable=True),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.CheckConstraint(
            "status IN ('pending','asked','answered','skipped')",
            name="ck_seller_dialog_topics_status",
        ),
    )
    op.create_index("ix_seller_dialog_topics_dialog", "seller_dialog_topics", ["dialog_id"])
    op.create_index("ix_seller_dialog_topics_status", "seller_dialog_topics", ["status"])

    op.add_column("seller_dialogs", sa.Column("recap_text", sa.Text, nullable=True))
    op.add_column("seller_dialogs", sa.Column("recap_msg_id", sa.Text,
                  sa.ForeignKey("messenger_messages.id"), nullable=True))
    op.add_column("seller_dialogs", sa.Column("recap_status", sa.String(16), nullable=True))

    # Data migration: upsert seed YAML into dialog_topics + auto-link to existing profile.
    seed_path = Path(__file__).resolve().parents[2] / "app" / "data" / "dialog_topics.yaml"
    with seed_path.open(encoding="utf-8") as f:
        topics = yaml.safe_load(f)
    bind = op.get_bind()
    for t in topics:
        bind.execute(sa.text(
            "INSERT INTO dialog_topics (key, title, category, default_phrasing, "
            "expected_format, created_by) "
            "VALUES (:key, :title, :category, :default_phrasing, :expected_format, 'system_seed') "
            "ON CONFLICT (key) DO UPDATE SET title = EXCLUDED.title, "
            "category = EXCLUDED.category, default_phrasing = EXCLUDED.default_phrasing, "
            "expected_format = EXCLUDED.expected_format"
        ), t)
    bind.execute(sa.text(
        "INSERT INTO profile_dialog_topics (profile_id, topic_key) "
        "SELECT p.id, t.key FROM search_profiles p CROSS JOIN dialog_topics t "
        "ON CONFLICT DO NOTHING"
    ))


def downgrade() -> None:
    op.drop_column("seller_dialogs", "recap_status")
    op.drop_column("seller_dialogs", "recap_msg_id")
    op.drop_column("seller_dialogs", "recap_text")
    op.drop_index("ix_seller_dialog_topics_status", table_name="seller_dialog_topics")
    op.drop_index("ix_seller_dialog_topics_dialog", table_name="seller_dialog_topics")
    op.drop_table("seller_dialog_topics")
    op.drop_table("profile_dialog_topics")
    op.drop_table("dialog_topics")

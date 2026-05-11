"""seller_dialogs — seller-side conversation state machine (Phase A subset)

Phase A creates a minimal schema for the seller dialog workflow:
  - ``seller_dialogs`` — one row per (profile, listing) pair tracking the
    current pipeline stage (``contact``, ``questions_setup`` in Phase A;
    later phases add ``questions``, ``price_negotiation``, etc.).
  - ``messenger_messages.dialog_id`` — nullable FK so the existing chat-log
    table can carry both reliability-bot messages (NULL) and seller-dialog
    messages without splitting tables.

Phase A intentionally omits ``silence_deadline``, ``timeout_notified``,
``prolongation_count``, ``target_price``, ``final_price``,
``shipping_method``, ``return_reason``, ``extracted_data`` — those land
in later phases when the corresponding stages are implemented.

Revision ID: 0013_seller_dialogs
Revises: 0012_reservation_tracking
Create Date: 2026-05-11 10:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0013_seller_dialogs"
down_revision: Union[str, None] = "0012_reservation_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "seller_dialogs",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "profile_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "listing_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel_id", sa.Text, nullable=True),
        sa.Column("stage", sa.String(24), nullable=False),
        sa.Column(
            "operator_mode",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_reason", sa.String(32), nullable=True),
        sa.ForeignKeyConstraint(
            ["profile_id", "listing_id"],
            ["profile_listings.profile_id", "profile_listings.listing_id"],
            ondelete="CASCADE",
            name="fk_seller_dialogs_profile_listing",
        ),
        sa.UniqueConstraint(
            "profile_id", "listing_id",
            name="uq_seller_dialogs_profile_listing",
        ),
        sa.CheckConstraint(
            "stage IN ('contact','questions_setup','questions','price_negotiation',"
            "'price_changed','purchased','shipped','received','closed','rejected')",
            name="ck_seller_dialogs_stage",
        ),
    )
    op.create_index(
        "ix_seller_dialogs_channel_id",
        "seller_dialogs",
        ["channel_id"],
        unique=False,
    )
    op.create_index(
        "ix_seller_dialogs_stage",
        "seller_dialogs",
        ["stage"],
    )

    op.add_column(
        "messenger_messages",
        sa.Column(
            "dialog_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("seller_dialogs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_messenger_messages_dialog_id",
        "messenger_messages",
        ["dialog_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_messenger_messages_dialog_id", table_name="messenger_messages")
    op.drop_column("messenger_messages", "dialog_id")
    op.drop_index("ix_seller_dialogs_stage", table_name="seller_dialogs")
    op.drop_index("ix_seller_dialogs_channel_id", table_name="seller_dialogs")
    op.drop_table("seller_dialogs")

"""reservation_tracking — listing reservation state + status-change event log

Adds reservation tracking so we can capture the moment a listing flips
``active → reserved`` (the closest signal we get to a real deal happening) and
the price the seller had at that instant. Avito buyers haggle aggressively,
so the *reserved-at price* is materially different from — and far more useful
than — the listing price for market intelligence.

New columns on ``listings``:
  - ``reservation_status`` — active | reserved | sold | unknown (default 'active')
  - ``reservation_changed_at`` — when reservation_status last flipped
  - ``reserved_at_price`` — list price at the moment status flipped to reserved

New table ``listing_status_events``:
  Free-form append-only audit log of price + status transitions. ``event_type``
  is one of ``status_change | price_change | reservation_capture``. Old/new
  values are stored as TEXT (decimal strings for prices, enum strings for
  statuses) so the same table covers both kinds of transitions without a
  polymorphic schema.

Revision ID: 0012_reservation_tracking
Revises: 0011_polling_humanization
Create Date: 2026-05-10 13:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0012_reservation_tracking"
down_revision: Union[str, None] = "0011_polling_humanization"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- listings: reservation columns ----------------------------------
    op.add_column(
        "listings",
        sa.Column(
            "reservation_status",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
    )
    op.add_column(
        "listings",
        sa.Column(
            "reservation_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "listings",
        sa.Column(
            "reserved_at_price",
            sa.Numeric(12, 2),
            nullable=True,
        ),
    )

    # --- listing_status_events ------------------------------------------
    op.create_table(
        "listing_status_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "listing_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(16), nullable=False),
        sa.Column("old_value", sa.Text, nullable=True),
        sa.Column("new_value", sa.Text, nullable=True),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('status_change','price_change','reservation_capture')",
            name="ck_listing_status_events_type",
        ),
    )
    op.create_index(
        "ix_listing_status_events_listing_at",
        "listing_status_events",
        ["listing_id", sa.text("at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_listing_status_events_listing_at",
        table_name="listing_status_events",
    )
    op.drop_table("listing_status_events")
    op.drop_column("listings", "reserved_at_price")
    op.drop_column("listings", "reservation_changed_at")
    op.drop_column("listings", "reservation_status")

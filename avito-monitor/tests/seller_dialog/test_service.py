"""Service layer for seller dialogs — CRUD only (no Avito or LLM calls)."""
import uuid
import pytest
from unittest.mock import AsyncMock

from sqlalchemy.sql.dml import Update

from app.db.models import SellerDialog
from app.services.seller_dialog.service import (
    close_dialog,
    create_dialog,
    get_dialog_by_channel,
    get_dialog_by_listing,
    set_stage,
    set_operator_mode,
)


@pytest.mark.asyncio
async def test_create_dialog_inserts_row():
    session = AsyncMock()
    profile_id = uuid.uuid4()
    listing_id = uuid.uuid4()

    await create_dialog(
        session,
        profile_id=profile_id,
        listing_id=listing_id,
        operator_mode=False,
    )

    # Verify session.add was called with a SellerDialog instance
    assert session.add.called
    added = session.add.call_args[0][0]
    assert added.profile_id == profile_id
    assert added.listing_id == listing_id
    assert added.stage == "contact"
    assert added.operator_mode is False
    assert added.channel_id is None


@pytest.mark.asyncio
async def test_close_dialog_issues_update_with_three_fields():
    """close_dialog must UPDATE the target row and set closed_at,
    closed_reason, and last_event_at — that last one keeps the kanban's
    recency sort working for any view that still includes closed rows."""
    session = AsyncMock()
    dialog_id = uuid.uuid4()

    await close_dialog(session, dialog_id, reason="rejected_by_operator")

    assert session.execute.await_count == 1
    stmt = session.execute.await_args[0][0]
    # It's an UPDATE on SellerDialog.
    assert isinstance(stmt, Update)
    assert stmt.table.name == SellerDialog.__tablename__

    # The SET-clause covers exactly the three fields we promise to write.
    set_keys = {col.key for col in stmt._values.keys()}  # type: ignore[attr-defined]
    assert set_keys == {"closed_at", "closed_reason", "last_event_at"}

    # closed_reason carries the operator-initiated sentinel.
    values_by_key = {col.key: val for col, val in stmt._values.items()}  # type: ignore[attr-defined]
    assert values_by_key["closed_reason"].value == "rejected_by_operator"
    # closed_at and last_event_at are bound to the same now() value.
    assert values_by_key["closed_at"].value == values_by_key["last_event_at"].value

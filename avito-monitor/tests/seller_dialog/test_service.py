"""Service layer for seller dialogs — CRUD only (no Avito or LLM calls)."""
import uuid
import pytest
from unittest.mock import AsyncMock

from app.services.seller_dialog.service import (
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

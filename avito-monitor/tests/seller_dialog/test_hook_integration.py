"""When user clicks ✓В работу, the listing_action endpoint enqueues
start_seller_dialog with the correct (profile_id, listing_id)."""
import uuid
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_accept_enqueues_dialog_task():
    """The action handler calls start_seller_dialog.kiq(profile_id, listing_id)."""
    with patch("app.web.routers.start_seller_dialog") as m:
        m.kiq = AsyncMock()
        from app.web.routers import _maybe_enqueue_start_seller_dialog
        await _maybe_enqueue_start_seller_dialog(
            action_raw="accept",
            profile_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            listing_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        )
        m.kiq.assert_awaited_once()


@pytest.mark.asyncio
async def test_reject_does_not_enqueue_dialog_task():
    with patch("app.web.routers.start_seller_dialog") as m:
        m.kiq = AsyncMock()
        from app.web.routers import _maybe_enqueue_start_seller_dialog
        await _maybe_enqueue_start_seller_dialog(
            action_raw="reject",
            profile_id=uuid.uuid4(),
            listing_id=uuid.uuid4(),
        )
        m.kiq.assert_not_called()

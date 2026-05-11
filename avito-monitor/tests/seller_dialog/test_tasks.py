"""Worker tasks for seller dialog."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_start_seller_dialog_creates_channel_and_sends_greeting():
    """Task: create dialog row + Avito channel + send greeting + persist message."""
    from app.tasks.seller_dialog_tasks import _start_seller_dialog_impl
    from app.services.seller_dialog.constants import GREETING_TEMPLATE

    profile_id = uuid.uuid4()
    listing_id = uuid.uuid4()
    avito_item_id = "1234567890"

    session = AsyncMock()
    xapi_client = AsyncMock()
    xapi_client.create_channel_by_item.return_value = {"id": "ch_abc"}
    xapi_client.send_text.return_value = {"id": "msg_xyz"}

    with patch("app.tasks.seller_dialog_tasks._get_avito_item_id",
               new=AsyncMock(return_value=avito_item_id)), \
         patch("app.tasks.seller_dialog_tasks.sd_service.get_dialog_by_listing",
               new=AsyncMock(return_value=None)), \
         patch("app.tasks.seller_dialog_tasks.ensure_chat_row",
               new=AsyncMock()) as m_ensure:
        result = await _start_seller_dialog_impl(
            session=session,
            xapi_client=xapi_client,
            profile_id=profile_id,
            listing_id=listing_id,
        )

    xapi_client.create_channel_by_item.assert_awaited_once_with(avito_item_id)
    xapi_client.send_text.assert_awaited_once_with("ch_abc", GREETING_TEMPLATE)
    # messenger_chats parent row must be ensured before the outgoing
    # MessengerMessage insert — otherwise FK violation on commit.
    m_ensure.assert_awaited_once_with("ch_abc", item_id=int(avito_item_id))
    assert result["channel_id"] == "ch_abc"
    assert result["greeting_message_id"] == "msg_xyz"


@pytest.mark.asyncio
async def test_start_seller_dialog_idempotent_when_dialog_exists():
    from app.tasks.seller_dialog_tasks import _start_seller_dialog_impl

    profile_id = uuid.uuid4()
    listing_id = uuid.uuid4()
    session = AsyncMock()
    xapi_client = AsyncMock()

    existing = MagicMock()
    existing.id = uuid.uuid4()
    existing.channel_id = "ch_already"
    existing.stage = "contact"

    with patch("app.tasks.seller_dialog_tasks.sd_service.get_dialog_by_listing",
               new=AsyncMock(return_value=existing)):
        result = await _start_seller_dialog_impl(
            session=session,
            xapi_client=xapi_client,
            profile_id=profile_id,
            listing_id=listing_id,
        )

    xapi_client.create_channel_by_item.assert_not_called()
    xapi_client.send_text.assert_not_called()
    assert result["skipped"] is True
    assert result["channel_id"] == "ch_already"

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

    # Mock listing lookup
    with patch("app.tasks.seller_dialog_tasks._get_avito_item_id",
               new=AsyncMock(return_value=avito_item_id)):
        result = await _start_seller_dialog_impl(
            session=session,
            xapi_client=xapi_client,
            profile_id=profile_id,
            listing_id=listing_id,
        )

    xapi_client.create_channel_by_item.assert_awaited_once_with(avito_item_id)
    xapi_client.send_text.assert_awaited_once_with("ch_abc", GREETING_TEMPLATE)
    assert result["channel_id"] == "ch_abc"
    assert result["greeting_message_id"] == "msg_xyz"

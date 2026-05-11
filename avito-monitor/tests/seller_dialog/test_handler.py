"""Inbound SSE handler — dispatches to seller dialog flow."""
import uuid
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_handle_seller_inbound_persists_message():
    """Inbound on a sales channel: persist incoming message with dialog_id."""
    from app.services.seller_dialog.handler import handle_seller_inbound

    session = AsyncMock()
    dialog = AsyncMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "contact"
    dialog.operator_mode = False

    with patch("app.services.seller_dialog.handler.get_dialog_by_channel",
               new=AsyncMock(return_value=dialog)), \
         patch("app.services.seller_dialog.handler.detect_yes_selling",
               new=AsyncMock(return_value=True)) as m_detect:
        await handle_seller_inbound(
            session=session,
            channel_id="ch_abc",
            message_id="m1",
            author_id="seller_id",
            text="Да, продаётся",
        )

    # Either we persisted the message AND attempted transition
    assert session.add.called
    m_detect.assert_awaited_once_with("Да, продаётся")


@pytest.mark.asyncio
async def test_handle_seller_inbound_skips_when_operator_mode():
    """When operator_mode=True, do NOT run LLM (operator handles dialog)."""
    from app.services.seller_dialog.handler import handle_seller_inbound

    session = AsyncMock()
    dialog = AsyncMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "contact"
    dialog.operator_mode = True

    with patch("app.services.seller_dialog.handler.get_dialog_by_channel",
               new=AsyncMock(return_value=dialog)), \
         patch("app.services.seller_dialog.handler.detect_yes_selling",
               new=AsyncMock(return_value=True)) as m_detect:
        await handle_seller_inbound(
            session=session,
            channel_id="ch_abc",
            message_id="m2",
            author_id="seller_id",
            text="any",
        )

    m_detect.assert_not_called()

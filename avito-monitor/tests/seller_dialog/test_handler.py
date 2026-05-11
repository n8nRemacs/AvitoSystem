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


@pytest.mark.asyncio
async def test_messenger_bot_routes_sales_channels_to_seller_handler():
    """When handle_event sees a known sales channel, it bypasses reliability gates."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.messenger_bot.handler import handle_event

    event = SimpleNamespace(
        event_name="new_message",
        data={"payload": {
            "channel_id": "ch_sales",
            "message_id": "m1",
            "author_id": "seller_id",
            "text": "Да, ещё продаётся",
        }},
    )
    client = AsyncMock()

    fake_dialog = MagicMock()
    fake_dialog.id = uuid.uuid4()

    sm_cm = MagicMock()
    sm_cm.__aenter__ = AsyncMock(return_value=AsyncMock())
    sm_cm.__aexit__ = AsyncMock(return_value=None)
    sessionmaker_factory = MagicMock(return_value=sm_cm)

    # Patch at the handler module's namespace (where the names are imported).
    # The `_persist_activity` patch avoids needing a real DB for the activity log.
    with patch("app.services.messenger_bot.handler.get_sessionmaker",
               return_value=sessionmaker_factory), \
         patch("app.services.messenger_bot.handler.get_dialog_by_channel",
               new=AsyncMock(return_value=fake_dialog)), \
         patch("app.services.messenger_bot.handler.handle_seller_inbound",
               new=AsyncMock()) as m_inbound, \
         patch("app.services.messenger_bot.handler._persist_activity",
               new=AsyncMock()):
        verdict = await handle_event(event, client=client)

    assert verdict.action == "sales_handled"
    m_inbound.assert_awaited_once()

"""Handler tests for stage='questions' branch."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_inbound_in_questions_stage_parses_and_marks_answered():
    from app.services.seller_dialog.handler import handle_seller_inbound

    dialog = MagicMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "questions"
    dialog.operator_mode = False
    dialog.recap_status = None

    asked_topic = MagicMock()
    asked_topic.id = uuid.uuid4()
    asked_topic.retry_count = 0
    asked_topic.topic_key = "battery_health"
    asked_topic.title = "АКБ %"
    asked_topic.default_phrasing = ""
    asked_topic.expected_format = "percent"

    session = AsyncMock()
    with patch("app.services.seller_dialog.handler.get_dialog_by_channel",
               new=AsyncMock(return_value=dialog)), \
         patch("app.services.seller_dialog.handler.ensure_chat_row",
               new=AsyncMock()), \
         patch("app.services.seller_dialog.handler.topic_state.get_asked_topic",
               new=AsyncMock(return_value=asked_topic)), \
         patch("app.services.seller_dialog.handler.topic_state.all_open_topics",
               new=AsyncMock(return_value=[])), \
         patch("app.services.seller_dialog.handler.parse_topic_answer",
               new=AsyncMock(return_value={
                   "status": "answered", "extracted": "87%", "side_topics": [],
               })), \
         patch("app.services.seller_dialog.handler.topic_state.mark_answered",
               new=AsyncMock()) as m_mark, \
         patch("app.services.seller_dialog.handler.dialog_tick_questions") as m_tick:
        m_tick.kiq = AsyncMock()
        await handle_seller_inbound(
            session=session, channel_id="ch_x", message_id="m1",
            author_id="seller", text="87 процентов",
        )

    m_mark.assert_awaited_once()
    m_tick.kiq.assert_awaited_once_with(str(dialog.id))


@pytest.mark.asyncio
async def test_inbound_recap_yes_confirms_and_pings_operator():
    from app.services.seller_dialog.handler import handle_seller_inbound

    dialog = MagicMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "questions"
    dialog.operator_mode = False
    dialog.recap_status = "pending_answer"

    session = AsyncMock()
    with patch("app.services.seller_dialog.handler.get_dialog_by_channel",
               new=AsyncMock(return_value=dialog)), \
         patch("app.services.seller_dialog.handler.ensure_chat_row",
               new=AsyncMock()), \
         patch("app.services.seller_dialog.handler.parse_seller_agreement",
               new=AsyncMock(return_value={"agreement": "yes", "corrections": None})), \
         patch("app.services.seller_dialog.handler.sd_service.set_recap_status",
               new=AsyncMock()) as m_set, \
         patch("app.services.seller_dialog.handler.enqueue_tg_ping",
               new=AsyncMock()) as m_ping:
        await handle_seller_inbound(
            session=session, channel_id="ch_x", message_id="m1",
            author_id="seller", text="да всё верно",
        )

    m_set.assert_awaited_once()
    m_ping.assert_awaited_once()
    assert m_ping.call_args.args[1] == "seller_dialog_ready_to_negotiate"

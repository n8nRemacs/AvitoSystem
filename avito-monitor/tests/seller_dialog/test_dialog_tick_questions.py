"""Tests for dialog_tick_questions state machine."""
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_first_tick_sends_opening_line_then_picks_first_pending():
    """First tick (no topics asked yet) sends opening line, then first question."""
    from app.tasks.seller_dialog_tasks import _dialog_tick_questions_impl

    dialog = MagicMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "questions"
    dialog.operator_mode = False
    dialog.recap_status = None
    dialog.channel_id = "ch_x"

    session = AsyncMock()
    xapi = AsyncMock()
    xapi.send_text = AsyncMock(side_effect=[{"id": "m_open"}, {"id": "m_q1"}])

    topic = MagicMock()
    topic.id = uuid.uuid4()
    topic.title = "АКБ %"
    topic.default_phrasing = "x"
    topic.expected_format = "percent"
    topic.topic_key = "battery_health"

    with patch("app.tasks.seller_dialog_tasks.sd_service.get_dialog",
               new=AsyncMock(return_value=dialog)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.get_asked_topic",
               new=AsyncMock(return_value=None)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.count_open",
               new=AsyncMock(return_value=1)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.pick_next_pending",
               new=AsyncMock(return_value=topic)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.mark_asked",
               new=AsyncMock()) as m_mark, \
         patch("app.tasks.seller_dialog_tasks.formulate_question",
               new=AsyncMock(return_value="Какой % АКБ?")), \
         patch("app.tasks.seller_dialog_tasks.has_started_questions",
               new=AsyncMock(return_value=False)), \
         patch("app.tasks.seller_dialog_tasks.asyncio.sleep",
               new=AsyncMock()):
        await _dialog_tick_questions_impl(session, xapi, dialog.id)

    # Two sends: opening + first question
    assert xapi.send_text.await_count == 2
    first_call = xapi.send_text.call_args_list[0]
    assert "вопросов по Вашему аппарату" in first_call.args[1]
    second_call = xapi.send_text.call_args_list[1]
    assert second_call.args[1] == "Какой % АКБ?"
    m_mark.assert_awaited_once()


@pytest.mark.asyncio
async def test_tick_waits_when_topic_already_asked():
    from app.tasks.seller_dialog_tasks import _dialog_tick_questions_impl

    dialog = MagicMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "questions"
    dialog.operator_mode = False
    dialog.recap_status = None
    dialog.channel_id = "ch_x"

    asked_topic = MagicMock()
    asked_topic.id = uuid.uuid4()

    session = AsyncMock()
    xapi = AsyncMock()

    with patch("app.tasks.seller_dialog_tasks.sd_service.get_dialog",
               new=AsyncMock(return_value=dialog)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.get_asked_topic",
               new=AsyncMock(return_value=asked_topic)):
        await _dialog_tick_questions_impl(session, xapi, dialog.id)

    xapi.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_tick_sends_recap_when_all_topics_done():
    from app.tasks.seller_dialog_tasks import _dialog_tick_questions_impl

    dialog = MagicMock()
    dialog.id = uuid.uuid4()
    dialog.stage = "questions"
    dialog.operator_mode = False
    dialog.recap_status = None
    dialog.channel_id = "ch_x"

    session = AsyncMock()
    xapi = AsyncMock()
    xapi.send_text = AsyncMock(return_value={"id": "m_recap"})

    with patch("app.tasks.seller_dialog_tasks.sd_service.get_dialog",
               new=AsyncMock(return_value=dialog)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.get_asked_topic",
               new=AsyncMock(return_value=None)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.count_open",
               new=AsyncMock(return_value=0)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.pick_next_pending",
               new=AsyncMock(return_value=None)), \
         patch("app.tasks.seller_dialog_tasks.topic_state.answered_topics",
               new=AsyncMock(return_value=[(MagicMock(title="АКБ %"), "87%")])), \
         patch("app.tasks.seller_dialog_tasks.formulate_recap",
               new=AsyncMock(return_value="Итак: АКБ 87%. Всё верно?")), \
         patch("app.tasks.seller_dialog_tasks.has_started_questions",
               new=AsyncMock(return_value=True)), \
         patch("app.tasks.seller_dialog_tasks.sd_service.set_recap",
               new=AsyncMock()) as m_set:
        await _dialog_tick_questions_impl(session, xapi, dialog.id)

    xapi.send_text.assert_awaited_once()
    assert "Итак" in xapi.send_text.call_args.args[1]
    m_set.assert_awaited_once()

"""View tests for Phase B (3rd column + filter)."""
import uuid
import pytest
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_query_returns_three_columns_including_questions():
    from app.services.seller_dialog_view import query_kanban_cards, PHASE_B_STAGES

    session = AsyncMock()
    rows = AsyncMock()
    rows.all = lambda: []
    session.execute = AsyncMock(return_value=rows)

    out = await query_kanban_cards(session, user_id=uuid.uuid4())
    assert set(out.keys()) >= {"contact", "questions_setup", "questions"}
    assert "questions" in PHASE_B_STAGES


@pytest.mark.asyncio
async def test_query_filters_by_profile_id():
    from app.services.seller_dialog_view import query_kanban_cards, KanbanFilters

    session = AsyncMock()
    rows = AsyncMock()
    rows.all = lambda: []
    session.execute = AsyncMock(return_value=rows)
    pid = uuid.uuid4()
    await query_kanban_cards(session, user_id=uuid.uuid4(),
                             filters=KanbanFilters(profile_ids=[pid]))
    # Just assert the query was built (compiled SQL contains profile_id)
    sql_text = str(session.execute.call_args.args[0])
    assert "profile_id" in sql_text.lower()

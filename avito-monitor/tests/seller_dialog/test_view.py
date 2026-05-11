"""Read-side query that powers the kanban UI."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.seller_dialog_view import (
    KanbanCard,
    KanbanFilters,
    PHASE_A_STAGES,
    query_kanban_cards,
)


def test_phase_a_stages_contains_two_stages():
    assert PHASE_A_STAGES == ["contact", "questions_setup"]


def test_kanban_filters_default_empty():
    f = KanbanFilters()
    assert f.profile_ids == []


def test_kanban_card_dataclass_fields():
    fields_set = {
        "dialog_id", "listing_id", "profile_id", "profile_name",
        "avito_id", "title", "price", "image_url", "stage",
        "operator_mode", "opened_at", "last_event_at",
    }
    annotations = set(KanbanCard.__annotations__.keys())
    assert fields_set <= annotations


@pytest.mark.asyncio
async def test_query_kanban_cards_filters_closed_dialogs():
    """The kanban must NOT surface dialogs whose closed_at is set —
    those were retired by reject-from-kanban (or similar) and are no
    longer actionable. Verifies the SQL query carries the filter by
    inspecting the statement passed to session.execute."""
    session = AsyncMock()
    # Empty result is fine — we only care about the WHERE clause.
    result = MagicMock()
    result.all = MagicMock(return_value=[])
    session.execute.return_value = result

    await query_kanban_cards(session, uuid.uuid4())

    assert session.execute.await_count == 1
    stmt = session.execute.await_args[0][0]
    sql = str(stmt.compile(compile_kwargs={"literal_binds": False}))
    # The render of `column.is_(None)` is `column IS NULL`.
    assert "seller_dialogs.closed_at IS NULL" in sql

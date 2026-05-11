"""Read-side query that powers the kanban UI."""
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

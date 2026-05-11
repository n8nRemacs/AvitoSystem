"""Stage transition rules — pure functions, easy to unit test."""
from app.services.seller_dialog.transitions import next_stage_on_seller_reply
from app.services.seller_dialog.constants import (
    STAGE_CONTACT, STAGE_QUESTIONS_SETUP, STAGE_QUESTIONS,
)


def test_contact_to_questions_setup_on_yes_selling():
    """At contact, LLM says yes-selling → advance to questions_setup."""
    new = next_stage_on_seller_reply(
        current_stage=STAGE_CONTACT,
        llm_yes_selling=True,
    )
    assert new == STAGE_QUESTIONS_SETUP


def test_contact_stays_on_low_confidence():
    """At contact, LLM not confident enough → keep waiting (no transition)."""
    new = next_stage_on_seller_reply(
        current_stage=STAGE_CONTACT,
        llm_yes_selling=False,
    )
    assert new is None  # no transition


def test_questions_setup_no_auto_transition():
    """At questions_setup, no auto-transition from a seller reply (operator drives)."""
    new = next_stage_on_seller_reply(
        current_stage=STAGE_QUESTIONS_SETUP,
        llm_yes_selling=True,
    )
    assert new is None

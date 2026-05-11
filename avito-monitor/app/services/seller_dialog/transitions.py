"""Pure stage-transition logic for seller dialogs.

Phase A only knows the contact → questions_setup transition. Later phases
extend the function by adding more cases.
"""
from __future__ import annotations

from app.services.seller_dialog.constants import (
    STAGE_CONTACT,
    STAGE_QUESTIONS_SETUP,
)


def next_stage_on_seller_reply(
    *,
    current_stage: str,
    llm_yes_selling: bool,
) -> str | None:
    """Decide whether a fresh seller reply triggers a stage transition.

    Returns the new stage name, or None if no transition.
    """
    if current_stage == STAGE_CONTACT and llm_yes_selling:
        return STAGE_QUESTIONS_SETUP
    return None

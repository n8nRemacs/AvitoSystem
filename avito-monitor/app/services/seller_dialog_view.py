"""Read-side query service for the kanban UI.

Returns dialogs grouped by stage. Phase B renders three columns
(contact + questions_setup + questions); later phases add more by
extending ``PHASE_B_STAGES``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Listing, SearchProfile, SellerDialog
from app.services.seller_dialog.constants import (
    STAGE_CONTACT,
    STAGE_QUESTIONS,
    STAGE_QUESTIONS_SETUP,
)


PHASE_B_STAGES = [STAGE_CONTACT, STAGE_QUESTIONS_SETUP, STAGE_QUESTIONS]
# Backwards-compat alias (callers using the old name still work).
PHASE_A_STAGES = PHASE_B_STAGES


@dataclass
class KanbanCard:
    dialog_id: uuid.UUID
    listing_id: uuid.UUID
    profile_id: uuid.UUID
    profile_name: str
    avito_id: int
    title: str
    price: int | None
    image_url: str | None
    stage: str
    operator_mode: bool
    opened_at: datetime
    last_event_at: datetime | None


@dataclass
class KanbanFilters:
    profile_ids: list[uuid.UUID] = field(default_factory=list)


def _first_image_url(images_jsonb: Any) -> str | None:
    if isinstance(images_jsonb, list) and images_jsonb:
        first = images_jsonb[0]
        if isinstance(first, dict):
            return first.get("url")
    return None


async def query_kanban_cards(
    session: AsyncSession,
    user_id: uuid.UUID | str,
    filters: KanbanFilters | None = None,
) -> dict[str, list[KanbanCard]]:
    """Return dict[stage_name -> list[KanbanCard]] for all stages in PHASE_B_STAGES.

    Empty list for stages with no cards (so the template can always iterate).
    """
    filters = filters or KanbanFilters()

    stmt = (
        select(
            SellerDialog,
            Listing,
            SearchProfile.name.label("profile_name"),
        )
        .select_from(SellerDialog)
        .join(Listing, Listing.id == SellerDialog.listing_id)
        .join(SearchProfile, SearchProfile.id == SellerDialog.profile_id)
        .where(
            SearchProfile.user_id == user_id,
            SellerDialog.stage.in_(PHASE_B_STAGES),
            SellerDialog.closed_at.is_(None),
        )
        .order_by(SellerDialog.opened_at.desc())
    )

    if filters.profile_ids:
        stmt = stmt.where(SellerDialog.profile_id.in_(filters.profile_ids))

    rows = (await session.execute(stmt)).all()

    out: dict[str, list[KanbanCard]] = {s: [] for s in PHASE_B_STAGES}
    for sd, listing, profile_name in rows:
        card = KanbanCard(
            dialog_id=sd.id,
            listing_id=sd.listing_id,
            profile_id=sd.profile_id,
            profile_name=profile_name,
            avito_id=listing.avito_id,
            title=listing.title,
            price=int(listing.price) if listing.price is not None else None,
            image_url=_first_image_url(listing.images),
            stage=sd.stage,
            operator_mode=sd.operator_mode,
            opened_at=sd.opened_at,
            last_event_at=sd.last_event_at,
        )
        out[sd.stage].append(card)
    return out

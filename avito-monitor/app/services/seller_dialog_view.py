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

from app.db.models import Listing, ListingFeature, SearchProfile, SellerDialog
from app.services.listings_view import ListingImage, _first_image_url, _images_list
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
    images: list[ListingImage]
    web_url: str
    description: str | None
    condition_reasoning: str | None
    condition_confidence: float | None
    stage: str
    operator_mode: bool
    opened_at: datetime
    last_event_at: datetime | None
    features: dict[str, str] = field(default_factory=dict)
    # Phase 2.1: rich feature dict for price_signal + info_api partials.
    # Maps feature_key -> {kind, state, value, evidence} for all kinds.
    features_by_key: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class KanbanFilters:
    profile_ids: list[uuid.UUID] = field(default_factory=list)


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

    # Batch-load features for all listings in one query (no N+1).
    # Phase 2.1: also fetch kind/value/evidence for price_signal + info_api partials.
    listing_ids = [listing.id for _, listing, _ in rows]
    features_rows = []
    if listing_ids:
        features_rows = (await session.execute(
            select(ListingFeature.listing_id, ListingFeature.feature_key,
                   ListingFeature.state, ListingFeature.kind,
                   ListingFeature.value, ListingFeature.evidence)
            .where(ListingFeature.listing_id.in_(listing_ids))
        )).all()
    # Legacy defect dict: {feature_key: state} — consumed by _features_block.html
    features_by_listing: dict[uuid.UUID, dict[str, str]] = {}
    # Rich dict: {feature_key: {kind, state, value, evidence}} — consumed by new partials
    features_by_key_by_listing: dict[uuid.UUID, dict[str, dict[str, Any]]] = {}
    for lid, fkey, state, kind, value, evidence in features_rows:
        if state is not None:
            features_by_listing.setdefault(lid, {})[fkey] = state
        features_by_key_by_listing.setdefault(lid, {})[fkey] = {
            "kind": kind,
            "state": state,
            "value": value,
            "evidence": evidence,
        }

    out: dict[str, list[KanbanCard]] = {s: [] for s in PHASE_B_STAGES}
    for sd, listing, profile_name in rows:
        listing_url = getattr(listing, "url", None)
        if listing_url and listing_url.startswith("https://"):
            web_url = listing_url
        else:
            web_url = f"https://www.avito.ru/{listing.avito_id}"
        card = KanbanCard(
            dialog_id=sd.id,
            listing_id=sd.listing_id,
            profile_id=sd.profile_id,
            profile_name=profile_name,
            avito_id=listing.avito_id,
            title=listing.title,
            price=int(listing.price) if listing.price is not None else None,
            image_url=_first_image_url(listing.images),
            images=_images_list(listing.images),
            web_url=web_url,
            description=listing.description,
            condition_reasoning=listing.condition_reasoning,
            condition_confidence=listing.condition_confidence,
            stage=sd.stage,
            operator_mode=sd.operator_mode,
            opened_at=sd.opened_at,
            last_event_at=sd.last_event_at,
            features=features_by_listing.get(listing.id, {}),
            features_by_key=features_by_key_by_listing.get(listing.id, {}),
        )
        out[sd.stage].append(card)
    return out

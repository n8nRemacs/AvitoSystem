"""Read-side query service for the /listings feed (UI Spec §4.5).

Composes one big SELECT across listings + profile_listings (+ search_profiles
for the filter chips) so the page can render a card per row without N+1.
Filters mirror the UI Spec: profile, condition_class, zone (alert/market),
period (24h/7d/30d/all). Sort key picked from a fixed allow-list to dodge
SQL injection through the query string.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Listing, ProfileListing, SearchProfile


PERIOD_TO_HOURS = {
    "24h": 24,
    "7d": 24 * 7,
    "30d": 24 * 30,
    "all": None,
}

ZONE_ALERT = "alert"
ZONE_MARKET = "market"
ZONE_ALL = "all"

SORT_KEYS = {
    "date": "discovered_at_desc",
    "price_asc": "price_asc",
    "price_desc": "price_desc",
    "delta": "price_delta_desc",  # biggest drop first
}


@dataclass
class ListingRow:
    """One card on the /listings page."""
    listing_id: uuid.UUID
    profile_id: uuid.UUID
    profile_name: str
    avito_id: int
    title: str
    price: int | None
    initial_price: int | None
    price_changed_at: datetime | None
    region: str | None
    seller_type: str | None
    seller_name: str | None
    condition_class: str
    condition_confidence: float | None
    in_alert_zone: bool
    processing_status: str
    user_action: str | None
    discovered_at: datetime | None
    last_seen_at: datetime | None
    image_url: str | None
    url: str | None

    @property
    def price_delta_pct(self) -> float | None:
        if self.initial_price and self.price and self.initial_price != self.price:
            return round((self.price - self.initial_price) * 100 / self.initial_price, 1)
        return None


@dataclass
class ListingFilters:
    profile_ids: list[uuid.UUID] | None = None
    condition_classes: list[str] | None = None
    zone: str = ZONE_ALL
    period: str = "7d"
    sort: str = "date"
    limit: int = 30
    offset: int = 0


def _first_image_url(images_jsonb: Any) -> str | None:
    if not isinstance(images_jsonb, list) or not images_jsonb:
        return None
    first = images_jsonb[0]
    if isinstance(first, dict):
        return first.get("url")
    return None


async def query_listings(
    session: AsyncSession,
    user_id: uuid.UUID,
    f: ListingFilters,
) -> tuple[list[ListingRow], int]:
    """Return (rows, total_count) for the given filters."""
    stmt = (
        select(
            Listing,
            ProfileListing,
            SearchProfile.id.label("p_id"),
            SearchProfile.name.label("p_name"),
        )
        .select_from(ProfileListing)
        .join(Listing, Listing.id == ProfileListing.listing_id)
        .join(SearchProfile, SearchProfile.id == ProfileListing.profile_id)
        .where(SearchProfile.user_id == user_id)
    )

    if f.profile_ids:
        stmt = stmt.where(ProfileListing.profile_id.in_(f.profile_ids))
    if f.condition_classes:
        stmt = stmt.where(Listing.condition_class.in_(f.condition_classes))
    if f.zone == ZONE_ALERT:
        stmt = stmt.where(ProfileListing.in_alert_zone.is_(True))
    elif f.zone == ZONE_MARKET:
        stmt = stmt.where(ProfileListing.in_alert_zone.is_(False))

    hours = PERIOD_TO_HOURS.get(f.period)
    if hours is not None:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
        stmt = stmt.where(ProfileListing.discovered_at >= cutoff)

    # Count BEFORE order/pagination so the UI can show "238 лотов".
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    sort_key = SORT_KEYS.get(f.sort, "discovered_at_desc")
    if sort_key == "price_asc":
        stmt = stmt.order_by(Listing.price.asc().nullslast())
    elif sort_key == "price_desc":
        stmt = stmt.order_by(Listing.price.desc().nullslast())
    elif sort_key == "price_delta_desc":
        # Largest drop first: cheaper-than-initial sorted by absolute delta.
        # Using initial_price - price gives a positive delta on a price drop.
        stmt = stmt.order_by(
            (Listing.initial_price - Listing.price).desc().nullslast(),
            ProfileListing.discovered_at.desc(),
        )
    else:
        stmt = stmt.order_by(ProfileListing.discovered_at.desc().nullslast())

    stmt = stmt.limit(f.limit).offset(f.offset)
    rows = (await session.execute(stmt)).all()

    out: list[ListingRow] = []
    for listing, link, p_id, p_name in rows:
        out.append(ListingRow(
            listing_id=listing.id,
            profile_id=p_id,
            profile_name=p_name,
            avito_id=listing.avito_id,
            title=listing.title,
            price=int(listing.price) if listing.price is not None else None,
            initial_price=int(listing.initial_price) if listing.initial_price is not None else None,
            price_changed_at=listing.last_price_change_at,
            region=listing.region,
            seller_type=listing.seller_type,
            seller_name=getattr(listing, "seller_name", None),
            condition_class=listing.condition_class,
            condition_confidence=listing.condition_confidence,
            in_alert_zone=link.in_alert_zone,
            processing_status=link.processing_status,
            user_action=link.user_action,
            discovered_at=link.discovered_at,
            last_seen_at=listing.last_seen_at,
            image_url=_first_image_url(listing.images),
            url=listing.url,
        ))
    return out, total


async def filter_summary(
    session: AsyncSession, user_id: uuid.UUID
) -> dict[str, Any]:
    """Profile names + condition counts for the filter chips."""
    profiles_stmt = (
        select(SearchProfile.id, SearchProfile.name, SearchProfile.is_active)
        .where(SearchProfile.user_id == user_id)
        .order_by(SearchProfile.name)
    )
    profiles = [
        {"id": pid, "name": name, "is_active": is_active}
        for pid, name, is_active in (await session.execute(profiles_stmt)).all()
    ]

    cond_stmt = (
        select(Listing.condition_class, func.count())
        .select_from(ProfileListing)
        .join(Listing, Listing.id == ProfileListing.listing_id)
        .join(SearchProfile, SearchProfile.id == ProfileListing.profile_id)
        .where(SearchProfile.user_id == user_id)
        .group_by(Listing.condition_class)
    )
    conditions = {
        cls: int(cnt)
        for cls, cnt in (await session.execute(cond_stmt)).all()
    }

    return {"profiles": profiles, "conditions": conditions}

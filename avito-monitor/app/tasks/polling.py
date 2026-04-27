"""``poll_profile`` task — the worker tick that fetches a search page,
syncs ``listings`` and ``profile_listings``, and (in Block 4.2) hands
new lots off to the LLM analyser.

Idempotency: every ``upsert`` is keyed by ``listings.avito_id``, so
re-running the same poll never creates duplicates and never spams
notifications. Disappeared lots (in DB but not in the latest page)
are bumped to ``status=closed`` once their ``last_seen_at`` is older
than this run's ``started_at``.

The Block 4.1 cut intentionally stops short of LLM dispatch — that
plugs in via ``analyze_listing`` in Block 4.2. The corresponding
section here is a clearly-marked TODO so the worker boots and runs
end-to-end against real Avito today, even before classification is
wired up.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.base import get_sessionmaker
from app.db.models import (
    Listing,
    ProfileListing,
    ProfileRun,
    SearchProfile,
)
from app.db.models.enums import ListingStatus, ProfileRunStatus
from app.integrations.avito_mcp_client.client import AvitoMcpClient
from app.tasks.broker import broker
from shared.models.avito import ListingShort

log = logging.getLogger(__name__)


def _to_decimal(value: int | float | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _is_in_alert_zone(price: int | float | None, profile: SearchProfile) -> bool:
    """``True`` iff price is inside the configured alert price band."""
    if price is None:
        return False
    if profile.alert_min_price is None and profile.alert_max_price is None:
        return False
    if profile.alert_min_price is not None and price < profile.alert_min_price:
        return False
    if profile.alert_max_price is not None and price > profile.alert_max_price:
        return False
    return True


def _images_to_jsonb(item: ListingShort) -> list[dict[str, Any]]:
    return [img.model_dump(mode="json") for img in item.images]


async def _upsert_listing(
    session, item: ListingShort, run_started_at: datetime
) -> tuple[uuid.UUID, bool, bool, float | None]:
    """Upsert one listing by ``avito_id`` and report (id, is_new, price_changed, prev_price).

    For an existing row we only refresh ``last_seen_at``, ``price`` (if
    actually changed), ``last_price_change_at`` and the few mutable
    cosmetic fields. Anything LLM-derived stays untouched so a
    re-poll never wipes out a classification we already paid for.
    """
    new_price = _to_decimal(item.price)
    insert_stmt = pg_insert(Listing).values(
        avito_id=item.id,
        title=item.title,
        price=new_price,
        initial_price=new_price,
        currency=item.currency or "RUB",
        region=item.region,
        url=item.url,
        images=_images_to_jsonb(item),
        seller_id=str(item.seller_id) if item.seller_id is not None else None,
        seller_type=item.seller_type,
        first_seen_at=run_started_at,
        last_seen_at=run_started_at,
        status=ListingStatus.ACTIVE.value,
    ).returning(Listing.id, Listing.price, Listing.first_seen_at)

    do_update = insert_stmt.on_conflict_do_update(
        index_elements=[Listing.avito_id],
        set_={
            "title": insert_stmt.excluded.title,
            "region": insert_stmt.excluded.region,
            "url": insert_stmt.excluded.url,
            "images": insert_stmt.excluded.images,
            "last_seen_at": insert_stmt.excluded.last_seen_at,
            "status": ListingStatus.ACTIVE.value,
        },
    )
    row = (await session.execute(do_update)).one()
    listing_id, stored_price, first_seen_at = row.id, row.price, row.first_seen_at
    is_new = first_seen_at == run_started_at

    price_changed = False
    prev_price: float | None = None
    if not is_new and new_price is not None and stored_price is not None:
        if Decimal(str(stored_price)) != new_price:
            prev_price = float(stored_price)
            await session.execute(
                update(Listing)
                .where(Listing.id == listing_id)
                .values(
                    price=new_price,
                    last_price_change_at=run_started_at,
                )
            )
            price_changed = True

    return listing_id, is_new, price_changed, prev_price


async def _upsert_profile_listing(
    session,
    *,
    profile_id: uuid.UUID,
    listing_id: uuid.UUID,
    in_alert_zone: bool,
    discovered_at: datetime,
) -> bool:
    """Upsert the M:N row. Returns True if it was a fresh insert."""
    insert_stmt = pg_insert(ProfileListing).values(
        profile_id=profile_id,
        listing_id=listing_id,
        discovered_at=discovered_at,
        in_alert_zone=in_alert_zone,
    )
    do_update = insert_stmt.on_conflict_do_update(
        index_elements=[ProfileListing.profile_id, ProfileListing.listing_id],
        set_={"in_alert_zone": insert_stmt.excluded.in_alert_zone},
    ).returning(ProfileListing.discovered_at)
    row = (await session.execute(do_update)).one()
    return row.discovered_at == discovered_at


async def _close_disappeared(
    session, *, profile_id: uuid.UUID, run_started_at: datetime
) -> int:
    """Mark listings linked to this profile that weren't seen in this run as ``closed``."""
    stmt = (
        update(Listing)
        .where(
            Listing.id.in_(
                select(ProfileListing.listing_id).where(
                    ProfileListing.profile_id == profile_id
                )
            ),
            Listing.last_seen_at < run_started_at,
            Listing.status == ListingStatus.ACTIVE.value,
        )
        .values(status=ListingStatus.CLOSED.value)
        .returning(Listing.id)
    )
    rows = (await session.execute(stmt)).fetchall()
    return len(rows)


@broker.task(task_name="app.tasks.polling.poll_profile")
async def poll_profile(profile_id: str) -> dict[str, Any]:
    """Fetch one search page for a profile and sync listings into DB.

    Returns a small summary dict so the scheduler / health-checker can
    inspect outcomes via the result backend without re-querying the DB.
    """
    sessionmaker = get_sessionmaker()
    pid = uuid.UUID(profile_id)
    started_at = datetime.now(timezone.utc)

    async with sessionmaker() as session:
        profile = await session.get(SearchProfile, pid)
        if profile is None:
            log.warning("polling.profile_not_found id=%s", profile_id)
            return {"status": "skipped", "reason": "profile not found"}
        if not profile.is_active:
            log.info("polling.profile_inactive id=%s", profile_id)
            return {"status": "skipped", "reason": "profile inactive"}

        run = ProfileRun(
            profile_id=pid,
            started_at=started_at,
            status=ProfileRunStatus.RUNNING.value,
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        run_id = run.id

    listings_seen = 0
    listings_new = 0
    listings_in_alert = 0
    price_changed_count = 0
    error_message: str | None = None

    try:
        async with AvitoMcpClient() as mcp:
            page = await mcp.fetch_search_page(profile.avito_search_url)
    except Exception as exc:  # pragma: no cover — covered by health-checker
        log.exception(
            "polling.fetch_failed profile_id=%s url=%s",
            profile_id, profile.avito_search_url,
        )
        async with sessionmaker() as session:
            await session.execute(
                update(ProfileRun)
                .where(ProfileRun.id == run_id)
                .values(
                    finished_at=datetime.now(timezone.utc),
                    status=ProfileRunStatus.FAILED.value,
                    error_message=str(exc)[:512],
                )
            )
            await session.commit()
        return {"status": "failed", "reason": "fetch_failed"}

    blocked = set(profile.blocked_sellers or [])

    async with sessionmaker() as session:
        for item in page.items:
            if item.seller_id is not None and str(item.seller_id) in blocked:
                continue

            listings_seen += 1
            listing_id, is_new, price_changed, _prev_price = await _upsert_listing(
                session, item, started_at
            )
            if is_new:
                listings_new += 1
            if price_changed:
                price_changed_count += 1

            in_alert = _is_in_alert_zone(item.price, profile)
            if in_alert:
                listings_in_alert += 1
            await _upsert_profile_listing(
                session,
                profile_id=pid,
                listing_id=listing_id,
                in_alert_zone=in_alert,
                discovered_at=started_at,
            )

            # TODO(Block 4.2): for new lots OR lots whose price just dropped
            # into the alert zone, enqueue analyze_listing(listing_id, profile_id)
            # in the LLM classify queue. Block 4.1 stops at DB sync so we can
            # ship + smoke the polling loop without OpenRouter spend.

        closed = await _close_disappeared(
            session, profile_id=pid, run_started_at=started_at
        )

        await session.execute(
            update(ProfileRun)
            .where(ProfileRun.id == run_id)
            .values(
                finished_at=datetime.now(timezone.utc),
                status=ProfileRunStatus.SUCCESS.value,
                listings_seen=listings_seen,
                listings_new=listings_new,
                listings_in_alert=listings_in_alert,
                metrics={
                    "price_changes": price_changed_count,
                    "closed_disappeared": closed,
                    "page_total": page.total,
                    "applied_query": page.applied_query,
                },
            )
        )
        await session.commit()

    log.info(
        "polling.success profile_id=%s seen=%d new=%d in_alert=%d closed=%d",
        profile_id, listings_seen, listings_new, listings_in_alert, closed,
    )
    return {
        "status": "success",
        "listings_seen": listings_seen,
        "listings_new": listings_new,
        "listings_in_alert": listings_in_alert,
        "price_changes": price_changed_count,
        "closed_disappeared": closed,
    }

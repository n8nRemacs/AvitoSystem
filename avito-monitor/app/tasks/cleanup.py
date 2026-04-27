"""Daily DB cleanup — applies the ADR-009 retention rules.

Cutoffs (per-listing, evaluated against ``last_seen_at``):

* ``market_data`` (or never-classified) — **30 days**
* ``analyzed`` (LLM-matched but didn't notify) — **90 days**
* ``notified`` (a Notification was created) — **kept indefinitely** for audit

Each ``listings`` row may participate in several ``profile_listings`` rows
(one per profile that ever saw it). Retention is per-listing, so we
look at the *strongest* status across every link: a listing held open
because at least one profile got a notification stays. Only when *all*
links are at or below ``analyzed`` (and old enough) does the listing
get deleted, taking the link rows with it through the schema's CASCADE.

``Notification.related_listing_id`` is ``ON DELETE SET NULL`` (see
``app/db/models/notification.py``), so the notification trail survives
the listing — exactly what the audit requirement asks for.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select

from app.db.base import get_sessionmaker
from app.db.models import Listing, ProfileListing
from app.db.models.enums import ProcessingStatus
from app.tasks.broker import broker

log = logging.getLogger(__name__)


# ADR-009 retention windows. Hours-resolution to make tests / overrides
# easier; the daily tick is the practical resolution we actually use.
_RETENTION_DAYS = {
    "market_data": 30,
    "analyzed": 90,
}

# Statuses that should NEVER be auto-deleted regardless of age.
_KEEP_FOREVER = {ProcessingStatus.NOTIFIED.value}

# Statuses subject to the 90-day window. Anything else (fetched /
# classified / pending_match / failed / market_data) falls under 30 days.
_LONG_RETENTION = {ProcessingStatus.ANALYZED.value}


@broker.task(task_name="app.tasks.cleanup.cleanup_old_listings")
async def cleanup_old_listings() -> dict[str, int]:
    """Delete listings whose every profile-link has aged past the cutoff."""
    sessionmaker = get_sessionmaker()
    now = datetime.now(timezone.utc)
    cutoff_30 = now - timedelta(days=_RETENTION_DAYS["market_data"])
    cutoff_90 = now - timedelta(days=_RETENTION_DAYS["analyzed"])

    async with sessionmaker() as session:
        # Per-listing aggregation: collect every distinct processing
        # status currently linked to a listing, plus its last_seen_at.
        # We then decide retention on the python side — the conditional
        # logic is gnarlier than what we want to express in SQL.
        agg = (
            select(
                Listing.id,
                Listing.last_seen_at,
                func.array_agg(func.distinct(ProfileListing.processing_status))
                .label("statuses"),
            )
            .outerjoin(ProfileListing, ProfileListing.listing_id == Listing.id)
            # Skip listings still seen recently — saves a lot of work.
            .where(Listing.last_seen_at < cutoff_30)
            .group_by(Listing.id, Listing.last_seen_at)
        )
        rows = (await session.execute(agg)).all()

        to_delete: list = []
        kept_notified = 0
        kept_recent_analyzed = 0
        for listing_id, last_seen_at, statuses in rows:
            statuses = set(s for s in (statuses or []) if s is not None)
            if statuses & _KEEP_FOREVER:
                kept_notified += 1
                continue
            # If any link is in long-retention set, apply 90-day cutoff.
            if statuses & _LONG_RETENTION:
                if last_seen_at is not None and last_seen_at < cutoff_90:
                    to_delete.append(listing_id)
                else:
                    kept_recent_analyzed += 1
                continue
            # Default: 30-day cutoff. We already filtered on it in SQL.
            to_delete.append(listing_id)

        deleted = 0
        if to_delete:
            # CASCADE on profile_listings + llm_analyses. Notifications
            # have ON DELETE SET NULL so the audit trail survives.
            result = await session.execute(
                delete(Listing).where(Listing.id.in_(to_delete))
            )
            deleted = result.rowcount or 0
            await session.commit()

    log.info(
        "cleanup.done deleted=%d kept_notified=%d kept_recent_analyzed=%d",
        deleted, kept_notified, kept_recent_analyzed,
    )
    return {
        "deleted": deleted,
        "kept_notified": kept_notified,
        "kept_recent_analyzed": kept_recent_analyzed,
    }


@broker.task(
    task_name="app.tasks.cleanup.tick",
    schedule=[{"cron": "30 3 * * *"}],
)
async def tick() -> dict[str, int]:
    """Daily 03:30 UTC: enqueue cleanup. Single job, no per-profile fan-out."""
    try:
        await cleanup_old_listings.kiq()
    except Exception:
        log.exception("cleanup.tick.kiq_failed")
        return {"enqueued": 0}
    return {"enqueued": 1}

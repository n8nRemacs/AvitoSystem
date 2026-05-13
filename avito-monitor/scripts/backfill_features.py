"""Backfill listing_features rows for all active listings.

For each (profile, listing) pair currently in user_action IN
(NULL, 'pending', 'viewed', 'accepted'), run analyze_listing_features
exactly once. Reports progress every 25 listings.

Phase 2.1: analyze_listing_features now writes all three feature kinds
(defect + price_signal + info_api), so this script populates the full
unified taxonomy in one pass — no separate scripts needed.

Usage:
    python -m scripts.backfill_features
    python -m scripts.backfill_features --profile <profile_id>
    python -m scripts.backfill_features --dry-run
    python -m scripts.backfill_features --limit 10     # smoke run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import uuid

from sqlalchemy import or_, select, update

from app.db.base import dispose_engine, get_sessionmaker
from app.db.models import Listing, ProfileListing
from app.services.defect_features.pipeline import analyze_listing_features


logger = logging.getLogger("backfill_features")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


ACTIVE_USER_ACTIONS = ("pending", "viewed", "accepted")


async def run(
    profile_filter: uuid.UUID | None, dry_run: bool, limit: int | None
) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        q = (
            select(ProfileListing.profile_id, ProfileListing.listing_id, Listing)
            .join(Listing, Listing.id == ProfileListing.listing_id)
            .where(
                or_(
                    ProfileListing.user_action.is_(None),
                    ProfileListing.user_action.in_(ACTIVE_USER_ACTIONS),
                )
            )
        )
        if profile_filter is not None:
            q = q.where(ProfileListing.profile_id == profile_filter)
        if limit is not None:
            q = q.limit(limit)
        rows = (await session.execute(q)).all()
        logger.info("found %d pairs to backfill", len(rows))

        if not rows:
            return

        bucket_counts = {"green": 0, "grey": 0, "red": 0}
        errors = 0
        for i, (pid, lid, listing) in enumerate(rows, 1):
            if dry_run:
                logger.info("[dry] %s — %s", lid, (listing.title or "")[:60])
                continue
            try:
                bucket, reason = await analyze_listing_features(
                    session=session,
                    listing_id=lid,
                    profile_id=pid,
                    title=listing.title or "",
                    description=listing.description or "",
                    parameters=listing.parameters or {},
                )
                await session.execute(
                    update(ProfileListing)
                    .where(
                        ProfileListing.profile_id == pid,
                        ProfileListing.listing_id == lid,
                    )
                    .values(bucket=bucket)
                )
                await session.commit()
                bucket_counts[bucket] += 1
                if i % 25 == 0:
                    logger.info(
                        "[%d/%d] bucket=%s reason=%s — running totals %s",
                        i, len(rows), bucket, reason, bucket_counts,
                    )
            except Exception:
                errors += 1
                logger.exception("listing %s failed, skipping", lid)
                await session.rollback()

        logger.info(
            "done: %d listings → buckets %s, errors %d",
            len(rows), bucket_counts, errors,
        )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--profile", type=uuid.UUID, default=None,
                   help="restrict backfill to a single profile id")
    p.add_argument("--dry-run", action="store_true",
                   help="list listings without parsing")
    p.add_argument("--limit", type=int, default=None,
                   help="process at most N pairs (smoke runs)")
    a = p.parse_args()
    try:
        asyncio.run(run(a.profile, a.dry_run, a.limit))
    finally:
        asyncio.run(dispose_engine())


if __name__ == "__main__":
    main()

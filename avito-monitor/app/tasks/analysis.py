"""LLM stages of the worker pipeline — Phase 1 defect-features only.

Single task:

* :func:`evaluate_listing` — Phase 1 defect-features evaluation. Runs on
  every new listing; assigns a green/grey/red bucket via per-profile
  feature rules (parse → upsert → compute_bucket), writes
  ``profile_listings.processing_status`` and ``profile_listings.bucket``.

The V2 flag-based criteria pipeline (analyze_listing_features driven by
profile_criteria rows) was removed in Phase 2.1 (migration 0016).
The defect-features pipeline is now the single source of bucket assignment.
Phase 2.1 will extend it with price_signal + info_api kinds.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from random import uniform
from typing import Any

from sqlalchemy import select, update

from app.config import get_settings
from app.db.base import get_sessionmaker
from app.db.models import (
    Listing,
    Notification,
    ProfileListing,
    SearchProfile,
)
from app.db.models.enums import (
    ConditionClass,
    NotificationStatus,
    NotificationType,
    ProcessingStatus,
)
from app.integrations.avito_mcp_client.client import AvitoMcpClient
from app.integrations.openrouter import OpenRouterClient
from app.services.defect_features.pipeline import analyze_listing_features
from app.services.llm_budget import LLMBudgetExceeded, assert_budget
from app.tasks.broker import broker
from shared.models.avito import ListingDetail

log = logging.getLogger(__name__)


def _listing_to_detail(listing: Listing) -> ListingDetail:
    """Convert the DB row into the LLM-friendly Pydantic model."""
    images_raw: list[Any] = listing.images if isinstance(listing.images, list) else []
    images = []
    for idx, img in enumerate(images_raw):
        if isinstance(img, dict) and img.get("url"):
            images.append({"url": img["url"], "index": idx})
    return ListingDetail.model_validate(
        {
            "id": listing.avito_id,
            "title": listing.title or "",
            "price": float(listing.price) if listing.price is not None else None,
            "currency": listing.currency or "RUB",
            "region": listing.region,
            "url": listing.url,
            "description": listing.description,
            "parameters": listing.parameters or {},
            "images": images,
            "first_seen": (
                listing.first_seen_at.isoformat()
                if listing.first_seen_at is not None
                else None
            ),
            "seller_id": listing.seller_id,
            "seller_type": listing.seller_type,
        }
    )


@broker.task(task_name="app.tasks.analysis.evaluate_listing")
async def evaluate_listing(listing_id: str, profile_id: str) -> dict[str, Any]:
    """Phase 1 defect-features evaluation.

    V2 LLM grader was removed in Phase 2.1 (migration 0016). The defect-features
    pipeline (parse → upsert → compute_bucket) is now the single source of bucket
    assignment. Phase 2.1 will extend pipeline with price_signal + info_api kinds.
    """
    sessionmaker = get_sessionmaker()
    settings = get_settings()
    lid = uuid.UUID(listing_id)
    pid = uuid.UUID(profile_id)

    try:
        await assert_budget(
            sessionmaker, limit_usd=settings.openrouter_daily_usd_limit
        )
    except LLMBudgetExceeded as exc:
        log.warning(
            "analysis.evaluate.budget_exhausted spent=%.4f limit=%.4f",
            exc.spent_usd, exc.limit_usd,
        )
        async with sessionmaker() as session:
            profile = await session.get(SearchProfile, pid)
            session.add(_make_error_notification(
                profile_id=pid,
                listing_id=lid,
                code="llm_budget_exceeded",
                message=str(exc),
                profile=profile,
            ))
            await session.commit()
        return {"status": "skipped", "reason": "budget_exhausted"}

    async with sessionmaker() as session:
        listing = await session.get(Listing, lid)
        profile = await session.get(SearchProfile, pid)
        if listing is None or profile is None:
            log.warning(
                "analysis.evaluate.row_missing listing=%s profile=%s",
                listing_id, profile_id,
            )
            return {"status": "skipped", "reason": "row missing"}
        link = await session.get(ProfileListing, (pid, lid))
        in_alert = bool(link and link.in_alert_zone)

    detail = _listing_to_detail(listing)

    # Lazy detail fetch on first sight (same strategy as before — descriptions
    # / parameters needed for the LLM feature parser).
    if not (detail.description or "").strip():
        await asyncio.sleep(uniform(5.0, 15.0))
        try:
            async with AvitoMcpClient() as mcp:
                fresh = await mcp.get_listing(int(listing.avito_id))
        except Exception:
            log.exception(
                "analysis.evaluate.fetch_detail_failed listing=%s",
                listing_id,
            )
        else:
            detail = fresh
            async with sessionmaker() as session:
                await session.execute(
                    update(Listing)
                    .where(Listing.id == lid)
                    .values(
                        description=fresh.description,
                        parameters=fresh.parameters or {},
                        images=[
                            img.model_dump(mode="json")
                            for img in (fresh.images or [])
                        ] or None,
                    )
                )
                await session.commit()

    params_for_features = (
        detail.parameters
        if (detail and getattr(detail, "parameters", None))
        else (listing.parameters or {})
    )

    async with sessionmaker() as session:
        feat_bucket, feat_reason = await analyze_listing_features(
            session=session,
            listing_id=lid,
            profile_id=pid,
            title=listing.title or "",
            description=listing.description or "",
            parameters=params_for_features,
        )

        # Auto-reject on red if user hasn't acted.
        pl_action_result = await session.execute(
            select(ProfileListing.user_action)
            .where(
                ProfileListing.profile_id == pid,
                ProfileListing.listing_id == lid,
            )
        )
        current_user_action = pl_action_result.scalar_one_or_none()
        auto_reject = (
            feat_bucket == "red"
            and current_user_action in (None, "pending", "viewed")
        )

        new_status = (
            ProcessingStatus.NOTIFIED.value
            if feat_bucket == "green" and in_alert
            else ProcessingStatus.EVALUATED.value
        )
        pl_updates: dict[str, Any] = dict(
            processing_status=new_status,
            bucket=feat_bucket,
        )
        if auto_reject:
            pl_updates["user_action"] = "rejected"
            pl_updates["rejected_reason"] = f"auto:{feat_reason}"

        await session.execute(
            update(ProfileListing)
            .where(
                ProfileListing.profile_id == pid,
                ProfileListing.listing_id == lid,
            )
            .values(**pl_updates)
        )

        notif_count = 0
        if feat_bucket == "green" and in_alert:
            channels = profile.notification_channels or ["telegram"]
            raw_imgs = listing.images or []
            images: list[str] = []
            for it in raw_imgs[:10]:
                if isinstance(it, dict):
                    u = it.get("url")
                elif isinstance(it, str):
                    u = it
                else:
                    u = None
                if u:
                    images.append(u)

            payload_base = {
                "listing_id": str(lid),
                "avito_id": listing.avito_id,
                "title": listing.title,
                "price": float(listing.price) if listing.price is not None else None,
                "url": listing.url,
                "bucket": feat_bucket,
                "feat_reason": feat_reason,
                "images": images,
            }
            for channel in channels:
                session.add(
                    Notification(
                        user_id=profile.user_id,
                        profile_id=pid,
                        related_listing_id=lid,
                        type=NotificationType.NEW_LISTING.value,
                        channel=channel,
                        payload=payload_base,
                        status=NotificationStatus.PENDING.value,
                    )
                )
                notif_count += 1

        await session.commit()

    log.info(
        "analysis.evaluate.success listing=%s bucket=%s reason=%s notifs=%d",
        listing_id, feat_bucket, feat_reason, notif_count,
    )
    return {
        "status": "success",
        "bucket": feat_bucket,
        "feat_reason": feat_reason,
        "in_alert_zone": in_alert,
        "notifications_created": notif_count,
    }


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _make_error_notification(
    *,
    profile_id: uuid.UUID,
    listing_id: uuid.UUID | None,
    code: str,
    message: str,
    profile: SearchProfile | None,
) -> Notification:
    return Notification(
        user_id=profile.user_id if profile is not None else uuid.uuid4(),
        profile_id=profile_id,
        related_listing_id=listing_id,
        type=NotificationType.ERROR.value,
        channel="telegram",
        payload={"code": code, "message": message[:500]},
        status=NotificationStatus.PENDING.value,
    )


# ----------------------------------------------------------------------
# refresh_listing_detail — no-LLM detail re-fetch (reservation tracking)
# ----------------------------------------------------------------------

@broker.task(task_name="app.tasks.analysis.refresh_listing_detail")
async def refresh_listing_detail(listing_id: str) -> dict[str, Any]:
    """Pull the latest detail payload for a listing and refresh DB fields.

    Triggered by polling when ``reservation_status`` flips. Updates
    ``description``, ``parameters`` and the reservation triplet
    (``reservation_status``, ``reservation_changed_at``,
    ``reserved_at_price``) when the detail-side status differs from what
    polling already persisted. Does NOT call the LLM — reservation events
    are cheap signals, not classifications.
    """
    from datetime import datetime, timezone

    from app.db.models import ListingStatusEvent

    sessionmaker = get_sessionmaker()
    lid = uuid.UUID(listing_id)

    async with sessionmaker() as session:
        listing = await session.get(Listing, lid)
        if listing is None:
            log.warning("analysis.refresh_detail.row_missing listing=%s", listing_id)
            return {"status": "skipped", "reason": "row missing"}
        avito_id = int(listing.avito_id)
        prev_reservation = listing.reservation_status

    try:
        async with AvitoMcpClient() as mcp:
            fresh = await mcp.get_listing(avito_id)
    except Exception:
        log.exception(
            "analysis.refresh_detail.fetch_failed listing=%s", listing_id
        )
        return {"status": "failed", "reason": "fetch_failed"}

    detail_reservation = getattr(fresh, "reservation_status", None)
    now = datetime.now(timezone.utc)

    async with sessionmaker() as session:
        updates: dict[str, Any] = {
            "description": fresh.description,
            "parameters": fresh.parameters or {},
            # Detail endpoint carries the full gallery; search feed only
            # had the cover. Persist all so the lightbox shows them.
            "images": [
                img.model_dump(mode="json")
                for img in (fresh.images or [])
            ] or None,
        }
        reservation_updated = False
        if (
            detail_reservation is not None
            and detail_reservation != prev_reservation
        ):
            updates["reservation_status"] = detail_reservation
            updates["reservation_changed_at"] = now
            session.add(
                ListingStatusEvent(
                    listing_id=lid,
                    event_type="status_change",
                    old_value=prev_reservation,
                    new_value=detail_reservation,
                    at=now,
                )
            )
            if detail_reservation == "reserved":
                # Detail is the more authoritative source for the snapshot
                # (search card may lag by a refresh); prefer its price.
                captured_price = fresh.price
                updates["reserved_at_price"] = captured_price
                session.add(
                    ListingStatusEvent(
                        listing_id=lid,
                        event_type="reservation_capture",
                        old_value=None,
                        new_value=(
                            str(captured_price)
                            if captured_price is not None
                            else None
                        ),
                        at=now,
                    )
                )
            reservation_updated = True

        await session.execute(
            update(Listing).where(Listing.id == lid).values(**updates)
        )
        await session.commit()

    log.info(
        "analysis.refresh_detail.success listing=%s reservation_updated=%s",
        listing_id, reservation_updated,
    )
    return {
        "status": "success",
        "reservation_updated": reservation_updated,
        "reservation_status": detail_reservation,
    }

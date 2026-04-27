"""LLM stages of the worker pipeline (Block 4.2).

Two cooperating tasks:

* :func:`analyze_listing` — stage-1 cheap classifier (ADR-010). Runs
  on every new listing; writes ``condition_class`` to ``listings``,
  flips ``profile_listings.processing_status`` to either
  ``pending_match`` (if the lot fits the profile's allowed conditions
  AND sits in the alert price band) or ``market_data`` otherwise.

* :func:`match_listing` — stage-2 heavyweight match. Only enqueued by
  :func:`analyze_listing` for the lots that survived stage 1.
  Produces a ``new_listing`` Notification (one per channel from
  ``profile.notification_channels``) when the score meets the
  per-profile threshold; otherwise marks the lot as ``analyzed`` and
  goes silent.

Both tasks are budget-aware. Before calling OpenRouter we check the
rolling 24h spend via :mod:`app.services.llm_budget`. When the budget
is exhausted ``classify`` is hard-stopped (stage-1 is the bulk of
spend), while ``match`` lets in-flight jobs finish so the user still
gets the value of the spend already paid for.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import update

from app.config import get_settings
from app.db.base import get_sessionmaker
from app.db.models import Listing, Notification, ProfileListing, SearchProfile
from app.db.models.enums import (
    ConditionClass,
    NotificationStatus,
    NotificationType,
    ProcessingStatus,
)
from app.integrations.avito_mcp_client.client import AvitoMcpClient
from app.integrations.openrouter import OpenRouterClient
from app.services.llm_analyzer import LLMAnalyzer
from app.services.llm_budget import LLMBudgetExceeded, assert_budget
from app.services.llm_cache import DBLLMCache
from app.tasks.broker import broker
from shared.models.avito import ListingDetail

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# Wiring
# ----------------------------------------------------------------------

def _build_analyzer() -> LLMAnalyzer:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is empty — cannot run LLM analysis"
        )
    openrouter = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        app_base_url=settings.app_base_url,
        app_title="Avito Monitor",
    )
    cache = DBLLMCache(get_sessionmaker())
    return LLMAnalyzer(
        openrouter=openrouter,
        cache=cache,
        default_text_model=settings.openrouter_default_text_model,
        default_vision_model=settings.openrouter_default_vision_model,
    )


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


def _min_confidence_threshold(profile: SearchProfile) -> int:
    """Pull the per-profile match threshold from notification_settings.

    Default is 70 (matches MatchResult.score scale: 70+ = matches).
    """
    settings = profile.notification_settings or {}
    raw = settings.get("min_confidence_threshold", 70)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 70


async def _ensure_match_enabled(profile: SearchProfile) -> bool:
    """Stage-2 match runs only when the profile has criteria text."""
    return bool(profile.custom_criteria and profile.custom_criteria.strip())


# ----------------------------------------------------------------------
# analyze_listing — stage 1
# ----------------------------------------------------------------------

@broker.task(task_name="app.tasks.analysis.analyze_listing")
async def analyze_listing(listing_id: str, profile_id: str) -> dict[str, Any]:
    """Stage-1 LLM classify; routes the lot to stage-2 or market-data."""
    sessionmaker = get_sessionmaker()
    settings = get_settings()
    lid = uuid.UUID(listing_id)
    pid = uuid.UUID(profile_id)

    # Budget gate — cheap, in-DB. Stage-1 is the bulk of spend so we
    # hard-stop here when the day's budget is gone.
    try:
        await assert_budget(
            sessionmaker, limit_usd=settings.openrouter_daily_usd_limit
        )
    except LLMBudgetExceeded as exc:
        log.warning(
            "analysis.classify.budget_exhausted spent=%.4f limit=%.4f",
            exc.spent_usd, exc.limit_usd,
        )
        async with sessionmaker() as session:
            session.add(_make_error_notification(
                profile_id=pid,
                listing_id=lid,
                code="llm_budget_exceeded",
                message=str(exc),
                profile=await session.get(SearchProfile, pid),
            ))
            await session.commit()
        return {"status": "skipped", "reason": "budget_exhausted"}

    async with sessionmaker() as session:
        listing = await session.get(Listing, lid)
        profile = await session.get(SearchProfile, pid)
        if listing is None or profile is None:
            log.warning(
                "analysis.classify.row_missing listing=%s profile=%s",
                listing_id, profile_id,
            )
            return {"status": "skipped", "reason": "row missing"}

        link = await session.get(ProfileListing, (pid, lid))
        in_alert = bool(link and link.in_alert_zone)

    detail = _listing_to_detail(listing)

    # The polling step only persists what's in the search results — title,
    # price, region, images. The actual ad description and parameters live
    # on the per-item detail page, so we fetch it here on the first
    # classify (when description is empty) and write it back to the row
    # so subsequent ops (match, compare-to-reference) and the listing
    # detail view see the full text.
    if not (detail.description or "").strip():
        try:
            async with AvitoMcpClient() as mcp:
                fresh = await mcp.get_listing(int(listing.avito_id))
        except Exception:
            log.exception(
                "analysis.fetch_detail_failed listing=%s avito_id=%s",
                listing_id, listing.avito_id,
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
                    )
                )
                await session.commit()

    analyzer = _build_analyzer()
    classification = await analyzer.classify_condition(
        detail, model=profile.llm_classify_model or None
    )

    fits_condition = classification.condition_class.value in (
        profile.allowed_conditions or []
    )
    enqueue_match = fits_condition and in_alert and await _ensure_match_enabled(profile)

    async with sessionmaker() as session:
        # 1) Persist condition fields on the listing.
        await session.execute(
            update(Listing)
            .where(Listing.id == lid)
            .values(
                condition_class=classification.condition_class.value,
                condition_confidence=classification.confidence,
                condition_reasoning=classification.reasoning,
            )
        )

        # 2) Move the link forward.
        new_status = (
            ProcessingStatus.PENDING_MATCH.value
            if enqueue_match
            else ProcessingStatus.MARKET_DATA.value
            if (not fits_condition or not in_alert)
            else ProcessingStatus.CLASSIFIED.value
        )
        await session.execute(
            update(ProfileListing)
            .where(
                ProfileListing.profile_id == pid,
                ProfileListing.listing_id == lid,
            )
            .values(processing_status=new_status)
        )
        await session.commit()

    if enqueue_match:
        await match_listing.kiq(str(lid), str(pid))

    log.info(
        "analysis.classify.success listing=%s class=%s in_alert=%s match_enqueued=%s",
        listing_id, classification.condition_class.value, in_alert, enqueue_match,
    )
    return {
        "status": "success",
        "condition_class": classification.condition_class.value,
        "confidence": classification.confidence,
        "in_alert_zone": in_alert,
        "match_enqueued": enqueue_match,
    }


# ----------------------------------------------------------------------
# match_listing — stage 2
# ----------------------------------------------------------------------

@broker.task(task_name="app.tasks.analysis.match_listing")
async def match_listing(listing_id: str, profile_id: str) -> dict[str, Any]:
    """Stage-2 LLM match; emits a ``new_listing`` notification on hit."""
    sessionmaker = get_sessionmaker()
    settings = get_settings()
    lid = uuid.UUID(listing_id)
    pid = uuid.UUID(profile_id)

    # Stage-2 budget gate is intentionally softer than stage-1: by the
    # time a job reaches us we've already paid for stage-1, so finishing
    # the match is usually worth it. Only refuse if budget is *grossly*
    # blown (>1.5× limit) — that's the same "let in-flight finish"
    # behaviour the TZ describes.
    try:
        await assert_budget(
            sessionmaker,
            limit_usd=settings.openrouter_daily_usd_limit * 1.5,
        )
    except LLMBudgetExceeded as exc:
        log.warning(
            "analysis.match.budget_exhausted spent=%.4f limit=%.4f",
            exc.spent_usd, exc.limit_usd,
        )
        return {"status": "skipped", "reason": "budget_exhausted"}

    async with sessionmaker() as session:
        listing = await session.get(Listing, lid)
        profile = await session.get(SearchProfile, pid)
        if listing is None or profile is None:
            return {"status": "skipped", "reason": "row missing"}

    detail = _listing_to_detail(listing)
    analyzer = _build_analyzer()
    match_res = await analyzer.match_criteria(
        detail,
        criteria=profile.custom_criteria or "",
        allowed_conditions=list(profile.allowed_conditions or []),
        condition_class=listing.condition_class,
        model=profile.llm_match_model or None,
    )

    threshold = _min_confidence_threshold(profile)
    is_hit = match_res.matches and match_res.score >= threshold

    async with sessionmaker() as session:
        new_status = (
            ProcessingStatus.NOTIFIED.value
            if is_hit
            else ProcessingStatus.ANALYZED.value
        )
        await session.execute(
            update(ProfileListing)
            .where(
                ProfileListing.profile_id == pid,
                ProfileListing.listing_id == lid,
            )
            .values(processing_status=new_status)
        )

        notif_count = 0
        if is_hit:
            channels = profile.notification_channels or ["telegram"]
            for channel in channels:
                payload = {
                    "listing_id": str(lid),
                    "avito_id": listing.avito_id,
                    "title": listing.title,
                    "price": float(listing.price) if listing.price is not None else None,
                    "url": listing.url,
                    "score": match_res.score,
                    "key_pros": match_res.key_pros,
                    "key_cons": match_res.key_cons,
                    "reasoning": match_res.reasoning,
                    "condition_class": listing.condition_class,
                }
                session.add(
                    Notification(
                        user_id=profile.user_id,
                        profile_id=pid,
                        related_listing_id=lid,
                        type=NotificationType.NEW_LISTING.value,
                        channel=channel,
                        payload=payload,
                        status=NotificationStatus.PENDING.value,
                    )
                )
                notif_count += 1

        await session.commit()

    log.info(
        "analysis.match.done listing=%s matches=%s score=%d hit=%s notifs=%d",
        listing_id, match_res.matches, match_res.score, is_hit, notif_count,
    )
    return {
        "status": "success",
        "matches": match_res.matches,
        "score": match_res.score,
        "is_hit": is_hit,
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

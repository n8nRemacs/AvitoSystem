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

from sqlalchemy import select, text, update

from app.config import get_settings
from app.db.base import get_sessionmaker
from app.db.models import (
    CriteriaTemplate,
    Listing,
    Notification,
    ProfileCriterion,
    ProfileListing,
    ProfileListingEvaluation,
    SearchProfile,
)
from app.db.models.enums import (
    ConditionClass,
    CriteriaTemplateKind,
    EvaluateStrategy,
    EvaluationBucket,
    NotificationStatus,
    NotificationType,
    ProcessingStatus,
)
from app.integrations.avito_mcp_client.client import AvitoMcpClient
from app.integrations.openrouter import OpenRouterClient
from app.services.llm_analyzer import (
    CriterionSpec,
    InfoFieldSpec,
    LLMAnalyzer,
)
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
                # Pull up to 10 image URLs (Telegram media-group limit) so
                # the messenger provider can attach them to the alert. Tolerate
                # both shapes seen in the wild: list of dicts ``{"url": ...}``
                # and list of bare strings.
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
                    "images": images,
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
# evaluate_listing — V2 single-stage flag-based pipeline
# ----------------------------------------------------------------------

# Map a red-flagged criterion key back to a legacy ConditionClass enum
# value, so listings.condition_class stays populated for the legacy
# clean-metrics filter (compute_market_stats) until Phase C drops it.
_CRITERION_TO_CONDITION = {
    "icloud_locked": ConditionClass.BLOCKED_ICLOUD,
    "account_blocked": ConditionClass.BLOCKED_ACCOUNT,
    "not_starting": ConditionClass.NOT_STARTING,
    "screen_broken": ConditionClass.BROKEN_SCREEN,
    "parts_only": ConditionClass.PARTS_ONLY,
}


async def _load_profile_specs(
    sessionmaker, profile_id: uuid.UUID
) -> tuple[list[CriterionSpec], list[InfoFieldSpec], list[tuple[str, str]]]:
    """Build (criterion specs, info_llm specs, info_api[(key, path)]) for a profile.

    Reads profile_criteria + criteria_templates with one round-trip per
    profile (small table, single user, fine without ORM relationships).
    """
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(ProfileCriterion, CriteriaTemplate)
                .join(
                    CriteriaTemplate,
                    ProfileCriterion.template_id == CriteriaTemplate.id,
                    isouter=True,
                )
                .where(ProfileCriterion.profile_id == profile_id)
                .order_by(ProfileCriterion.sort_order)
            )
        ).all()

    criteria: list[CriterionSpec] = []
    info_llm: list[InfoFieldSpec] = []
    info_api: list[tuple[str, str]] = []

    for pc, tpl in rows:
        if tpl is not None:
            kind = tpl.kind
            key = tpl.key
            title = tpl.title_ru
            fragment = tpl.prompt_fragment or ""
            version = tpl.version or 1
            api_path = tpl.api_path
        else:
            kind = pc.custom_kind or "criterion"
            key = pc.custom_key or "custom"
            title = pc.custom_title_ru or key
            fragment = pc.custom_prompt_fragment or ""
            version = 1
            api_path = None

        if kind == CriteriaTemplateKind.CRITERION.value:
            criteria.append(
                CriterionSpec(
                    key=key,
                    title_ru=title,
                    prompt_fragment=fragment,
                    version=version,
                    params=pc.params,
                )
            )
        elif kind == CriteriaTemplateKind.INFO_LLM.value:
            info_llm.append(
                InfoFieldSpec(
                    key=key,
                    title_ru=title,
                    prompt_fragment=fragment,
                    version=version,
                )
            )
        elif kind == CriteriaTemplateKind.INFO_API.value and api_path:
            info_api.append((key, api_path))

    return criteria, info_llm, info_api


def _resolve_info_api(
    parameters: dict[str, Any] | None, paths: list[tuple[str, str]]
) -> dict[str, Any]:
    """Pull info_api values out of listing.parameters with no LLM cost.

    ``api_path`` is a flat key into the parameters dict for now —
    Avito's mobile API exposes the relevant fields as a single-level
    map (``Встроенная память``, ``Цвет``, etc.). Nested path support
    can be added later if a future template needs it.
    """
    if not parameters:
        return {}
    out: dict[str, Any] = {}
    for key, path in paths:
        val = parameters.get(path)
        if val is not None:
            out[key] = val
    return out


def _derive_condition_class(
    bucket: str, criteria_flags: dict[str, dict[str, Any]]
) -> str:
    """Map a v2 evaluation back to a legacy ConditionClass enum value.

    Keeps ``listings.condition_class`` meaningful for compute_market_stats
    on profiles that haven't migrated yet (Phase B). Once Phase C drops
    the column, this helper goes away.
    """
    for key, cls in _CRITERION_TO_CONDITION.items():
        flag = criteria_flags.get(key) or {}
        if flag.get("flag") == "red":
            return cls.value
    if bucket == "green":
        return ConditionClass.WORKING.value
    if bucket == "red":
        # red but not from a mappable enum — likely FRP / custom — call it broken_other.
        return ConditionClass.BROKEN_OTHER.value
    return ConditionClass.UNKNOWN.value


@broker.task(task_name="app.tasks.analysis.evaluate_listing")
async def evaluate_listing(listing_id: str, profile_id: str) -> dict[str, Any]:
    """V2 single-stage evaluation. Replaces analyze_listing + match_listing."""
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
                "analysis.evaluate.row_missing listing=%s profile=%s",
                listing_id, profile_id,
            )
            return {"status": "skipped", "reason": "row missing"}
        link = await session.get(ProfileListing, (pid, lid))
        in_alert = bool(link and link.in_alert_zone)
        threshold = float(profile.confidence_threshold or 0.7)
        strategy = profile.evaluate_strategy or EvaluateStrategy.PER_LISTING.value

    detail = _listing_to_detail(listing)

    # Fetch the full listing detail on first sight (same lazy strategy
    # as analyze_listing) so descriptions / parameters are available.
    if not (detail.description or "").strip():
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
                    )
                )
                await session.commit()

    criteria_specs, info_llm_specs, info_api_paths = await _load_profile_specs(
        sessionmaker, pid
    )
    info_api_values = _resolve_info_api(detail.parameters, info_api_paths)

    analyzer = _build_analyzer()
    eval_result = await analyzer.evaluate_listing(
        detail,
        criteria=criteria_specs,
        info_llm_fields=info_llm_specs,
        info_api_values=info_api_values,
        strategy=strategy,
        confidence_threshold=threshold,
    )

    # Persist evaluation row + denormalised bucket on profile_listings,
    # plus a derived condition_class on listings (legacy compatibility).
    criteria_dump = {
        k: v.model_dump(mode="json") for k, v in eval_result.criteria.items()
    }
    info_dump = {
        k: v.model_dump(mode="json") for k, v in eval_result.info.items()
    }
    derived_condition = _derive_condition_class(eval_result.bucket, criteria_dump)

    async with sessionmaker() as session:
        evaluation = ProfileListingEvaluation(
            profile_id=pid,
            listing_id=lid,
            bucket=eval_result.bucket,
            confidence_threshold=threshold,
            criteria_flags=criteria_dump,
            info_fields=info_dump,
            red_criterion_keys=list(eval_result.red_criterion_keys),
            criteria_set_hash=profile.criteria_set_hash or "",
        )
        session.add(evaluation)
        await session.flush()

        await session.execute(
            update(Listing)
            .where(Listing.id == lid)
            .values(condition_class=derived_condition)
        )

        new_status = (
            ProcessingStatus.NOTIFIED.value
            if eval_result.bucket == "green" and in_alert
            else ProcessingStatus.EVALUATED.value
        )
        await session.execute(
            update(ProfileListing)
            .where(
                ProfileListing.profile_id == pid,
                ProfileListing.listing_id == lid,
            )
            .values(
                processing_status=new_status,
                bucket=eval_result.bucket,
                latest_evaluation_id=evaluation.id,
            )
        )

        notif_count = 0
        if eval_result.bucket == EvaluationBucket.RED.value and eval_result.red_criterion_keys:
            # Auto-blacklist (ADR-011 reuse). ON CONFLICT DO NOTHING so a
            # prior manual reject is preserved as the canonical reason.
            await session.execute(
                text(
                    """
                    INSERT INTO user_listing_blacklist
                        (user_id, listing_id, reason, created_at)
                    VALUES (:user_id, :listing_id, :reason, NOW())
                    ON CONFLICT (user_id, listing_id) DO NOTHING
                    """
                ),
                {
                    "user_id": profile.user_id,
                    "listing_id": lid,
                    "reason": f"auto_red:{eval_result.red_criterion_keys[0]}",
                },
            )
        elif eval_result.bucket == EvaluationBucket.GREEN.value and in_alert:
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
                "bucket": eval_result.bucket,
                "criteria_flags": criteria_dump,
                "info_fields": info_dump,
                "condition_class": derived_condition,
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
        "analysis.evaluate.success listing=%s bucket=%s strategy=%s reds=%s notifs=%d",
        listing_id, eval_result.bucket, strategy,
        eval_result.red_criterion_keys, notif_count,
    )
    return {
        "status": "success",
        "bucket": eval_result.bucket,
        "red_criterion_keys": list(eval_result.red_criterion_keys),
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

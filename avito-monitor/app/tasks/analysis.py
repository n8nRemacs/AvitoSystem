"""LLM stages of the worker pipeline (Block 4.2) — V2 pipeline only.

Single task:

* :func:`evaluate_listing` — V2 flag-based evaluator. Runs on every
  new listing; assigns a green/grey/red bucket via per-profile criteria
  flags, writes ``condition_class`` (legacy compatibility) and
  ``profile_listings.processing_status``.

The legacy ADR-010 two-stage pipeline (analyze_listing + match_listing)
was removed in Phase C (migration 0009_drop_legacy_v2_artifacts). All
profiles must use profile_criteria rows instead of custom_criteria text.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from random import uniform
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
# API killer rules — pure-Python verdicts straight from listing.parameters.
# Avito-side structured fields ("Работа устройства" = "Не включается", etc.)
# are ground truth — no need to spend an LLM call to confirm. When any rule
# matches we skip the LLM entirely and write a red evaluation outright.
# ----------------------------------------------------------------------

# Sensors that are NOT a deal-breaker. Anything else listed under
# "Не работают датчики" is treated as red:
#   Wi-Fi / Bluetooth / Compass — motherboard-level, kills resale value
#   Face ID / Touch ID         — affects everyday use, kills resale value
# The proximity sensor ("Приближения к уху") is the lone exception per
# user feedback 2026-05-10 — most buyers don't notice it.
_API_SAFE_SENSORS = {
    "приближения к уху",
    "приближение к уху",
}


def _normalise_sensor_token(s: str) -> str:
    return s.strip().lower()


def check_api_killers(parameters: dict | None) -> list[tuple[str, str]]:
    """Inspect Avito-side parameters for unambiguous deal-breakers.

    Returns a list of ``(criterion_key, reasoning)`` tuples. An empty list
    means no killer fired and the LLM should run as usual.

    Rules (per user feedback 2026-05-10):
      Работа устройства  ∋ "Не включается" or "Не работает сенсор"  → red
      Аккумулятор        ∋ "Не заряжается"                          → red
      Не работают функции ≠ ""                                       → red
      Не работают датчики has any non-safe sensor                   → red
        (safe = только "Приближения к уху")
    """
    if not parameters:
        return []

    matches: list[tuple[str, str]] = []

    work_state = str(parameters.get("Работа устройства") or "")
    if "не включается" in work_state.lower():
        matches.append((
            "api:device_not_starting",
            f"Avito-параметр «Работа устройства» = «{work_state}» (не включается)",
        ))
    elif "не работает сенсор" in work_state.lower():
        matches.append((
            "api:motherboard_sensor_dead",
            f"Avito-параметр «Работа устройства» = «{work_state}» (датчик платы)",
        ))

    battery_state = str(parameters.get("Аккумулятор") or "")
    if "не заряжается" in battery_state.lower():
        matches.append((
            "api:battery_dead",
            f"Avito-параметр «Аккумулятор» = «{battery_state}»",
        ))

    broken_functions = str(parameters.get("Не работают функции") or "").strip()
    if broken_functions:
        matches.append((
            "api:functions_broken",
            f"Avito-параметр «Не работают функции» = «{broken_functions}»",
        ))

    broken_sensors = str(parameters.get("Не работают датчики") or "").strip()
    if broken_sensors:
        # CSV-like: split on common separators and check each token.
        tokens = [t for t in broken_sensors.replace(";", ",").split(",") if t.strip()]
        unsafe = [t.strip() for t in tokens if _normalise_sensor_token(t) not in _API_SAFE_SENSORS]
        if unsafe:
            matches.append((
                "api:critical_sensors_broken",
                f"Avito-параметр «Не работают датчики» включает критичные: {', '.join(unsafe)}",
            ))

    # Камера: red ТОЛЬКО если явно "Не работает <что-то>". Визуальные
    # дефекты (потёртости/пятна/трещины линзы) сами по себе НЕ киллер —
    # их LLM посмотрит как часть общей картины.
    camera_state = str(parameters.get("Камера") or "").strip()
    if camera_state and "не работает" in camera_state.lower():
        matches.append((
            "api:camera_broken",
            f"Avito-параметр «Камера» = «{camera_state}» (не работает)",
        ))

    return matches


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
        # Humanization: pace detail fetches like a buyer who scans the
        # search page, then opens an interesting card every few seconds.
        # Combined with serial-ish task scheduling this keeps Avito from
        # spotting the analysis fan-out as a burst of ~500 detail hits.
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
                    )
                )
                await session.commit()

    criteria_specs, info_llm_specs, info_api_paths = await _load_profile_specs(
        sessionmaker, pid
    )
    info_api_values = _resolve_info_api(detail.parameters, info_api_paths)

    # ── API killer pre-check ─────────────────────────────────────────────
    # Before paying the LLM round-trip, see if Avito's structured params
    # already make this listing a clear red. If yes, skip the analyzer and
    # write a synthetic evaluation right here. Saves cost + time, and the
    # api criterion shows up in the UI with the rule that fired.
    api_killers = check_api_killers(detail.parameters)
    if api_killers:
        log.info(
            "analysis.evaluate.api_killer listing=%s killers=%s",
            listing_id, [k[0] for k in api_killers],
        )
        criteria_dump = {
            ckey: {"flag": "red", "confidence": 1.0, "reasoning": reasoning}
            for ckey, reasoning in api_killers
        }
        red_keys = [ckey for ckey, _ in api_killers]

        async with sessionmaker() as session:
            evaluation = ProfileListingEvaluation(
                profile_id=pid,
                listing_id=lid,
                bucket=EvaluationBucket.RED.value,
                confidence_threshold=threshold,
                criteria_flags=criteria_dump,
                info_fields={},
                red_criterion_keys=red_keys,
                # Same hash as a normal LLM evaluation so a profile criteria
                # change still triggers re-evaluation. The api: prefix on
                # criteria_flags keys is the distinguisher — column is
                # VARCHAR(64), no room for a custom suffix.
                criteria_set_hash=profile.criteria_set_hash or "",
            )
            session.add(evaluation)
            await session.flush()
            await session.execute(
                update(Listing)
                .where(Listing.id == lid)
                .values(condition_class=ConditionClass.BROKEN.value)
            )
            await session.execute(
                update(ProfileListing)
                .where(
                    ProfileListing.profile_id == pid,
                    ProfileListing.listing_id == lid,
                )
                .values(
                    processing_status=ProcessingStatus.EVALUATED.value,
                    bucket=EvaluationBucket.RED.value,
                    latest_evaluation_id=evaluation.id,
                )
            )
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
                    "reason": f"auto_red:{red_keys[0]}",
                },
            )
            await session.commit()
        return {
            "status": "success",
            "skipped_llm": True,
            "killers": red_keys,
            "bucket": "red",
        }

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

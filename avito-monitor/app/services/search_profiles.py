"""SearchProfile CRUD + business logic (URL parse, dual range, overlay)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProfileRun, SearchProfile
from app.db.models.enums import ProfileRunStatus
from app.schemas.search_profile import (
    ParsedUrlPreview,
    SearchProfileCreate,
    SearchProfileUpdate,
)
from app.services.url_parser import (
    apply_overlay,
    compute_search_range,
    parse_avito_url,
)


def preview_url(url: str) -> ParsedUrlPreview:
    """Parse URL and produce a preview for the create form (HTMX endpoint)."""
    parsed = parse_avito_url(url)
    s_min, s_max = compute_search_range(parsed.pmin, parsed.pmax)
    return ParsedUrlPreview(
        region_slug=parsed.region_slug,
        region_name=parsed.region_name,
        category_human=parsed.category_human,
        brand=parsed.brand,
        model=parsed.model,
        query=parsed.query,
        pmin=parsed.pmin,
        pmax=parsed.pmax,
        sort=parsed.sort,
        only_with_delivery=parsed.only_with_delivery,
        suggested_name=parsed.display_name(),
        suggested_search_min=s_min,
        suggested_search_max=s_max,
    )


def _fill_from_url(profile: SearchProfile, *, only_when_empty: bool = True) -> None:
    """Run URL parser and populate denormalised fields + auto-set defaults."""
    try:
        p = parse_avito_url(profile.avito_search_url)
    except ValueError:
        return

    def _maybe_set(field: str, value):
        current = getattr(profile, field)
        if value is None:
            return
        if not only_when_empty or current in (None, "", []):
            setattr(profile, field, value)

    _maybe_set("parsed_brand", p.brand)
    _maybe_set("parsed_model", p.model)
    _maybe_set("parsed_category", p.category_human)
    _maybe_set("region_slug", p.region_slug)
    if profile.alert_min_price is None and p.pmin is not None:
        profile.alert_min_price = p.pmin
    if profile.alert_max_price is None and p.pmax is not None:
        profile.alert_max_price = p.pmax
    if profile.sort is None and p.sort is not None:
        profile.sort = p.sort

    # Auto-derive search-вилка from alert-вилка if not provided
    if (profile.search_min_price is None and profile.alert_min_price is not None
            and profile.search_max_price is None and profile.alert_max_price is not None):
        s_min, s_max = compute_search_range(
            profile.alert_min_price, profile.alert_max_price
        )
        profile.search_min_price = s_min
        profile.search_max_price = s_max


async def list_profiles(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    include_archived: bool = False,
) -> list[SearchProfile]:
    stmt = (
        select(SearchProfile)
        .where(SearchProfile.user_id == user_id)
        .order_by(SearchProfile.created_at.desc())
    )
    if not include_archived:
        stmt = stmt.where(SearchProfile.archived_at.is_(None))
    return list((await session.execute(stmt)).scalars().all())


async def list_archived_profiles(
    session: AsyncSession, user_id: uuid.UUID
) -> list[SearchProfile]:
    stmt = (
        select(SearchProfile)
        .where(
            SearchProfile.user_id == user_id,
            SearchProfile.archived_at.is_not(None),
        )
        .order_by(SearchProfile.archived_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_profile(
    session: AsyncSession, user_id: uuid.UUID, profile_id: uuid.UUID
) -> SearchProfile | None:
    stmt = select(SearchProfile).where(
        SearchProfile.id == profile_id,
        SearchProfile.user_id == user_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_profile(
    session: AsyncSession, user_id: uuid.UUID, data: SearchProfileCreate
) -> SearchProfile:
    profile = SearchProfile(
        user_id=user_id,
        **data.model_dump(),
    )
    _fill_from_url(profile, only_when_empty=True)
    session.add(profile)
    await session.flush()
    return profile


async def update_profile(
    session: AsyncSession,
    profile: SearchProfile,
    data: SearchProfileUpdate,
) -> SearchProfile:
    payload = data.model_dump(exclude_unset=True)
    url_changed = "avito_search_url" in payload
    for k, v in payload.items():
        setattr(profile, k, v)
    if url_changed:
        # Only refresh denormalisation if URL changed; don't override user-edits
        _fill_from_url(profile, only_when_empty=False)
    await session.flush()
    return profile


async def delete_profile(
    session: AsyncSession, profile: SearchProfile
) -> None:
    await session.delete(profile)
    await session.flush()


async def toggle_profile(
    session: AsyncSession, profile: SearchProfile
) -> SearchProfile:
    profile.is_active = not profile.is_active
    await session.flush()
    return profile


async def schedule_run_now(
    session: AsyncSession, profile: SearchProfile
) -> ProfileRun:
    """Enqueue an immediate poll_profile run via TaskIQ.

    Returns a marker ``ProfileRun`` row so the UI has something to render
    while the worker picks up the task. The worker creates its own
    authoritative ``ProfileRun`` row keyed by its actual ``started_at``;
    these two coexist in ``profile_runs`` (this one as a manual trigger
    record, the worker's as the real execution).
    """
    from app.tasks.polling import poll_profile

    run = ProfileRun(
        profile_id=profile.id,
        started_at=datetime.now(tz=timezone.utc),
        status=ProfileRunStatus.RUNNING.value,
        error_message=None,
    )
    session.add(run)
    await session.flush()
    await poll_profile.kiq(str(profile.id))
    return run


async def list_runs(
    session: AsyncSession, profile_id: uuid.UUID, limit: int = 50
) -> list[ProfileRun]:
    stmt = (
        select(ProfileRun)
        .where(ProfileRun.profile_id == profile_id)
        .order_by(ProfileRun.started_at.desc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


def build_polling_url(profile: SearchProfile) -> str:
    """Apply overlay parameters to the base URL — used by worker (Block 4)."""
    return apply_overlay(
        profile.avito_search_url,
        region_slug=profile.region_slug,
        search_min_price=profile.search_min_price,
        search_max_price=profile.search_max_price,
        only_with_delivery=profile.only_with_delivery,
        sort=profile.sort,
    )

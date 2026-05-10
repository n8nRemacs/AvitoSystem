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

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

# Word-boundary tokeniser for post-filter title matching. \w+ матчит alnum
# и Unicode-буквы (re.UNICODE по умолчанию в Python 3) — кириллица входит.
# Ловит "iPhone 12 Pro Max, 128 ГБ" → ["iphone","12","pro","max","128","гб"],
# что предотвращает substring-false-positive «"12" in "128"».
_WORD_RE = re.compile(r"\w+", re.UNICODE)

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.base import get_sessionmaker
from app.db.models import (
    Listing,
    ProfileCriterion,
    ProfileListing,
    ProfileRun,
    SearchProfile,
    UserListingBlacklist,
)
from app.db.models.enums import ListingStatus, ProfileRunStatus
from app.integrations.avito_mcp_client.client import AvitoMcpClient
from app.services.account_pool import AccountPool, NoAvailableAccountError
from app.services.account_pool_factory import get_account_pool
from app.services.search_profiles import build_polling_url
from app.tasks.broker import broker
from avito_mcp.integrations.xapi_client import XapiError
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


async def fetch_with_pool(
    *,
    fetcher_fn,
    pool: AccountPool,
    max_attempts: int = 2,
    required_owner: str | None = None,
):
    """Wraps fetcher_fn(account_claim) → result, with retry on 403/401/5xx.

    fetcher_fn receives the account claim dict and returns the fetch result,
    or raises XapiError on HTTP errors.

    Returns None if the pool is fully drained (NoAvailableAccountError on the
    very first claim attempt).  Re-raises the last XapiError once max_attempts
    are exhausted.

    After every attempt (success or failure) pool.report() is called so the
    xapi account state machine stays up to date.

    required_owner: if set, all claims are pinned to that account_id and
    effective_attempts is forced to 1 — wrong Avito user can never fetch the
    autosearch subscription regardless of which token is tried.
    """
    effective_attempts = 1 if required_owner else max_attempts
    last_error: Exception | None = None
    for attempt in range(effective_attempts):
        try:
            async with pool.claim_for_poll(account_id=required_owner) as acc:
                try:
                    result = await fetcher_fn(acc)
                except XapiError as exc:
                    body = getattr(exc, "detail", None)
                    body_str = str(body) if body is not None else None
                    await pool.report(acc["account_id"], exc.status_code or 0, body_str)
                    if exc.status_code in (401, 403) and attempt < effective_attempts - 1:
                        last_error = exc
                        continue
                    # 429 = Avito rate-limit on this token. Pool reports it,
                    # rotates to another account, and we back off briefly so
                    # the next attempt isn't on a still-warm bucket.
                    if exc.status_code == 429 and attempt < effective_attempts - 1:
                        last_error = exc
                        await asyncio.sleep(3)
                        continue
                    if exc.status_code is not None and exc.status_code >= 500 and attempt < effective_attempts - 1:
                        last_error = exc
                        await asyncio.sleep(5)
                        continue
                    raise
                else:
                    await pool.report(acc["account_id"], 200)
                    return result
        except NoAvailableAccountError:
            log.warning(
                "fetch_with_pool: pool drained — skipping (required_owner=%s)",
                required_owner,
            )
            return None
    if last_error is not None:
        raise last_error
    raise RuntimeError("fetch_with_pool exhausted without error")  # pragma: no cover


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

    # --- fetch via account pool (rotates on 403/401/5xx) ---
    pool = get_account_pool()

    # build_polling_url overlays the profile's search-вилка (search_min_price /
    # search_max_price), region_slug, delivery, sort onto the base URL so the
    # query string carries the wide ±25% search range. Without this Avito
    # returns lots above the alert range — the user-pasted URL often has no
    # pmin/pmax at all (only `?context=H4sI...` cookies survive copy-paste).
    polling_url = build_polling_url(profile)

    def _make_fetcher(page_num: int):
        async def _fetcher(acc: dict):
            async with AvitoMcpClient(account_id=acc["account_id"]) as mcp:
                if (
                    profile.import_source == "autosearch_sync"
                    and profile.avito_autosearch_id
                ):
                    return await mcp.fetch_subscription_items(
                        int(profile.avito_autosearch_id), page=page_num
                    )
                return await mcp.fetch_search_page(polling_url, page=page_num)
        return _fetcher

    required_owner: str | None = None
    if (
        profile.import_source == "autosearch_sync"
        and profile.avito_autosearch_id
        and profile.owner_account_id
    ):
        required_owner = str(profile.owner_account_id)

    # Avito returns ~30 items per page. For an iPhone 12 Pro Max search in a
    # ±25% price вилка, total results sit around 500 → ~17 pages. The cap of
    # 25 lets us absorb growth without runaway pagination on a misconfigured
    # profile. If a profile genuinely needs more, we'll bump the cap rather
    # than silently truncate.
    MAX_POLL_PAGES = 25

    # Inter-page delay. Avito caps requests-per-token at ~1 rps; without this
    # we 429 on page 2 because the analysis fan-out from page 1 already
    # consumed our budget. The Avito-app paginates lazily on user scroll, so
    # mimicking that pace stays under the cap.
    PAGE_DELAY_SECONDS = 1.2

    pages_fetched: list = []  # list[SearchPage]
    page_total: int | None = None
    pool_drained = False
    fetch_error: Exception | None = None
    for page_num in range(1, MAX_POLL_PAGES + 1):
        if page_num > 1:
            await asyncio.sleep(PAGE_DELAY_SECONDS)
        try:
            pg = await fetch_with_pool(
                fetcher_fn=_make_fetcher(page_num),
                pool=pool,
                required_owner=required_owner,
            )
        except Exception as exc:  # pragma: no cover — covered by health-checker
            log.exception(
                "polling.fetch_failed profile_id=%s url=%s page=%d",
                profile_id, profile.avito_search_url, page_num,
            )
            fetch_error = exc
            break

        if pg is None:
            # Pool fully drained mid-paginate. Keep what we already have and
            # bail; next tick will pick up where we left off (since seen=False
            # listings get _close_disappeared'd only if we DID complete).
            log.warning(
                "polling.pool_drained_mid_paginate profile_id=%s page=%d",
                profile_id, page_num,
            )
            pool_drained = True
            break

        if page_total is None:
            page_total = pg.total
        pages_fetched.append(pg)
        # Stop once Avito tells us there's no next page, OR we get a short
        # page (defensive — has_more occasionally flaps to True on the very
        # last page).
        if not pg.has_more or not pg.items:
            break

    if fetch_error is not None and not pages_fetched:
        async with sessionmaker() as session:
            await session.execute(
                update(ProfileRun)
                .where(ProfileRun.id == run_id)
                .values(
                    finished_at=datetime.now(timezone.utc),
                    status=ProfileRunStatus.FAILED.value,
                    error_message=str(fetch_error)[:512],
                )
            )
            await session.commit()
        return {"status": "failed", "reason": "fetch_failed"}

    if not pages_fetched:
        async with sessionmaker() as session:
            await session.execute(
                update(ProfileRun)
                .where(ProfileRun.id == run_id)
                .values(
                    finished_at=datetime.now(timezone.utc),
                    status=ProfileRunStatus.FAILED.value,
                    error_message="pool_drained: no available account",
                )
            )
            await session.commit()
        return {"status": "skipped", "reason": "pool_drained"}

    # Flatten all pages into a single iteration. _close_disappeared at the end
    # keys off this run's started_at, so a partially-complete paginate (pool
    # drained mid-way) WON'T mark the un-fetched tail as closed — _upsert
    # bumps last_seen only for items we actually saw, and items we never got
    # to see retain their previous last_seen and stay open.
    all_items = [it for pg in pages_fetched for it in pg.items]
    pages_count = len(pages_fetched)
    log.info(
        "polling.pagination profile_id=%s pages=%d items=%d total=%s drained=%s",
        profile_id, pages_count, len(all_items), page_total, pool_drained,
    )

    # `page` (first SearchPage) is kept around only so the metrics block
    # below can read `.total` and `.applied_query` without re-derivation.
    page = pages_fetched[0]

    blocked = set(profile.blocked_sellers or [])
    to_analyze: list[uuid.UUID] = []

    # Title pre-filter: Avito free-text search is fuzzy and returns lots of
    # garbage when query is just "Iphone 12 Pro Max" (chairs called "Apple",
    # cutting boards, kitchen scales mentioning "iPhone" in description).
    # Until we wire up structured params[brand][model] queries via autosearch
    # subscriptions, drop items whose title doesn't contain the expected
    # brand+model tokens. parsed_brand/parsed_model are populated by
    # url_parser when the user creates the profile.
    title_must_contain: list[str] = []
    eff_brand = profile.parsed_brand
    eff_model = profile.parsed_model
    # Self-heal: profiles created before url_parser was tightened may have
    # NULL parsed_brand / parsed_model. Re-parse the URL on-the-fly so the
    # filter still works without backfill migration.
    if (not eff_brand or not eff_model) and profile.avito_search_url:
        try:
            from app.services.url_parser import parse_avito_url
            re_parsed = parse_avito_url(profile.avito_search_url)
            eff_brand = eff_brand or re_parsed.brand
            eff_model = eff_model or re_parsed.model
        except Exception:
            log.exception("polling.reparse_failed profile_id=%s", profile_id)
    if eff_brand:
        title_must_contain.append(eff_brand.lower())
    if eff_model:
        # Multi-word models ("12 Pro Max") → every token must appear in title.
        for tok in eff_model.lower().split():
            if tok and tok not in title_must_contain:
                title_must_contain.append(tok)

    listings_filtered_out = 0

    async with sessionmaker() as session:
        # Per-user global blacklist (ADR-011): once a user has rejected a
        # listing, it should never resurface in any of their profiles, even
        # under different criteria. We pre-fetch the avito_ids of blacklisted
        # listings for this profile's owner in one query and skip them below.
        blacklisted_avito_ids: set[int] = set(
            (await session.execute(
                select(Listing.avito_id)
                .join(UserListingBlacklist, UserListingBlacklist.listing_id == Listing.id)
                .where(UserListingBlacklist.user_id == profile.user_id)
            )).scalars().all()
        )

        for item in all_items:
            if item.seller_id is not None and str(item.seller_id) in blocked:
                continue
            if item.id in blacklisted_avito_ids:
                continue

            # Drop fuzzy-search noise: title must contain every brand+model token
            # as a *word*, not as a substring. "12" должен матчить "12 ГБ", но
            # НЕ "128 ГБ" — иначе iPhone 14 Pro Max (128) проходит в выдачу
            # iPhone 12 Pro Max. См. DOCS/REFERENCE/05.
            if title_must_contain:
                title_words = set(_WORD_RE.findall((item.title or "").lower()))
                if not all(tok in title_words for tok in title_must_contain):
                    listings_filtered_out += 1
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

            # Stage-1 LLM dispatch (Block 4.2).
            # Trigger conditions:
            #  - brand-new listing (always classify so we can route it
            #    into market-data even if it's outside alert zone), OR
            #  - existing listing whose price just dropped into the
            #    alert zone (we re-classify because match might change).
            if is_new or (price_changed and in_alert):
                to_analyze.append(listing_id)

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
                    "queued_for_analysis": len(to_analyze),
                },
            )
        )
        await session.commit()

    # Enqueue analysis AFTER the polling commit. Doing it outside the
    # DB session keeps the transaction short and lets the worker pull
    # them up immediately from Redis.
    #
    # Phase C: legacy analyze_listing removed. All profiles must have at
    # least one profile_criteria row. Profiles without criteria are
    # skipped (safety guard — no silently wrong LLM calls).
    enqueued_for_analysis = 0
    if to_analyze:
        from sqlalchemy import func as sa_func

        from app.tasks.analysis import evaluate_listing

        async with sessionmaker() as session:
            count = await session.scalar(
                select(sa_func.count(ProfileCriterion.id)).where(
                    ProfileCriterion.profile_id == pid
                )
            )
        if not count:
            log.warning(
                "polling.no_criteria_skip_analysis profile_id=%s",
                profile_id,
            )
        else:
            for lid in to_analyze:
                try:
                    await evaluate_listing.kiq(str(lid), str(pid))
                    enqueued_for_analysis += 1
                except Exception:
                    log.exception(
                        "polling.enqueue_analyze_failed listing_id=%s", lid
                    )

    log.info(
        "polling.success profile_id=%s seen=%d new=%d in_alert=%d closed=%d analyze=%d",
        profile_id, listings_seen, listings_new, listings_in_alert, closed,
        enqueued_for_analysis,
    )
    return {
        "status": "success",
        "listings_seen": listings_seen,
        "listings_new": listings_new,
        "listings_in_alert": listings_in_alert,
        "price_changes": price_changed_count,
        "closed_disappeared": closed,
        "enqueued_for_analysis": enqueued_for_analysis,
    }

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
import random
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

# Word-boundary tokeniser for post-filter title matching. \w+ матчит alnum
# и Unicode-буквы (re.UNICODE по умолчанию в Python 3) — кириллица входит.
# Ловит "iPhone 12 Pro Max, 128 ГБ" → ["iphone","12","pro","max","128","гб"],
# что предотвращает substring-false-positive «"12" in "128"».
_WORD_RE = re.compile(r"\w+", re.UNICODE)

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import Settings, get_settings
from app.db.base import get_sessionmaker
from app.db.models import (
    Listing,
    ListingStatusEvent,
    ProfileCriterion,
    ProfileListing,
    ProfileRun,
    SearchProfile,
    SystemSetting,
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


# ---------------------------------------------------------------------------
# Polling humanization helpers (ADR: бот ходит как живой человек)
# ---------------------------------------------------------------------------

# system_settings key holding {"counter": int, "break_until": iso8601 | null}.
# counter == polls executed since the last forced break; once it crosses a
# random target in [BREAK_AFTER_MIN, BREAK_AFTER_MAX], we set break_until
# to now + uniform(BREAK_DURATION_MIN..MAX) minutes and reset counter.
_BREAK_STATE_KEY = "polling_break_state"
BREAK_AFTER_MIN = 8
BREAK_AFTER_MAX = 12
BREAK_DURATION_MIN_MINUTES = 20
BREAK_DURATION_MAX_MINUTES = 40

# How long a "full paginate" stays valid before the next tick must walk all
# pages again. Between full walks we only fetch page=1 — same shape as a user
# refreshing the search and only looking at the freshest 30 lots.
FULL_POLL_INTERVAL = timedelta(hours=1)


def is_within_active_hours(now: datetime, settings: Settings) -> bool:
    """True iff ``now`` (UTC-aware) falls inside ``[start, end)`` in the
    configured timezone. If the env override is off, always True.

    Window is half-open: ``8 <= h < 23`` for the default 8..23 config —
    wakes up at 08:00, last allowed minute is 22:59.
    """
    if not settings.poll_respect_active_hours:
        return True
    tz = ZoneInfo(settings.poll_active_hours_timezone)
    local = now.astimezone(tz)
    start = settings.poll_active_hours_start
    end = settings.poll_active_hours_end
    return start <= local.hour < end


async def _load_break_state(session) -> tuple[int, datetime | None]:
    """Read polling_break_state row → (counter, break_until)."""
    row = await session.get(SystemSetting, _BREAK_STATE_KEY)
    if row is None:
        return 0, None
    val = row.value or {}
    counter = int(val.get("counter") or 0)
    raw_until = val.get("break_until")
    break_until: datetime | None = None
    if raw_until:
        try:
            parsed = datetime.fromisoformat(raw_until)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            break_until = parsed
        except ValueError:
            log.warning("polling.break_state.bad_until value=%r", raw_until)
    return counter, break_until


async def _save_break_state(
    session, *, counter: int, break_until: datetime | None
) -> None:
    """Upsert polling_break_state — single row, key is the constant."""
    payload = {
        "counter": counter,
        "break_until": break_until.isoformat() if break_until else None,
    }
    insert_stmt = pg_insert(SystemSetting).values(
        key=_BREAK_STATE_KEY, value=payload
    )
    do_update = insert_stmt.on_conflict_do_update(
        index_elements=[SystemSetting.key],
        set_={"value": insert_stmt.excluded.value},
    )
    await session.execute(do_update)


async def _check_and_advance_break(sessionmaker, now: datetime) -> str | None:
    """Return ``None`` to proceed with the poll, or a skip reason string.

    State machine:
      * if ``break_until`` is in the future → return "on_break"
      * else increment counter; once it ≥ random target picked at reset,
        flip into a fresh break (random 20-40 min) and return "on_break"
      * otherwise persist incremented counter and return None
    """
    async with sessionmaker() as session:
        counter, break_until = await _load_break_state(session)

        if break_until is not None and break_until > now:
            return "on_break"

        # Break expired (or never started) — resume counting.
        new_counter = counter + 1
        target = random.randint(BREAK_AFTER_MIN, BREAK_AFTER_MAX)
        if new_counter >= target:
            duration = timedelta(
                minutes=random.uniform(
                    BREAK_DURATION_MIN_MINUTES, BREAK_DURATION_MAX_MINUTES
                )
            )
            new_until = now + duration
            await _save_break_state(
                session, counter=0, break_until=new_until
            )
            await session.commit()
            log.info(
                "polling.break.start until=%s after_polls=%d",
                new_until.isoformat(), new_counter,
            )
            return "on_break"

        await _save_break_state(session, counter=new_counter, break_until=None)
        await session.commit()
        return None


def _should_full_paginate(profile: SearchProfile, now: datetime) -> bool:
    """True if it's been ≥1h since the last full pagination for this profile."""
    last = profile.last_full_poll_at
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last) >= FULL_POLL_INTERVAL


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
) -> tuple[uuid.UUID, bool, bool, float | None, bool, str | None]:
    """Upsert one listing by ``avito_id`` and return:

    ``(id, is_new, price_changed, prev_price, reservation_changed, prev_reservation_status)``

    For an existing row we only refresh ``last_seen_at``, ``price`` (if
    actually changed), ``last_price_change_at`` and the few mutable
    cosmetic fields. Anything LLM-derived stays untouched so a
    re-poll never wipes out a classification we already paid for.

    ``reservation_status`` is seeded from the item on INSERT (default 'active'
    when xapi couldn't infer); on UPDATE we deliberately do NOT mutate it
    here — the caller handles the diff so it can also write a status-event
    row in the same transaction.
    """
    new_price = _to_decimal(item.price)
    insert_reservation = item.reservation_status or "active"
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
        reservation_status=insert_reservation,
    ).returning(
        Listing.id,
        Listing.price,
        Listing.first_seen_at,
        Listing.reservation_status,
    )

    do_update = insert_stmt.on_conflict_do_update(
        index_elements=[Listing.avito_id],
        set_={
            "title": insert_stmt.excluded.title,
            "region": insert_stmt.excluded.region,
            "url": insert_stmt.excluded.url,
            # NOTE: don't refresh images here. Search feed only carries the
            # cover photo; the full gallery is populated by evaluate_listing /
            # refresh_listing_detail from /items/{id}. Overwriting on every
            # poll wipes the gallery back to cover-only.
            "last_seen_at": insert_stmt.excluded.last_seen_at,
            "status": ListingStatus.ACTIVE.value,
        },
    )
    row = (await session.execute(do_update)).one()
    listing_id = row.id
    stored_price = row.price
    first_seen_at = row.first_seen_at
    stored_reservation = row.reservation_status
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

    # Reservation diff. Only meaningful on existing rows AND when xapi
    # actually inferred a status (None = unknown, don't fabricate a flip
    # to/from active).
    reservation_changed = False
    prev_reservation: str | None = None
    if (
        not is_new
        and item.reservation_status is not None
        and stored_reservation is not None
        and item.reservation_status != stored_reservation
    ):
        prev_reservation = stored_reservation
        reservation_changed = True

    return (
        listing_id,
        is_new,
        price_changed,
        prev_price,
        reservation_changed,
        prev_reservation,
    )


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
    settings = get_settings()

    # Humanization gate 1: outside active hours → just bail. Cheap, no DB writes,
    # no ProfileRun row created (we don't want failed-run noise overnight).
    if not is_within_active_hours(started_at, settings):
        log.info(
            "polling.skip.outside_active_hours profile_id=%s",
            profile_id,
        )
        return {"status": "skipped", "reason": "outside_active_hours"}

    # Humanization gate 2: random session break. Same bail-early shape.
    break_reason = await _check_and_advance_break(sessionmaker, started_at)
    if break_reason is not None:
        log.info(
            "polling.skip.on_break profile_id=%s",
            profile_id,
        )
        return {"status": "skipped", "reason": break_reason}

    async with sessionmaker() as session:
        profile = await session.get(SearchProfile, pid)
        if profile is None:
            log.warning("polling.profile_not_found id=%s", profile_id)
            return {"status": "skipped", "reason": "profile not found"}
        if not profile.is_active:
            log.info("polling.profile_inactive id=%s", profile_id)
            return {"status": "skipped", "reason": "profile inactive"}

        # Decide BEFORE the run row is created so the metrics know about it.
        full_paginate = _should_full_paginate(profile, started_at)

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
    #
    # Humanization: only the once-per-hour "full" tick walks all pages. Every
    # other tick fetches page=1 only — same shape as a buyer pulling-to-refresh
    # the search and only glancing at the freshest 30 lots.
    MAX_POLL_PAGES = 25 if full_paginate else 1

    pages_fetched: list = []  # list[SearchPage]
    page_total: int | None = None
    pool_drained = False
    fetch_error: Exception | None = None
    for page_num in range(1, MAX_POLL_PAGES + 1):
        if page_num > 1:
            # Random uniform 2-5s instead of fixed 1.2s. Keeps us under Avito's
            # ~1rps token cap with extra slack and breaks the constant-cadence
            # pattern that screams "bot".
            await asyncio.sleep(random.uniform(2.0, 5.0))
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
    # Items whose reservation_status flipped — re-fetch detail (no LLM) so
    # description / parameters reflect the new state; the detail endpoint
    # may also carry richer reservation hints than the search card.
    to_refresh_detail: list[uuid.UUID] = []
    reservation_changes_count = 0
    reservations_captured = 0

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
            (
                listing_id,
                is_new,
                price_changed,
                prev_price,
                reservation_changed,
                prev_reservation,
            ) = await _upsert_listing(session, item, started_at)
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

            # ── Three buckets for what to do next ─────────────────────────
            # 1. New listing → full LLM evaluation. Same as before.
            # 2. Price changed (existing) → audit-log row + listings.price
            #    already updated in _upsert_listing. NO LLM re-eval —
            #    the description / criteria haven't moved.
            # 3. Reservation flipped → audit-log row + (if flipped to
            #    'reserved') a reservation_capture snapshot row + commit
            #    the new reservation_status / changed_at / reserved_at_price
            #    onto the listing. Then queue a detail re-fetch (no LLM).
            if is_new:
                to_analyze.append(listing_id)

            if price_changed:
                session.add(
                    ListingStatusEvent(
                        listing_id=listing_id,
                        event_type="price_change",
                        old_value=str(prev_price) if prev_price is not None else None,
                        new_value=(
                            str(item.price) if item.price is not None else None
                        ),
                        at=started_at,
                    )
                )

            if reservation_changed:
                reservation_changes_count += 1
                session.add(
                    ListingStatusEvent(
                        listing_id=listing_id,
                        event_type="status_change",
                        old_value=prev_reservation,
                        new_value=item.reservation_status,
                        at=started_at,
                    )
                )
                listing_updates: dict[str, Any] = {
                    "reservation_status": item.reservation_status,
                    "reservation_changed_at": started_at,
                }
                if item.reservation_status == "reserved":
                    # Snapshot the price the seller had at the moment of
                    # reservation — this is the headline number for market
                    # intelligence (closest signal we get to a real deal).
                    captured_price = (
                        _to_decimal(item.price)
                        if item.price is not None
                        else _to_decimal(prev_price)
                    )
                    listing_updates["reserved_at_price"] = captured_price
                    session.add(
                        ListingStatusEvent(
                            listing_id=listing_id,
                            event_type="reservation_capture",
                            old_value=None,
                            new_value=(
                                str(captured_price)
                                if captured_price is not None
                                else None
                            ),
                            at=started_at,
                        )
                    )
                    reservations_captured += 1
                await session.execute(
                    update(Listing)
                    .where(Listing.id == listing_id)
                    .values(**listing_updates)
                )
                to_refresh_detail.append(listing_id)

        # _close_disappeared keys off "anything not bumped to last_seen=now is
        # gone". That assumption only holds when we paginated EVERYTHING — on
        # an incremental tick (page=1, ~30 items) we'd wrongly close every
        # listing past the first page. Skip on incremental runs; the next
        # full walk (≤1h later) will catch genuine closures.
        if full_paginate:
            closed = await _close_disappeared(
                session, profile_id=pid, run_started_at=started_at
            )
        else:
            closed = 0

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
                    "queued_for_detail_refresh": len(to_refresh_detail),
                    "reservation_changes": reservation_changes_count,
                    "reservations_captured": reservations_captured,
                    "full_paginate": full_paginate,
                    "pages_fetched": pages_count,
                },
            )
        )

        # Persist the full-paginate timestamp so the next ≤1h of ticks
        # take the cheap page=1-only path. Done in the same commit as the
        # run row so a crash here can't leave us with a stale marker.
        if full_paginate:
            await session.execute(
                update(SearchProfile)
                .where(SearchProfile.id == pid)
                .values(last_full_poll_at=started_at)
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

    # Detail-refresh fan-out for reservation-flipped items. Independent of
    # the analyze enqueue: detail re-fetch is cheap (no LLM) and we want it
    # even on profiles without criteria, since reservation state is profile-
    # agnostic listing data.
    enqueued_for_detail_refresh = 0
    if to_refresh_detail:
        from app.tasks.analysis import refresh_listing_detail

        for lid in to_refresh_detail:
            try:
                await refresh_listing_detail.kiq(str(lid))
                enqueued_for_detail_refresh += 1
            except Exception:
                log.exception(
                    "polling.enqueue_detail_refresh_failed listing_id=%s", lid
                )

    log.info(
        "polling.success profile_id=%s seen=%d new=%d in_alert=%d closed=%d "
        "analyze=%d detail_refresh=%d reservation_changes=%d "
        "full_paginate=%s pages=%d",
        profile_id, listings_seen, listings_new, listings_in_alert, closed,
        enqueued_for_analysis, enqueued_for_detail_refresh,
        reservation_changes_count, full_paginate, pages_count,
    )
    return {
        "status": "success",
        "listings_seen": listings_seen,
        "listings_new": listings_new,
        "listings_in_alert": listings_in_alert,
        "price_changes": price_changed_count,
        "closed_disappeared": closed,
        "enqueued_for_analysis": enqueued_for_analysis,
        "enqueued_for_detail_refresh": enqueued_for_detail_refresh,
        "reservation_changes": reservation_changes_count,
        "reservations_captured": reservations_captured,
    }

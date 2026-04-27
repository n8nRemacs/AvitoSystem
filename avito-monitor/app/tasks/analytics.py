"""Daily market-stats aggregation (Block 4.3 — minimal triggers).

Two cooperating jobs:

* :func:`tick` — runs once per day (cron ``5 0 * * *`` UTC). Walks every
  active profile and enqueues :func:`compute_market_stats` for each.
  Polling-style instead of CronCreate-per-profile because profile sets
  change at runtime and reseeding scheduler labels is fiddly.

* :func:`compute_market_stats(profile_id, granularity)` — aggregates the
  previous UTC day for one profile, upserts a row in
  ``profile_market_stats``, then compares against the prior period and
  emits market-insight notifications when the configured thresholds are
  crossed (``market_trend_*``, ``supply_surge``, ``condition_mix_change``).

Block 7 will replace this with the full Price-Intelligence engine
(``historical_low`` over a rolling 30-day window, smoothing,
auto-recommended alert bands). For now we keep the math intentionally
naive so the dashboard has data and Telegram has something to show by
the time Block 5 turns the notifications real.
"""
from __future__ import annotations

import logging
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.base import get_sessionmaker
from app.db.models import (
    Listing,
    Notification,
    ProfileListing,
    ProfileMarketStats,
    SearchProfile,
)
from app.db.models.enums import (
    ConditionClass,
    ListingStatus,
    NotificationStatus,
    NotificationType,
    StatGranularity,
)
from app.tasks.broker import broker

log = logging.getLogger(__name__)


# Default thresholds (ADR-009). Overridden per-profile via
# ``notification_settings`` JSONB. Stored as fractions, not percents.
_DEFAULT_TRIGGERS = {
    "market_trend_pct": 0.05,
    "supply_surge_pct": 0.30,
    "condition_mix_pct": 0.10,
}


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _period_window(
    granularity: str, now: datetime
) -> tuple[datetime, datetime]:
    """Return (period_start, period_end) for the most recently *closed* period.

    Aligned to UTC midnight so consecutive daily runs produce
    non-overlapping windows the trigger logic can compare directly.
    """
    today_utc = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == StatGranularity.WEEK.value:
        # Monday-aligned ISO week boundary.
        weekday = today_utc.weekday()  # 0=Mon .. 6=Sun
        this_monday = today_utc - timedelta(days=weekday)
        return this_monday - timedelta(days=7), this_monday
    if granularity == StatGranularity.MONTH.value:
        first_of_this = today_utc.replace(day=1)
        # Step back into previous month, then normalise to its first day.
        last_of_prev = first_of_this - timedelta(days=1)
        first_of_prev = last_of_prev.replace(day=1)
        return first_of_prev, first_of_this
    # default: day
    return today_utc - timedelta(days=1), today_utc


def _trigger_thresholds(profile: SearchProfile) -> dict[str, float]:
    """Resolve trigger thresholds — profile overrides global defaults."""
    settings = profile.notification_settings or {}
    out = dict(_DEFAULT_TRIGGERS)
    for key in out:
        raw = settings.get(key)
        if raw is None:
            continue
        try:
            out[key] = float(raw)
        except (TypeError, ValueError):
            continue
    return out


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _percentile(values: list[float], pct: float) -> float | None:
    """Linear-interpolation percentile. ``pct`` ∈ [0,100]."""
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    rank = (pct / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def _condition_distribution(condition_counts: dict[str, int]) -> dict[str, float]:
    total = sum(condition_counts.values())
    if total == 0:
        return {}
    return {k: round(v / total, 4) for k, v in condition_counts.items()}


def _emit(
    session,
    *,
    user_id: uuid.UUID,
    profile_id: uuid.UUID,
    channels: Iterable[str],
    notif_type: str,
    payload: dict[str, Any],
) -> int:
    """Stage a Notification row per channel. Caller commits."""
    n = 0
    for channel in channels:
        session.add(
            Notification(
                user_id=user_id,
                profile_id=profile_id,
                related_listing_id=None,
                type=notif_type,
                channel=channel,
                payload=payload,
                status=NotificationStatus.PENDING.value,
            )
        )
        n += 1
    return n


# ----------------------------------------------------------------------
# compute_market_stats
# ----------------------------------------------------------------------

@broker.task(task_name="app.tasks.analytics.compute_market_stats")
async def compute_market_stats(
    profile_id: str, granularity: str = "day"
) -> dict[str, Any]:
    """Aggregate the previous UTC day for one profile + emit triggers."""
    sessionmaker = get_sessionmaker()
    pid = uuid.UUID(profile_id)
    now = datetime.now(timezone.utc)
    period_start, period_end = _period_window(granularity, now)
    prev_start = period_start - (period_end - period_start)

    async with sessionmaker() as session:
        profile = await session.get(SearchProfile, pid)
        if profile is None:
            log.warning("analytics.profile_missing id=%s", profile_id)
            return {"status": "skipped", "reason": "profile missing"}

        # --- snapshot of "active in window" listings for this profile ---
        # We define "in window" as: linked to this profile AND visible at
        # least once during [period_start, period_end).
        rows = (
            await session.execute(
                select(Listing)
                .join(ProfileListing, ProfileListing.listing_id == Listing.id)
                .where(
                    ProfileListing.profile_id == pid,
                    Listing.last_seen_at >= period_start,
                    Listing.first_seen_at < period_end,
                )
            )
        ).scalars().all()

        # --- new / disappeared counters (independent of snapshot) -------
        new_count = (
            await session.execute(
                select(func.count())
                .select_from(Listing)
                .join(ProfileListing, ProfileListing.listing_id == Listing.id)
                .where(
                    ProfileListing.profile_id == pid,
                    Listing.first_seen_at >= period_start,
                    Listing.first_seen_at < period_end,
                )
            )
        ).scalar_one() or 0

        disappeared_q = (
            select(Listing.first_seen_at, Listing.last_seen_at)
            .join(ProfileListing, ProfileListing.listing_id == Listing.id)
            .where(
                ProfileListing.profile_id == pid,
                Listing.last_seen_at >= period_start,
                Listing.last_seen_at < period_end,
                Listing.status.in_(
                    [ListingStatus.CLOSED.value, ListingStatus.REMOVED.value]
                ),
            )
        )
        disappeared_rows = (await session.execute(disappeared_q)).all()
        disappeared_count = len(disappeared_rows)
        if disappeared_rows:
            lifetimes_h = []
            for first_seen, last_seen in disappeared_rows:
                if first_seen and last_seen:
                    delta = last_seen - first_seen
                    lifetimes_h.append(delta.total_seconds() / 3600.0)
            avg_lifetime_h = (
                round(sum(lifetimes_h) / len(lifetimes_h), 2)
                if lifetimes_h
                else None
            )
        else:
            avg_lifetime_h = None

        # --- price metrics ---------------------------------------------
        prices_raw = [
            float(r.price)
            for r in rows
            if r.price is not None
        ]
        allowed = set(profile.allowed_conditions or [ConditionClass.WORKING.value])
        prices_clean = [
            float(r.price)
            for r in rows
            if r.price is not None and r.condition_class in allowed
        ]

        median_raw = round(statistics.median(prices_raw), 2) if prices_raw else None
        median_clean = (
            round(statistics.median(prices_clean), 2) if prices_clean else None
        )
        price_mean = (
            round(statistics.fmean(prices_raw), 2) if prices_raw else None
        )
        price_min = round(min(prices_raw), 2) if prices_raw else None
        price_max = round(max(prices_raw), 2) if prices_raw else None
        p25 = _percentile(prices_clean, 25.0)
        p75 = _percentile(prices_clean, 75.0)
        p25 = round(p25, 2) if p25 is not None else None
        p75 = round(p75, 2) if p75 is not None else None

        # --- condition distribution ------------------------------------
        condition_counts: dict[str, int] = {}
        for r in rows:
            condition_counts[r.condition_class] = (
                condition_counts.get(r.condition_class, 0) + 1
            )
        distribution = _condition_distribution(condition_counts)
        working_share = distribution.get(ConditionClass.WORKING.value)

        # --- upsert ProfileMarketStats ---------------------------------
        stats_payload = {
            "profile_id": pid,
            "granularity": granularity,
            "period_start": period_start,
            "period_end": period_end,
            "listings_count": len(rows),
            "new_listings_count": int(new_count),
            "disappeared_listings_count": disappeared_count,
            "avg_listing_lifetime_hours": avg_lifetime_h,
            "price_median_raw": median_raw,
            "price_median_clean": median_clean,
            "price_mean": price_mean,
            "price_min": price_min,
            "price_max": price_max,
            "price_p25_clean": p25,
            "price_p75_clean": p75,
            "working_share": working_share,
            "condition_distribution": distribution,
        }
        upsert = pg_insert(ProfileMarketStats).values(**stats_payload)
        upsert = upsert.on_conflict_do_update(
            constraint="uq_profile_market_stats_period",
            set_={
                k: upsert.excluded[k]
                for k in stats_payload
                if k not in {"profile_id", "granularity", "period_start"}
            },
        )
        await session.execute(upsert)

        # --- triggers (compare to previous period) ---------------------
        prev = (
            await session.execute(
                select(ProfileMarketStats).where(
                    ProfileMarketStats.profile_id == pid,
                    ProfileMarketStats.granularity == granularity,
                    ProfileMarketStats.period_start == prev_start,
                )
            )
        ).scalar_one_or_none()

        triggers_fired: list[str] = []
        notif_count = 0
        if prev is not None:
            thresholds = _trigger_thresholds(profile)
            channels = profile.notification_channels or ["telegram"]
            common_payload = {
                "granularity": granularity,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "previous_period_start": prev_start.isoformat(),
            }

            # market_trend_* — clean median change
            prev_median = _to_float(prev.price_median_clean)
            if prev_median and median_clean is not None and prev_median > 0:
                delta_pct = (median_clean - prev_median) / prev_median
                if abs(delta_pct) >= thresholds["market_trend_pct"]:
                    notif_type = (
                        NotificationType.MARKET_TREND_DOWN.value
                        if delta_pct < 0
                        else NotificationType.MARKET_TREND_UP.value
                    )
                    notif_count += _emit(
                        session,
                        user_id=profile.user_id,
                        profile_id=pid,
                        channels=channels,
                        notif_type=notif_type,
                        payload={
                            **common_payload,
                            "previous_median_clean": prev_median,
                            "current_median_clean": median_clean,
                            "delta_pct": round(delta_pct, 4),
                            "threshold_pct": thresholds["market_trend_pct"],
                        },
                    )
                    triggers_fired.append(notif_type)

            # supply_surge — listings_count change
            if prev.listings_count and len(rows) > 0:
                delta_pct = (len(rows) - prev.listings_count) / prev.listings_count
                if delta_pct >= thresholds["supply_surge_pct"]:
                    notif_count += _emit(
                        session,
                        user_id=profile.user_id,
                        profile_id=pid,
                        channels=channels,
                        notif_type=NotificationType.SUPPLY_SURGE.value,
                        payload={
                            **common_payload,
                            "previous_listings_count": prev.listings_count,
                            "current_listings_count": len(rows),
                            "delta_pct": round(delta_pct, 4),
                            "threshold_pct": thresholds["supply_surge_pct"],
                        },
                    )
                    triggers_fired.append(NotificationType.SUPPLY_SURGE.value)

            # condition_mix_change — working_share absolute swing
            prev_working = _to_float(prev.working_share)
            if prev_working is not None and working_share is not None:
                delta = working_share - prev_working
                if abs(delta) >= thresholds["condition_mix_pct"]:
                    notif_count += _emit(
                        session,
                        user_id=profile.user_id,
                        profile_id=pid,
                        channels=channels,
                        notif_type=NotificationType.CONDITION_MIX_CHANGE.value,
                        payload={
                            **common_payload,
                            "previous_working_share": prev_working,
                            "current_working_share": working_share,
                            "delta": round(delta, 4),
                            "threshold": thresholds["condition_mix_pct"],
                        },
                    )
                    triggers_fired.append(
                        NotificationType.CONDITION_MIX_CHANGE.value
                    )

        await session.commit()

    log.info(
        "analytics.computed profile_id=%s granularity=%s "
        "listings=%d median_clean=%s triggers=%s notifs=%d",
        profile_id, granularity, len(rows), median_clean,
        triggers_fired, notif_count,
    )
    return {
        "status": "success",
        "granularity": granularity,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "listings_count": len(rows),
        "median_clean": median_clean,
        "triggers_fired": triggers_fired,
        "notifications_created": notif_count,
    }


# ----------------------------------------------------------------------
# tick — daily fan-out
# ----------------------------------------------------------------------

@broker.task(
    task_name="app.tasks.analytics.tick",
    schedule=[{"cron": "5 0 * * *"}],
)
async def tick() -> dict[str, int]:
    """Daily 00:05 UTC: enqueue ``compute_market_stats`` for active profiles."""
    sessionmaker = get_sessionmaker()
    enqueued = 0
    async with sessionmaker() as session:
        ids = (
            await session.execute(
                select(SearchProfile.id).where(SearchProfile.is_active.is_(True))
            )
        ).scalars().all()

    for profile_id in ids:
        try:
            await compute_market_stats.kiq(str(profile_id), "day")
            enqueued += 1
        except Exception:
            log.exception(
                "analytics.tick.kiq_failed profile_id=%s", profile_id
            )

    log.info("analytics.tick enqueued=%d", enqueued)
    return {"enqueued": enqueued}

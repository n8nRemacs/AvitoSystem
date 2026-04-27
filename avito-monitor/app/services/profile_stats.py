"""Aggregate the data the Profile Stats screen renders (Block 6).

A single :func:`compute_stats_view` returns a plain dict that the Jinja
template inlines as JSON for Chart.js. The view is read-only and runs
in the request handler — for a personal monitor with ≤10 active
profiles this is fast enough that pre-computing into another table
would be premature.

Sources:

* ``profile_market_stats`` (filled by ``app.tasks.analytics``) — line
  chart history.
* ``listings`` joined to ``profile_listings`` — current price histogram
  + condition donut.
* ``notifications`` with ``type LIKE 'market_%'`` — market events feed.

If neither history nor a current snapshot is available the caller's
template shows a "stats accumulating" placeholder; we still return a
populated dict so the template can branch on counters.
"""
from __future__ import annotations

import statistics
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Listing,
    Notification,
    ProfileListing,
    ProfileMarketStats,
    SearchProfile,
)
from app.db.models.enums import ConditionClass, ListingStatus

# Histogram is grouped into ~10 buckets. We pick a "nice" bucket width
# (1k / 2.5k / 5k / 10k …) so the X axis labels read like real prices.
_NICE_WIDTHS = [
    500, 1_000, 2_000, 2_500, 5_000, 10_000, 20_000, 25_000, 50_000,
    100_000, 200_000, 500_000, 1_000_000,
]


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_bucket_width(prices: list[float]) -> int:
    if not prices:
        return 1000
    span = max(prices) - min(prices)
    if span <= 0:
        return 1000
    # target ~10 buckets — find the smallest "nice" width that produces
    # at most 12 of them.
    for w in _NICE_WIDTHS:
        if span / w <= 12:
            return w
    return _NICE_WIDTHS[-1]


def _bucket_label(low_int: int) -> str:
    if low_int >= 1_000_000:
        return f"{low_int / 1_000_000:.1f}M".rstrip("0").rstrip(".") + "M"
    if low_int >= 1000:
        # 13000 → 13K, 12500 → 12.5K
        v = low_int / 1000.0
        s = f"{v:g}"
        return f"{s}K"
    return str(int(low_int))


def _categorize(condition: str) -> str:
    """Reduce 8 ConditionClass values to 4 histogram buckets."""
    if condition == ConditionClass.WORKING.value:
        return "working"
    if condition in (
        ConditionClass.BLOCKED_ICLOUD.value,
        ConditionClass.BLOCKED_ACCOUNT.value,
    ):
        return "icloud"
    if condition in (
        ConditionClass.BROKEN_SCREEN.value,
        ConditionClass.BROKEN_OTHER.value,
        ConditionClass.NOT_STARTING.value,
    ):
        return "broken"
    if condition == ConditionClass.PARTS_ONLY.value:
        return "parts"
    return "unknown"


def _condition_label(condition: str) -> str:
    labels = {
        "working": "рабочие",
        "blocked_icloud": "iCloud-блок",
        "blocked_account": "блок Apple ID",
        "not_starting": "не включаются",
        "broken_screen": "разбит экран",
        "broken_other": "повреждённые",
        "parts_only": "на запчасти",
        "unknown": "не определено",
    }
    return labels.get(condition, condition)


# ---------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------

async def compute_stats_view(
    session: AsyncSession,
    profile: SearchProfile,
    *,
    history_days: int = 30,
    current_window_hours: int = 168,  # 7 days
) -> dict[str, Any]:
    """Build the Profile Stats view dict for a single profile."""
    now = datetime.now(timezone.utc)
    history_cutoff = now - timedelta(days=history_days)
    current_cutoff = now - timedelta(hours=current_window_hours)

    # --- history (line chart) -----------------------------------------
    hist_rows = (
        await session.execute(
            select(ProfileMarketStats)
            .where(
                ProfileMarketStats.profile_id == profile.id,
                ProfileMarketStats.granularity == "day",
                ProfileMarketStats.period_start >= history_cutoff,
            )
            .order_by(ProfileMarketStats.period_start.asc())
        )
    ).scalars().all()
    history = [
        {
            "d": row.period_start.strftime("%d.%m"),
            "period_start": row.period_start.isoformat(),
            "median_clean": _to_float(row.price_median_clean),
            "median_raw": _to_float(row.price_median_raw),
            "min": _to_float(row.price_min),
            "max": _to_float(row.price_max),
            "p25": _to_float(row.price_p25_clean),
            "p75": _to_float(row.price_p75_clean),
            "listings_count": row.listings_count,
        }
        for row in hist_rows
    ]

    # --- current snapshot (last 24h-ish) ------------------------------
    current_rows = (
        await session.execute(
            select(Listing)
            .join(ProfileListing, ProfileListing.listing_id == Listing.id)
            .where(
                ProfileListing.profile_id == profile.id,
                Listing.last_seen_at >= current_cutoff,
                Listing.status == ListingStatus.ACTIVE.value,
            )
        )
    ).scalars().all()

    prices_all: list[float] = []
    prices_clean: list[float] = []
    condition_counts: dict[str, int] = {}
    listings_for_hist: list[tuple[float, str]] = []  # (price, category)
    for r in current_rows:
        price = _to_float(r.price)
        if price is None:
            continue
        prices_all.append(price)
        if r.condition_class == ConditionClass.WORKING.value:
            prices_clean.append(price)
        cat = _categorize(r.condition_class)
        condition_counts[r.condition_class] = (
            condition_counts.get(r.condition_class, 0) + 1
        )
        listings_for_hist.append((price, cat))

    current_count = len(current_rows)
    in_alert = sum(
        1 for r in current_rows
        if profile.alert_min_price is not None
        and profile.alert_max_price is not None
        and r.price is not None
        and float(profile.alert_min_price) <= float(r.price) <= float(profile.alert_max_price)
    )

    median_clean_now = (
        round(statistics.median(prices_clean), 0) if prices_clean else None
    )
    working_share = (
        round(
            condition_counts.get(ConditionClass.WORKING.value, 0)
            / max(sum(condition_counts.values()), 1)
            * 100,
            1,
        )
        if condition_counts
        else None
    )

    # --- delta vs 30d-ago history (KPIs) ------------------------------
    median_clean_30d_ago: float | None = None
    if history:
        oldest = history[0]
        median_clean_30d_ago = oldest.get("median_clean")
    median_clean_delta_pct: float | None = None
    if (
        median_clean_now is not None
        and median_clean_30d_ago
        and median_clean_30d_ago > 0
    ):
        median_clean_delta_pct = round(
            (median_clean_now - median_clean_30d_ago) / median_clean_30d_ago * 100,
            1,
        )

    # --- histogram buckets --------------------------------------------
    buckets: list[dict[str, Any]] = []
    if listings_for_hist:
        prices_only = [p for p, _ in listings_for_hist]
        width = _pick_bucket_width(prices_only)
        low = (int(min(prices_only)) // width) * width
        high = (int(max(prices_only)) // width + 1) * width
        edges = list(range(low, high + 1, width))
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            entry = {
                "label": _bucket_label(lo),
                "low": lo, "high": hi,
                "working": 0, "broken": 0, "icloud": 0, "parts": 0,
                "unknown": 0,
            }
            buckets.append(entry)
        for price, cat in listings_for_hist:
            idx = min(int((price - low) // width), len(buckets) - 1)
            buckets[idx][cat] = buckets[idx].get(cat, 0) + 1

    # --- donut + legend rows ------------------------------------------
    donut = []
    for cls, cnt in sorted(
        condition_counts.items(), key=lambda kv: -kv[1]
    ):
        donut.append(
            {
                "key": cls,
                "label": _condition_label(cls),
                "count": cnt,
            }
        )

    # --- market events feed -------------------------------------------
    events_cutoff = now - timedelta(days=7)
    events_rows = (
        await session.execute(
            select(Notification)
            .where(
                Notification.profile_id == profile.id,
                Notification.created_at >= events_cutoff,
                Notification.type.in_(
                    [
                        "market_trend_down",
                        "market_trend_up",
                        "supply_surge",
                        "condition_mix_change",
                        "historical_low",
                    ]
                ),
            )
            .order_by(desc(Notification.created_at))
            .limit(50)
        )
    ).scalars().all()
    events = [
        {
            "id": str(n.id),
            "type": n.type,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "payload": n.payload or {},
            "status": n.status,
        }
        for n in events_rows
    ]

    # --- recommended alert band (rough) -------------------------------
    recommended_band: dict[str, float] | None = None
    if prices_clean and len(prices_clean) >= 4:
        ordered = sorted(prices_clean)
        rec_min = ordered[max(0, int(len(ordered) * 0.10))]
        rec_max = ordered[min(len(ordered) - 1, int(len(ordered) * 0.50))]
        recommended_band = {
            "min": round(rec_min, 0),
            "max": round(rec_max, 0),
        }

    # --- ready check --------------------------------------------------
    has_history = len(history) >= 7
    has_current = current_count > 0
    placeholder = (not has_history) and (not has_current)

    return {
        "profile": profile,
        "kpi": {
            "current_count": current_count,
            "in_alert": in_alert,
            "median_clean_now": median_clean_now,
            "median_clean_delta_pct": median_clean_delta_pct,
            "working_share": working_share,
        },
        "history": history,
        "history_days_with_data": len(history),
        "buckets": buckets,
        "donut": donut,
        "events": events,
        "recommended_band": recommended_band,
        "current_window_hours": current_window_hours,
        "history_days": history_days,
        "placeholder": placeholder,
        "has_history": has_history,
        "has_current": has_current,
    }


def serialize_for_template(view: dict[str, Any]) -> dict[str, Any]:
    """Strip ORM bits so ``json.dumps`` works on the chart payload."""
    return {
        "history": view["history"],
        "buckets": view["buckets"],
        "donut": view["donut"],
        "events": view["events"],
        "alert_band": (
            {
                "min": float(view["profile"].alert_min_price)
                if view["profile"].alert_min_price is not None
                else None,
                "max": float(view["profile"].alert_max_price)
                if view["profile"].alert_max_price is not None
                else None,
            }
            if view["profile"].alert_min_price is not None
            or view["profile"].alert_max_price is not None
            else None
        ),
    }


def _format_event_short(event: dict[str, Any]) -> str:
    """Plain-text one-liner for the "events" feed."""
    p = event.get("payload") or {}
    t = event.get("type")
    if t == "market_trend_down":
        return f"Медиана −{abs((p.get('delta_pct') or 0) * 100):.1f}%"
    if t == "market_trend_up":
        return f"Медиана +{(p.get('delta_pct') or 0) * 100:.1f}%"
    if t == "supply_surge":
        return f"Лотов +{(p.get('delta_pct') or 0) * 100:.0f}%"
    if t == "condition_mix_change":
        delta = (p.get("delta") or 0) * 100
        return f"Доля working {'+' if delta >= 0 else ''}{delta:.0f}%"
    if t == "historical_low":
        return f"Историческое дно — {p.get('price', '?')} ₽"
    return t or ""

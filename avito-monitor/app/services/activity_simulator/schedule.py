"""Schedule helpers: pick the next gap and the next action name.

Per TZ §6:

* Hour-of-day rate from settings (work vs off hours, in
  ``ACTIVITY_SIM_TIMEZONE``).
* Expected gap = 3600 / actions_per_hour, with ±50% uniform jitter.
* Action mix is a fixed weighted distribution (60/20/10/10).
"""
from __future__ import annotations

import random
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import Settings

# Action -> weight (sums to 100). Order is irrelevant for the sampler.
ACTION_WEIGHTS: dict[str, int] = {
    "get_chats": 60,
    "get_unread_count": 20,
    "get_listing_detail": 10,
    "open_random_chat_and_read": 10,
}


def is_work_hour(now: datetime, settings: Settings) -> bool:
    """True iff ``now`` (in the simulator's TZ) falls inside the work-hours window.

    The window is half-open: ``[start, end)``. If ``end`` <= ``start`` we treat
    the window as wrapping past midnight (e.g. 22..06). Defaults are 10..22.
    """
    tz = ZoneInfo(settings.activity_sim_timezone)
    local = now.astimezone(tz)
    h = local.hour
    start = settings.activity_sim_workhours_start
    end = settings.activity_sim_workhours_end
    if start == end:
        return False
    if start < end:
        return start <= h < end
    # Wrap-around window (e.g. 22..6).
    return h >= start or h < end


def actions_per_hour(now: datetime, settings: Settings) -> int:
    return (
        settings.activity_sim_actions_per_hour_work
        if is_work_hour(now, settings)
        else settings.activity_sim_actions_per_hour_off
    )


def next_gap_seconds(
    now: datetime,
    settings: Settings,
    *,
    rng: random.Random | None = None,
) -> float:
    """Return seconds until the next action.

    Computes the expected gap from the current hour-of-day rate, then applies
    uniform ±50% jitter. Caller should call this immediately *after* firing an
    action so the rate adapts to work/off-hours transitions naturally.
    """
    rate = actions_per_hour(now, settings)
    if rate <= 0:
        # Defensive: avoid div/0; sleep a long-ish minute and re-check.
        return 60.0
    expected = 3600.0 / rate
    r = rng or random
    jitter = r.uniform(0.5, 1.5)
    return expected * jitter


def pick_action_name(rng: random.Random | None = None) -> str:
    """Weighted-random pick from ACTION_WEIGHTS."""
    r = rng or random
    names = list(ACTION_WEIGHTS.keys())
    weights = [ACTION_WEIGHTS[n] for n in names]
    return r.choices(names, weights=weights, k=1)[0]


def expected_gap_seconds(rate_per_hour: int) -> float:
    """Expected gap (no jitter) for a given hourly rate. Helper for tests."""
    if rate_per_hour <= 0:
        return float("inf")
    return 3600.0 / rate_per_hour

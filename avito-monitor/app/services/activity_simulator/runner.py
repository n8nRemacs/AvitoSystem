"""Simulator scheduling loop.

One forever-loop that, on each tick, picks an action by weighted sample and
sleeps a jittered gap derived from the current hour-of-day rate. If
``ACTIVITY_SIM_ENABLED=false`` the loop just sleeps (manual triggers via the
FastAPI sidecar still work).
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from app.config import Settings, get_settings
from app.services.activity_simulator.actions import (
    ACTIONS,
    ITEM_ID_CACHE,
    ActionResult,
    run_action,
)
from app.services.activity_simulator.schedule import (
    actions_per_hour,
    next_gap_seconds,
    pick_action_name,
)
from app.services.health_checker.xapi_client import XapiClient

log = structlog.get_logger(__name__)


# Observability state for the FastAPI sidecar.
LAST_ACTION_TS: datetime | None = None
TOTAL_ACTIONS_TODAY: int = 0
_TOTALS_DAY: int | None = None  # day-of-year used to reset the counter on date roll


def _bump_counter(now: datetime) -> None:
    global TOTAL_ACTIONS_TODAY, _TOTALS_DAY, LAST_ACTION_TS
    today = now.timetuple().tm_yday
    if _TOTALS_DAY != today:
        _TOTALS_DAY = today
        TOTAL_ACTIONS_TODAY = 0
    TOTAL_ACTIONS_TODAY += 1
    LAST_ACTION_TS = now


def make_xapi_client(settings: Settings | None = None) -> XapiClient:
    s = settings or get_settings()
    return XapiClient(base_url=s.avito_xapi_url, api_key=s.avito_xapi_api_key)


async def run_named_once(name: str, settings: Settings | None = None) -> ActionResult:
    """Trigger one action by name; updates counters; persists log row."""
    settings = settings or get_settings()
    if name not in ACTIONS:
        raise KeyError(f"unknown action {name!r}; known: {sorted(ACTIONS)}")
    client = make_xapi_client(settings)
    result = await run_action(name, client)
    _bump_counter(datetime.now(UTC))
    return result


async def run_random_once(settings: Settings | None = None) -> ActionResult:
    """Pick + run one action by the weighted distribution."""
    settings = settings or get_settings()
    name = pick_action_name()
    client = make_xapi_client(settings)
    result = await run_action(name, client)
    # ``get_listing_detail`` may skip if the cache is empty — fall back to
    # something that's always safe to fire so the loop keeps the rate roughly
    # on target. We don't bump the counter for the skipped one.
    if result.status == "skipped" and name == "get_listing_detail":
        log.info("simulator.fallback", reason="item_id_cache empty", original=name)
        result = await run_action("get_chats", client)
    _bump_counter(datetime.now(UTC))
    return result


async def simulator_loop(settings: Settings) -> None:
    """Forever-loop. Honours ``ACTIVITY_SIM_ENABLED``."""
    log.info(
        "simulator.loop.start",
        enabled=settings.activity_sim_enabled,
        timezone=settings.activity_sim_timezone,
        workhours=f"{settings.activity_sim_workhours_start}..{settings.activity_sim_workhours_end}",
        rate_work=settings.activity_sim_actions_per_hour_work,
        rate_off=settings.activity_sim_actions_per_hour_off,
        cache_size=len(ITEM_ID_CACHE),
    )
    while True:
        now = datetime.now(UTC)
        gap = next_gap_seconds(now, settings)
        rate = actions_per_hour(now, settings)
        log.info(
            "simulator.tick.scheduled",
            sleep_sec=round(gap, 1),
            rate_per_hour=rate,
        )
        await asyncio.sleep(gap)
        if not settings.activity_sim_enabled:
            log.info("simulator.tick.disabled_skip")
            continue
        try:
            await run_random_once(settings)
        except Exception:
            log.exception("simulator.tick.crashed")


async def start_scheduler(settings: Settings | None = None) -> list[asyncio.Task]:
    """Spawn the single simulator loop task. Caller cancels on shutdown."""
    settings = settings or get_settings()
    task = asyncio.create_task(simulator_loop(settings), name="sim-loop")
    return [task]

"""Async scheduler + persister for health-check scenarios A-F.

* One coroutine per scenario, looping ``run -> persist -> sleep`` indefinitely.
* If ``RELIABILITY_ENABLED=false`` the loops still spawn but they only sleep
  (manual triggers from the API still execute).
* Persistence opens a fresh DB session per row to avoid long-lived txns.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from app.config import Settings, get_settings
from app.db.base import get_sessionmaker
from app.db.models import HealthCheck
from app.services.health_checker.alerts import check_and_alert_after_persist
from app.services.health_checker.scenarios import REGISTRY, ScenarioFn, ScenarioResult
from app.services.health_checker.xapi_client import XapiClient

log = structlog.get_logger(__name__)


# Tracks the latest run timestamp per scenario for /healthz uptime info.
LAST_RUNS: dict[str, datetime] = {}


def make_xapi_client(settings: Settings | None = None) -> XapiClient:
    s = settings or get_settings()
    return XapiClient(base_url=s.avito_xapi_url, api_key=s.avito_xapi_api_key)


async def persist_result(result: ScenarioResult) -> None:
    """Insert one row into ``health_checks``. Each call uses a fresh session."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = HealthCheck(
            scenario=result.scenario,
            status=result.status,
            latency_ms=result.latency_ms,
            details=result.details or None,
        )
        session.add(row)
        await session.commit()


async def run_one(name: str, fn: ScenarioFn, client: XapiClient) -> ScenarioResult:
    """Execute a single scenario, swallowing exceptions into a fail row."""
    try:
        result = await fn(client)
    except Exception as exc:  # a failed scenario must never crash the loop
        log.exception("scenario.crashed", scenario=name)
        result = ScenarioResult(
            scenario=name,
            status="fail",
            latency_ms=0,
            details={"error": f"{type(exc).__name__}: {exc}"},
        )
    LAST_RUNS[name] = datetime.now(UTC)
    return result


async def run_and_persist(name: str, fn: ScenarioFn, client: XapiClient) -> ScenarioResult:
    result = await run_one(name, fn, client)
    try:
        await persist_result(result)
    except Exception:  # persistence failure must not crash the loop
        log.exception("scenario.persist_failed", scenario=name, status=result.status)
    log.info(
        "scenario.completed",
        scenario=name,
        status=result.status,
        latency_ms=result.latency_ms,
        details=result.details,
    )
    try:
        await check_and_alert_after_persist(result)
    except Exception:  # alert failure must never crash the loop
        log.warning("scenario.alert_failed", scenario=name, status=result.status)
    return result


async def scenario_loop(name: str, fn: ScenarioFn, settings: Settings) -> None:
    """Forever-loop for one scenario; honours ``RELIABILITY_ENABLED`` toggle."""
    interval = settings.health_check_interval_sec
    log.info("scenario.loop.start", scenario=name, interval_sec=interval)
    while True:
        if not settings.reliability_enabled:
            await asyncio.sleep(interval)
            continue
        client = make_xapi_client(settings)
        await run_and_persist(name, fn, client)
        await asyncio.sleep(interval)


async def run_all_once(settings: Settings | None = None) -> list[ScenarioResult]:
    """Trigger every scenario in parallel, persist, and return all results."""
    settings = settings or get_settings()
    client = make_xapi_client(settings)
    results = await asyncio.gather(
        *[run_and_persist(name, fn, client) for name, fn in REGISTRY.items()]
    )
    return list(results)


async def run_named_once(name: str, settings: Settings | None = None) -> ScenarioResult:
    """Trigger one scenario by canonical name (case-insensitive)."""
    settings = settings or get_settings()
    key = name.upper()
    if key not in REGISTRY:
        raise KeyError(f"unknown scenario {name!r}; known: {sorted(REGISTRY)}")
    client = make_xapi_client(settings)
    return await run_and_persist(key, REGISTRY[key], client)


async def start_scheduler(settings: Settings | None = None) -> list[asyncio.Task]:
    """Spawn one task per scenario; caller is responsible for cancellation."""
    settings = settings or get_settings()
    tasks = [
        asyncio.create_task(scenario_loop(name, fn, settings), name=f"hc-loop-{name}")
        for name, fn in REGISTRY.items()
    ]
    return tasks

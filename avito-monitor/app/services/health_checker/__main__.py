"""Entry point for the health-checker service.

Boots:
1. structlog logging (via shared :func:`app.logging_config.configure_logging`)
2. six async loops (one per scenario A-F)
3. a tiny FastAPI for manual triggers, served on
   ``HEALTH_CHECKER_API_PORT`` (default 9100).
"""
from __future__ import annotations

import asyncio
import os
import signal

import structlog
import uvicorn

from app.config import get_settings
from app.logging_config import configure_logging
from app.services.account_pool_factory import get_account_pool
from app.services.health_checker.account_loop import account_loop
from app.services.health_checker.alerts import daily_summary_loop, send_alert
from app.services.health_checker.api import app as fastapi_app
from app.services.health_checker.runner import start_scheduler
from app.services.health_checker.token_refresher import loop as token_refresh_loop

log = structlog.get_logger(__name__)

DEFAULT_API_PORT = 9100


async def amain() -> None:
    settings = get_settings()
    configure_logging(settings)
    log.info(
        "health_checker.startup",
        env=settings.app_env,
        reliability_enabled=settings.reliability_enabled,
        interval_sec=settings.health_check_interval_sec,
        xapi_url=settings.avito_xapi_url,
    )

    # 1. background scheduler (per-scenario loops)
    loop_tasks = await start_scheduler(settings)

    # 1b. daily Telegram summary at RELIABILITY_TG_ALERT_DAILY_SUMMARY_HOUR MSK.
    summary_task = asyncio.create_task(
        daily_summary_loop(settings), name="hc-daily-summary"
    )
    loop_tasks.append(summary_task)

    # 1c. token-refresh trigger — watches the active xapi session's TTL
    # and, when JWT exp is 60–180 s away, asks the APK (via xapi
    # device-commands) to bring Avito to the foreground and nudge it.
    refresh_task = asyncio.create_task(
        token_refresh_loop(settings), name="hc-token-refresh"
    )
    loop_tasks.append(refresh_task)

    # 1d. account-pool tick — auto-recovery after cooldown, dead-detection,
    # proactive token refresh. Runs every 30 s in a separate task so it is
    # independent of the per-scenario reliability loops.
    _stop_event = asyncio.Event()
    account_task = asyncio.create_task(
        account_loop(get_account_pool(), send_alert, _stop_event),
        name="hc-account-tick",
    )
    loop_tasks.append(account_task)

    # 2. uvicorn server in the same event loop
    api_port = int(os.environ.get("HEALTH_CHECKER_API_PORT", DEFAULT_API_PORT))
    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",  # noqa: S104 — container-bound, exposed via docker
        port=api_port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)

    async def _shutdown() -> None:
        log.info("health_checker.shutdown.signal_received")
        server.should_exit = True
        _stop_event.set()  # wake account_loop immediately

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(_shutdown()))
        except NotImplementedError:
            # Windows: signal handlers not supported in proactor loop.
            pass

    try:
        await server.serve()
    finally:
        log.info("health_checker.shutdown.cancel_loops")
        for t in loop_tasks:
            t.cancel()
        await asyncio.gather(*loop_tasks, return_exceptions=True)


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()

"""Entry point for the activity-simulator service.

Boots:
1. structlog logging (via :func:`app.logging_config.configure_logging`)
2. one async simulator loop
3. a tiny FastAPI sidecar on ``ACTIVITY_SIM_API_PORT`` (default 9101).
"""
from __future__ import annotations

import asyncio
import os
import signal

import structlog
import uvicorn

from app.config import get_settings
from app.logging_config import configure_logging
from app.services.activity_simulator.api import app as fastapi_app
from app.services.activity_simulator.runner import start_scheduler

log = structlog.get_logger(__name__)

DEFAULT_API_PORT = 9101


async def amain() -> None:
    settings = get_settings()
    configure_logging(settings)
    log.info(
        "activity_simulator.startup",
        env=settings.app_env,
        enabled=settings.activity_sim_enabled,
        timezone=settings.activity_sim_timezone,
        rate_work=settings.activity_sim_actions_per_hour_work,
        rate_off=settings.activity_sim_actions_per_hour_off,
        xapi_url=settings.avito_xapi_url,
    )

    # 1. background loop
    loop_tasks = await start_scheduler(settings)

    # 2. FastAPI sidecar in the same event loop
    api_port = int(os.environ.get("ACTIVITY_SIM_API_PORT", DEFAULT_API_PORT))
    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",  # noqa: S104 — container-bound, exposed via docker
        port=api_port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)

    async def _shutdown() -> None:
        log.info("activity_simulator.shutdown.signal_received")
        server.should_exit = True

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
        log.info("activity_simulator.shutdown.cancel_loops")
        for t in loop_tasks:
            t.cancel()
        await asyncio.gather(*loop_tasks, return_exceptions=True)


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()

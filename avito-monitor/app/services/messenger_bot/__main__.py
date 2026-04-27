"""Entry point for the messenger-bot service.

Boots:

1. structlog logging (via :func:`app.logging_config.configure_logging`)
2. one async SSE-listener loop holding a connection to xapi
3. a tiny FastAPI sidecar on ``MESSENGER_BOT_API_PORT`` (default 9102)
"""
from __future__ import annotations

import asyncio
import os
import signal

import structlog
import uvicorn

from app.config import get_settings
from app.logging_config import configure_logging
from app.services.messenger_bot.api import app as fastapi_app
from app.services.messenger_bot.runner import start_listener

log = structlog.get_logger(__name__)

DEFAULT_API_PORT = 9102


async def amain() -> None:
    settings = get_settings()
    configure_logging(settings)
    log.info(
        "messenger_bot.startup",
        env=settings.app_env,
        enabled=settings.messenger_bot_enabled,
        whitelist_only=settings.messenger_bot_whitelist_own_listings_only,
        rate_limit_per_hour=settings.messenger_bot_rate_limit_per_hour,
        per_channel_cooldown_sec=settings.messenger_bot_per_channel_cooldown_sec,
        xapi_url=settings.avito_xapi_url,
    )

    # 1. SSE listener loop.
    loop_tasks = await start_listener(settings)

    # 2. FastAPI sidecar in the same event loop.
    api_port = int(os.environ.get("MESSENGER_BOT_API_PORT", DEFAULT_API_PORT))
    config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",  # noqa: S104 — container-bound, exposed via docker
        port=api_port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)

    async def _shutdown() -> None:
        log.info("messenger_bot.shutdown.signal_received")
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
        log.info("messenger_bot.shutdown.cancel_loops")
        for t in loop_tasks:
            t.cancel()
        await asyncio.gather(*loop_tasks, return_exceptions=True)


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()

"""Periodic runner for :func:`account_tick_iteration`.

Spawned as an independent asyncio.Task inside ``health_checker.__main__``
alongside the per-scenario reliability loops.  Runs every
:data:`ACCOUNT_TICK_INTERVAL` seconds; errors inside a tick are caught and
logged so they never kill the loop.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from app.services.health_checker.account_tick import account_tick_iteration

log = logging.getLogger(__name__)

ACCOUNT_TICK_INTERVAL = 30  # seconds

TgCallable = Callable[[str], Awaitable[None]]


async def account_loop(
    pool,
    tg: TgCallable,
    stop_event: asyncio.Event,
) -> None:
    """Forever-loop: call ``account_tick_iteration`` every 30 seconds.

    Args:
        pool: An :class:`~app.services.account_pool.AccountPool` instance.
        tg:   Async callable ``(message: str) -> None`` for Telegram alerts.
        stop_event: Set this to request a clean shutdown.
    """
    log.info("account_loop.started interval_sec=%d", ACCOUNT_TICK_INTERVAL)
    while not stop_event.is_set():
        try:
            await account_tick_iteration(
                pool=pool,
                now=datetime.now(timezone.utc),
                tg=tg,
            )
        except Exception:
            log.exception("account_loop.tick_failed; continuing")

        # Sleep for ACCOUNT_TICK_INTERVAL but wake up early if stop is requested.
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=ACCOUNT_TICK_INTERVAL
            )
        except asyncio.TimeoutError:
            pass

    log.info("account_loop.stopped")

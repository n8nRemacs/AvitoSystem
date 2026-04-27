"""Daily OpenRouter spend tracker.

Every ``LLMAnalyzer.put`` writes ``cost_usd`` into ``llm_analyses``;
this module sums the last 24 hours and tells the worker whether the
budget is exhausted.

Behaviour split (TZ §6 + V1_BLOCKS_TZ Block 3):
* :func:`current_spend_usd` is informational and never raises.
* :func:`check_budget` returns a tuple ``(allowed, spent, limit)`` and
  is the cheap gate the worker checks before queueing new
  ``classify_condition`` jobs.
* :func:`assert_budget` raises :class:`LLMBudgetExceeded` so the worker
  can let the exception bubble up and catch it once at the top of the
  task to emit an ``error`` notification.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.llm_analysis import LLMAnalysis

log = logging.getLogger(__name__)


class LLMBudgetExceeded(RuntimeError):
    """Raised when the rolling 24h LLM spend has reached the configured limit."""

    def __init__(self, *, spent_usd: float, limit_usd: float) -> None:
        super().__init__(
            f"OpenRouter daily budget exceeded: spent ${spent_usd:.4f} / "
            f"limit ${limit_usd:.4f}"
        )
        self.spent_usd = spent_usd
        self.limit_usd = limit_usd


async def current_spend_usd(
    sessionmaker: async_sessionmaker, *, window_hours: int = 24
) -> float:
    """Return the rolling-window total spend, or 0.0 on DB failure."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    try:
        async with sessionmaker() as session:
            stmt = select(
                func.coalesce(func.sum(LLMAnalysis.cost_usd), 0)
            ).where(LLMAnalysis.created_at >= cutoff)
            value = (await session.execute(stmt)).scalar_one_or_none()
            return float(value or 0.0)
    except Exception:  # pragma: no cover
        log.exception("llm_budget.current_spend_failed")
        return 0.0


async def check_budget(
    sessionmaker: async_sessionmaker,
    *,
    limit_usd: float,
    window_hours: int = 24,
) -> tuple[bool, float, float]:
    """Return ``(within_budget, spent, limit)``."""
    spent = await current_spend_usd(sessionmaker, window_hours=window_hours)
    return spent < limit_usd, spent, limit_usd


async def assert_budget(
    sessionmaker: async_sessionmaker,
    *,
    limit_usd: float,
    window_hours: int = 24,
) -> None:
    """Raise :class:`LLMBudgetExceeded` if the rolling spend hit the limit."""
    within, spent, limit = await check_budget(
        sessionmaker, limit_usd=limit_usd, window_hours=window_hours
    )
    if not within:
        raise LLMBudgetExceeded(spent_usd=spent, limit_usd=limit)

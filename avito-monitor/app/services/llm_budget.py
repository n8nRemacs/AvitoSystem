"""Daily OpenRouter spend tracker — stub pending new cache table.

The llm_analyses table was dropped in migration 0016_unified_criteria
(Phase 2.1). This module is now a no-op stub that always reports
spend=0 and never raises LLMBudgetExceeded until a replacement cost
tracking table is added.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

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
    """Always returns 0.0 — llm_analyses table dropped in 0016."""
    return 0.0


async def check_budget(
    sessionmaker: async_sessionmaker,
    *,
    limit_usd: float,
    window_hours: int = 24,
) -> tuple[bool, float, float]:
    """Return ``(within_budget, spent, limit)`` — always within budget."""
    return True, 0.0, limit_usd


async def assert_budget(
    sessionmaker: async_sessionmaker,
    *,
    limit_usd: float,
    window_hours: int = 24,
) -> None:
    """No-op — always within budget until replacement cost table exists."""
    pass

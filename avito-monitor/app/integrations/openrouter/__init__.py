"""OpenRouter integration — AsyncOpenAI wrapper + token pricing.

Public surface kept narrow: callers get an :class:`OpenRouterClient`
plus the :func:`estimate_cost_usd` helper. Everything else (model
catalogue, raw httpx, tokenization) is internal.
"""
from app.integrations.openrouter.client import (
    OpenRouterClient,
    OpenRouterError,
)
from app.integrations.openrouter.pricing import estimate_cost_usd

__all__ = ["OpenRouterClient", "OpenRouterError", "estimate_cost_usd"]

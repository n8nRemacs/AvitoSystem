"""Per-model price catalogue for OpenRouter.

We don't trust OpenRouter's response to embed the cost (some providers
don't fill it), so we apply our own multiplication using the table
below. Values are USD per million tokens, taken from the public
OpenRouter pricing page snapshot — keep this list short and only
include models we actually use in production prompts.

Lookup is forgiving: if a model is missing the helper returns 0.0
and logs a warning, so a stale catalogue never crashes the worker —
just understates cost until the table is updated.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


# (input_per_million_usd, output_per_million_usd)
PRICING: dict[str, tuple[float, float]] = {
    # Anthropic — primary models for V1.
    "anthropic/claude-haiku-4.5": (0.25, 1.25),
    "anthropic/claude-sonnet-4.6": (3.00, 15.00),
    "anthropic/claude-sonnet-4.7": (3.00, 15.00),
    "anthropic/claude-opus-4.6": (15.00, 75.00),
    "anthropic/claude-opus-4.7": (15.00, 75.00),
    # Backup / non-Anthropic — kept for compare/Telegram-summary fallback.
    "openai/gpt-4.1-mini": (0.40, 1.60),
    "openai/gpt-4o-mini": (0.15, 0.60),
}


def estimate_cost_usd(
    model: str, *, input_tokens: int, output_tokens: int
) -> float:
    """Return USD spent on one OpenRouter call.

    Returns 0.0 (and logs a warning once per process) for models that
    aren't in :data:`PRICING`, so missing catalogue entries don't break
    callers — they just need to update this file.
    """
    rates = PRICING.get(model)
    if rates is None:
        if model not in _WARNED_MODELS:
            log.warning("openrouter.pricing.unknown_model model=%s", model)
            _WARNED_MODELS.add(model)
        return 0.0
    in_rate, out_rate = rates
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


_WARNED_MODELS: set[str] = set()

"""Phase 2.1: price_signal features extractor.

One batched LLM call extracts battery_health + repaired_components from the
listing title + description. Returns dict mapping feature_key -> value (JSONB).

LLM failures fall back to {"battery_health": None, "repaired_components": None}
— same shape as no-mentions case. Caller upserts these as listing_features rows
with kind='price_signal' and value=<dict|null>.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import structlog

from app.services.llm_analyzer import _llm_call_json

log = structlog.get_logger(__name__)

PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "extract_price_signal.md"


async def extract_price_signal_features(
    title: str, description: str
) -> dict[str, dict | None]:
    """Extract battery_health + repaired_components from listing text.

    Returns:
        {"battery_health": <dict|None>, "repaired_components": <dict|None>}

    Never raises — LLM failures return safe nulls.
    """
    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    prompt = prompt_template.replace("{title}", title or "").replace(
        "{description}", description or ""
    )

    try:
        result = await _llm_call_json(prompt, max_tokens=600)
    except Exception as e:
        log.warning("price_signal.llm_failed", error=str(e))
        return {"battery_health": None, "repaired_components": None}

    if not isinstance(result, dict):
        log.warning("price_signal.unexpected_shape", result_type=type(result).__name__)
        return {"battery_health": None, "repaired_components": None}

    return {
        "battery_health": result.get("battery_health"),
        "repaired_components": result.get("repaired_components"),
    }

"""Phase 2.1: info_api features reader.

Pure-Python extraction from listing.parameters JSONB dict — no LLM.
Returns dict[feature_key -> value|None]. Caller upserts results as
listing_features rows with kind='info_api'.
"""

from __future__ import annotations

import re
from typing import Any


def _parse_numeric_gb(value: str | None) -> dict[str, int] | None:
    """'128 ГБ' / '256GB' / '512' → {'gb': N}, else None."""
    if not value:
        return None
    m = re.search(r"(\d+)", str(value))
    if not m:
        return None
    try:
        return {"gb": int(m.group(1))}
    except ValueError:
        return None


def read_info_api_features(parameters: dict[str, Any] | None) -> dict[str, dict | None]:
    """Read info_api features from listing.parameters.

    Args:
        parameters: listing.parameters JSONB dict (may be None or empty).

    Returns:
        {"memory_gb": <dict|None>, "color": <dict|None>, "vendor_model": <dict|None>}
    """
    if not parameters:
        return {"memory_gb": None, "color": None, "vendor_model": None}

    memory_gb = _parse_numeric_gb(parameters.get("Встроенная память"))

    color_text = parameters.get("Цвет")
    color = {"text": color_text} if color_text else None

    vendor = parameters.get("Производитель")
    model = parameters.get("Модель")
    if vendor and model:
        vendor_model = {"text": f"{vendor} {model}"}
    else:
        vendor_model = None

    return {
        "memory_gb": memory_gb,
        "color": color,
        "vendor_model": vendor_model,
    }

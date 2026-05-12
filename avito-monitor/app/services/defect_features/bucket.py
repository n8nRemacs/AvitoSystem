"""Deterministic bucketing: (features, profile_rules) → ('green'|'grey'|'red', reason)."""
from __future__ import annotations

from typing import Literal


Bucket = Literal["green", "grey", "red"]


def compute_bucket(
    features: dict[str, str],   # {feature_key: 'ok'|'defect'|'unknown'}
    rules: dict[str, str],      # {feature_key: 'green'|'red'|'ignore'}
) -> tuple[Bucket, str | None]:
    """Pure: same inputs → same outputs. See spec §8 for the truth table.

    Returns (bucket, reason_feature_key). reason is None when bucket == 'green'.
    """
    # Step 1: red-flag CONFIRMED defect → red, short-circuit
    for fkey, rule in rules.items():
        if rule == "red" and features.get(fkey) == "defect":
            return ("red", fkey)

    # Step 2: any non-ignored unknown → grey (must clarify)
    for fkey, rule in rules.items():
        if rule in ("green", "red") and features.get(fkey, "unknown") == "unknown":
            return ("grey", fkey)

    # Step 3: green-flag defect → grey (operator decides)
    for fkey, rule in rules.items():
        if rule == "green" and features.get(fkey) == "defect":
            return ("grey", fkey)

    # Step 4: clean sweep
    return ("green", None)

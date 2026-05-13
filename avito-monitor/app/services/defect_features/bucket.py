"""Deterministic bucketing: (features, profile_rules) → ('green'|'grey'|'red', reason)."""
from __future__ import annotations

from typing import Literal


Bucket = Literal["green", "grey", "red"]


def compute_bucket(
    features: dict[str, str],   # {feature_key: 'ok'|'defect'|'unknown'}
    rules: dict[str, str],      # {feature_key: 'green'|'red'|'ignore'}
) -> tuple[Bucket, str | None]:
    """Pure: same inputs → same outputs.

    Semantics (post-F2 relax):
    - Confirmed defect on a red-rule → red (short-circuit).
    - Confirmed defect on a green-rule → grey (operator decides).
    - Rule has NO feature row at all (parser didn't fill the key) → grey.
      This catches lots that never ran through the new pipeline.
    - Otherwise (every rule's feature is 'ok' or 'unknown') → green.
      Parser-emitted 'unknown' counts as not-a-defect: the LLM scanned and
      found no positive evidence of damage. Combined with active red-rule
      catching confirmed defects, green = «scanned and no defects spotted».
    """
    # Step 1: red-flag CONFIRMED defect → red, short-circuit
    for fkey, rule in rules.items():
        if rule == "red" and features.get(fkey) == "defect":
            return ("red", fkey)

    # Step 2: rule with NO feature row (parser didn't run) → grey
    for fkey, rule in rules.items():
        if rule in ("green", "red") and features.get(fkey) is None:
            return ("grey", fkey)

    # Step 3: green-flag defect → grey (operator decides)
    for fkey, rule in rules.items():
        if rule == "green" and features.get(fkey) == "defect":
            return ("grey", fkey)

    # Step 4: no confirmed defects on any rule, all rules covered by parser
    return ("green", None)

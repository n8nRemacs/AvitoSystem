"""Avito-parameters → feature state matcher.

For features that Avito itself encodes structurally (mostly locks +
display 'condition' fields), prefer the structured value over LLM
parsing of the free-text description. Returns a partial dict; features
not covered here are left for the LLM section parser.

Generous on negative — when in doubt return nothing and let the LLM
decide. Never raise.
"""
from __future__ import annotations

from typing import Any, Iterable


# value normalization helper
def _norm(v: Any) -> str:
    return str(v or "").strip().lower()


# (feature_key, avito_param_name_normalized) → ((ok_value_tokens, defect_value_tokens))
# Values matched substring-wise after _norm.
RULES: dict[tuple[str, str], tuple[tuple[str, ...], tuple[str, ...]]] = {
    ("locks.icloud_linked", "привязка к icloud"): (
        ("отвязан", "не привязан", "снят", "чист"),
        ("привязан", "залочен", "icloud locked"),
    ),
    ("locks.passcode_forgotten", "пароль"): (
        ("известен", "снят", "сброшен"),
        ("забыт", "не помню"),
    ),
}


def match_avito_parameters(
    parameters: dict[str, Any] | None,
    active_keys: Iterable[str],
) -> dict[str, dict[str, Any]]:
    """Map raw Avito parameters dict to {feature_key: {state, source, evidence}}.

    Returns only entries that were resolved (ok or defect). Unknown is
    represented by absence — caller's LLM dispatch fills the rest.
    """
    if not parameters:
        return {}
    active = set(active_keys)
    # Lower-cased copy keyed by canonical param name for case-insensitive lookup
    norm_params = {_norm(k): (k, v) for k, v in parameters.items() if v is not None}

    out: dict[str, dict[str, Any]] = {}
    for (fkey, param_name), (ok_vals, def_vals) in RULES.items():
        if fkey not in active:
            continue
        if param_name not in norm_params:
            continue
        orig_key, raw_val = norm_params[param_name]
        v = _norm(raw_val)
        state: str | None = None
        if any(token in v for token in def_vals):
            state = "defect"
        elif any(token in v for token in ok_vals):
            state = "ok"
        if state is None:
            continue
        out[fkey] = {
            "state": state,
            "source": "avito_parameters",
            "evidence": f"{orig_key}: {raw_val}",
            "confidence": None,
        }
    return out

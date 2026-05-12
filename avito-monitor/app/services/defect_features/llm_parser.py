"""Per-section LLM-based defect parser.

For each section (display / case / ...), one LLM call extracts the
state of all the requested features in a single response. Six sections
run in parallel via parse_defect_features (Task 6).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import yaml

from app.services.defect_features.taxonomy import FeatureSpec
from app.services.llm_analyzer import _llm_call_json


_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_VALID_STATES = {"ok", "defect", "unknown"}


def _build_features_listing(features: Iterable[FeatureSpec]) -> str:
    return "\n".join(
        f"- {f.key}: {f.title} ({f.expected_format})" for f in features
    )


def _render_prompt(section: str, features: Iterable[FeatureSpec],
                   title: str, description: str,
                   parameters: dict[str, Any]) -> str:
    path = _PROMPTS_DIR / f"parse_section_{section}.md"
    template = path.read_text(encoding="utf-8")
    return (
        template
        .replace("{{model}}", "iPhone")
        .replace("{{features_listing}}", _build_features_listing(features))
        .replace("{{title}}", title or "")
        .replace("{{description}}", description or "")
        .replace("{{parameters_yaml}}",
                 yaml.safe_dump(parameters or {}, allow_unicode=True))
    )


def _coerce_one(raw: Any) -> dict[str, Any]:
    """Validate one feature's LLM block, returning a normalized dict."""
    if not isinstance(raw, dict):
        return {"state": "unknown", "confidence": None, "evidence": None}
    state = raw.get("state")
    if state not in _VALID_STATES:
        state = "unknown"
    confidence = raw.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = None
    evidence = raw.get("evidence")
    if not isinstance(evidence, str):
        evidence = None
    return {"state": state, "confidence": confidence, "evidence": evidence}


async def parse_section_defects(
    *,
    section: str,
    features: list[FeatureSpec],
    title: str,
    description: str,
    parameters: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Return {feature_key: {state, confidence, evidence, source='llm'}}.

    If `features` is empty, returns {} immediately without calling LLM.
    On LLM failure: all requested features -> state='unknown', source='llm'.
    """
    if not features:
        return {}

    prompt = _render_prompt(section, features, title, description, parameters)
    try:
        result = await _llm_call_json(prompt, max_tokens=600)
    except Exception:
        return {
            f.key: {"state": "unknown", "confidence": None,
                    "evidence": None, "source": "llm"}
            for f in features
        }
    if not isinstance(result, dict):
        result = {}
    out: dict[str, dict[str, Any]] = {}
    for f in features:
        block = _coerce_one(result.get(f.key))
        block["source"] = "llm"
        out[f.key] = block
    return out

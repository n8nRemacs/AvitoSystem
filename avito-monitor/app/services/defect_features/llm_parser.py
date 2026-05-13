"""Per-section LLM-based defect parser.

For each section (display / case / ...), one LLM call extracts the
state of all the requested features in a single response. Six sections
run in parallel via parse_defect_features (Task 6).

Phase 2.1: parse_section_defects now also accepts `active_keys` (list of
feature key strings) as an alternative to `features` (list of FeatureSpec).
Results support both dict-style access (result[key]["state"]) and
attribute-style access (result[key].state) via FeatureResult.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Iterable

import yaml

from app.services.defect_features.avito_params import match_avito_parameters
from app.services.defect_features.taxonomy import SECTIONS, FeatureSpec, load_taxonomy
from app.services.llm_analyzer import _llm_call_json


_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
_VALID_STATES = {"ok", "defect", "unknown"}


class FeatureResult(dict):
    """Dict subclass that also supports attribute-style access.

    Allows both result["state"] and result.state for compatibility
    with both old tests (dict access) and new Task 6 tests (attr access).
    """

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


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


def _coerce_one(raw: Any) -> FeatureResult:
    """Validate one feature's LLM block, returning a normalized FeatureResult."""
    if not isinstance(raw, dict):
        return FeatureResult({"state": "unknown", "confidence": None, "evidence": None})
    state = raw.get("state")
    if state not in _VALID_STATES:
        state = "unknown"
    confidence = raw.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = None
    evidence = raw.get("evidence")
    if not isinstance(evidence, str):
        evidence = None
    return FeatureResult({"state": state, "confidence": confidence, "evidence": evidence})


async def parse_section_defects(
    *,
    section: str,
    features: list[FeatureSpec] | None = None,
    active_keys: list[str] | None = None,
    title: str,
    description: str,
    parameters: dict[str, Any],
) -> dict[str, FeatureResult]:
    """Return {feature_key: FeatureResult(state, confidence, evidence, source='llm')}.

    Accepts either `features` (list[FeatureSpec]) or `active_keys` (list[str]).
    When `active_keys` is provided, FeatureSpecs are resolved from taxonomy.

    If the effective features list is empty, returns {} immediately (no LLM call).
    On LLM failure: all requested features -> state='unknown', source='llm'.

    Results support both dict-style (result[key]["state"]) and attribute-style
    (result[key].state) access via FeatureResult.
    """
    # Resolve features from active_keys if provided
    if features is None and active_keys is not None:
        taxonomy_by_key = {f.key: f for f in load_taxonomy()}
        features = [taxonomy_by_key[k] for k in active_keys if k in taxonomy_by_key]
    elif features is None:
        features = []

    if not features:
        return {}

    prompt = _render_prompt(section, features, title, description, parameters)
    try:
        result = await _llm_call_json(prompt, max_tokens=600)
    except Exception:
        return {
            f.key: FeatureResult({"state": "unknown", "confidence": None,
                                  "evidence": None, "source": "llm"})
            for f in features
        }
    if not isinstance(result, dict):
        result = {}
    out: dict[str, FeatureResult] = {}
    for f in features:
        block = _coerce_one(result.get(f.key))
        block["source"] = "llm"
        out[f.key] = block
    return out


async def parse_defect_features(
    *,
    title: str,
    description: str,
    parameters: dict[str, Any] | None,
    active_keys: set[str],
) -> dict[str, dict[str, Any]]:
    """Full pipeline: Avito-params first, then LLM for the rest, parallel by section.

    `active_keys` = the subset of features the caller is interested in
    (typically `{k for k, r in profile_rules.items() if r != 'ignore'}`).
    Returns {feature_key: {state, confidence, evidence, source}} for every key
    in active_keys (state='unknown' if neither layer resolved it).
    """
    if not active_keys:
        return {}

    taxonomy_by_key = {f.key: f for f in load_taxonomy()}
    requested = {k: taxonomy_by_key[k] for k in active_keys if k in taxonomy_by_key}

    # Layer 1 — Avito structured parameters
    avito_resolved = match_avito_parameters(parameters, set(requested.keys()))

    # Layer 2 — LLM by section, for keys NOT yet resolved
    pending = {k: spec for k, spec in requested.items() if k not in avito_resolved}
    by_section: dict[str, list[FeatureSpec]] = {s: [] for s in SECTIONS}
    for spec in pending.values():
        by_section[spec.section].append(spec)

    tasks = [
        parse_section_defects(
            section=section, features=feats,
            title=title, description=description, parameters=parameters or {},
        )
        for section, feats in by_section.items() if feats
    ]
    llm_results = await asyncio.gather(*tasks) if tasks else []

    out = dict(avito_resolved)
    for partial in llm_results:
        out.update(partial)

    # Anything still missing → explicit unknown (defensive)
    for k in active_keys:
        out.setdefault(k, {"state": "unknown", "confidence": None,
                           "evidence": None, "source": "llm"})
    return out

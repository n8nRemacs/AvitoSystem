"""Pydantic result models for LLM analyses.

These are the structured outputs that come back from the LLMAnalyzer
service. Each one mirrors the JSON schema we ask the model to emit in
the corresponding ``app/prompts/<name>.md`` template, so the parser
in the analyzer can do a strict ``Model.model_validate(json.loads(...))``
without bespoke field-by-field plumbing.

Stored as the ``result`` JSONB column on ``llm_analyses`` (see
``app/db/models/llm_analysis.py``) and replayed on cache hit.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ConditionClass(str, Enum):
    """Allowed values for the condition LLM classifier (ADR-010 stage 1).

    Order is loosely "good → bad" — useful for default sort in UI.
    """

    WORKING = "working"
    BLOCKED_ICLOUD = "blocked_icloud"
    BLOCKED_ACCOUNT = "blocked_account"
    NOT_STARTING = "not_starting"
    BROKEN_SCREEN = "broken_screen"
    BROKEN_OTHER = "broken_other"
    PARTS_ONLY = "parts_only"
    UNKNOWN = "unknown"


class ConditionClassification(BaseModel):
    """Output of ``LLMAnalyzer.classify_condition``.

    Cheap text-only classifier (haiku by default). Runs on every new
    listing, so we keep the schema minimal.
    """

    condition_class: ConditionClass
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class MatchResult(BaseModel):
    """Output of ``LLMAnalyzer.match_criteria``.

    Heavyweight text+optional-vision check that only runs on alert-zone
    listings whose condition_class is in ``profile.allowed_conditions``
    (ADR-010 stage 2).
    """

    matches: bool
    score: int = Field(ge=0, le=100)
    reasoning: str = ""
    key_pros: list[str] = Field(default_factory=list)
    key_cons: list[str] = Field(default_factory=list)


class ComparisonResult(BaseModel):
    """Output of ``LLMAnalyzer.compare_to_reference`` — Price Intelligence.

    ``price_delta_estimate`` is the LLM's guess at the rouble delta
    between the competitor and the reference (positive = competitor
    is more expensive than the reference for the same condition).
    """

    comparable: bool
    score: int = Field(ge=0, le=100)
    key_advantages: list[str] = Field(default_factory=list)
    key_disadvantages: list[str] = Field(default_factory=list)
    price_delta_estimate: int | None = None


class LLMResponse(BaseModel):
    """Raw OpenRouter response normalised for analyzer consumption.

    The analyzer parses ``content`` as JSON to produce the structured
    result above; ``input_tokens`` / ``output_tokens`` / ``cost_usd``
    come straight from OpenRouter's ``usage`` field plus our local
    ``pricing.py`` lookup.
    """

    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0

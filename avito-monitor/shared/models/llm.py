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
from typing import Any, Literal

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


class CriterionFlag(BaseModel):
    """Single criterion verdict from the v2 evaluation pipeline.

    Cached per-criterion (``llm_analyses.type='criterion_eval'``) so the
    same row is reused regardless of whether the originating call was
    a per_listing batch or a per_criterion request.
    """

    flag: Literal["red", "green", "unknown"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class InfoFieldExtract(BaseModel):
    """Single info-field extraction from the v2 pipeline.

    Always produced by ``extract_info.md`` (one batch call per listing).
    The ``value`` is intentionally typed loosely (``Any``) — concrete
    schema lives in the ``criteria_templates.output_schema`` for the
    matching template and is validated downstream when needed.
    """

    value: Any | None = None
    reasoning: str = ""


class ListingEvaluation(BaseModel):
    """Aggregated bucket verdict for one (profile, listing).

    Produced after all criteria + info-fields are resolved (cache hit
    OR fresh LLM call). Persisted as a row in
    ``profile_listing_evaluations`` (with criteria/info as JSONB).
    """

    criteria: dict[str, CriterionFlag] = Field(default_factory=dict)
    info: dict[str, InfoFieldExtract] = Field(default_factory=dict)
    bucket: Literal["green", "grey", "red"]
    red_criterion_keys: list[str] = Field(default_factory=list)


class BatchEvaluationResponse(BaseModel):
    """Direct parse of ``evaluate_listing_batch.md`` output.

    Distinct from :class:`ListingEvaluation` because the LLM does NOT
    decide the bucket — Python applies the confidence threshold after
    the call, so the bucket can be re-tuned without a re-prompt.
    """

    criteria: dict[str, CriterionFlag] = Field(default_factory=dict)
    info: dict[str, Any] = Field(default_factory=dict)


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

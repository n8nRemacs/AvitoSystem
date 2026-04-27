"""LLM-driven listing analysis: classify, match, compare.

Two-stage pipeline (ADR-010):

1. ``classify_condition`` — cheap text-only classifier (haiku by default).
   Runs on every new listing in the worker (Block 4).
2. ``match_criteria`` — heavyweight check, optionally multimodal.
   Runs only when ``classify_condition`` lands the listing in
   ``profile.allowed_conditions`` AND it is in the alert price band.

A third method, ``compare_to_reference``, powers Price Intelligence
(Block 7) — comparing a competitor against the user's reference lot.

All three methods share the same skeleton:

* Compute a deterministic ``cache_key`` (sha256 of model, prompt
  version, listing id+timestamp, plus any per-method extras) and
  short-circuit through the DB cache (``llm_analyses`` table) on hit.
* On cache miss, render the Jinja2 prompt (located under
  ``app/prompts/<name>.md``), call OpenRouter, parse the JSON response
  via Pydantic, and persist the entry — so the budget tracker
  (``app/services/llm_budget.py``) can sum cost across the day.
* On parse failure, return a SAFE default (``unknown`` / ``matches=False``)
  and still persist the entry, because we never want to retry an
  upstream that's just hallucinating malformed JSON.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import jinja2

from shared.models.avito import ListingDetail
from shared.models.llm import (
    ComparisonResult,
    ConditionClass,
    ConditionClassification,
    LLMResponse,
    MatchResult,
)

log = logging.getLogger(__name__)

DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

_VERSION_RE = re.compile(r"<!--\s*version:\s*(\d+)\s*-->")
_SECTION_RE = re.compile(r"^# (system|user)\s*$", re.MULTILINE)


# ----------------------------------------------------------------------
# Protocols (so LLMAnalyzer is easy to fake in tests).
# ----------------------------------------------------------------------

class _OpenRouterProto(Protocol):
    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse: ...


class _CacheProto(Protocol):
    async def get(self, cache_key: str) -> dict[str, Any] | None: ...
    async def put(
        self,
        *,
        cache_key: str,
        type: str,
        listing_id: int | uuid.UUID | None,
        reference_id: int | uuid.UUID | None,
        model: str,
        prompt_version: str,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        latency_ms: int,
        result: dict[str, Any],
    ) -> None: ...


# ----------------------------------------------------------------------
# Prompt loading.
# ----------------------------------------------------------------------

@lru_cache(maxsize=8)
def _read_prompt(name: str, prompts_dir: str) -> tuple[str, jinja2.Template, jinja2.Template]:
    """Read ``<prompts_dir>/<name>.md`` and split into (version, system, user).

    Both system and user sections are returned as Jinja2 templates so the
    caller can pass ``{{ title }}`` / ``{{ criteria }}`` etc. directly.
    Version is the integer in the leading ``<!-- version: N -->`` marker;
    increment it whenever you change the prompt to invalidate caches.
    """
    path = Path(prompts_dir) / f"{name}.md"
    raw = path.read_text(encoding="utf-8")

    m = _VERSION_RE.search(raw)
    if not m:
        raise RuntimeError(
            f"prompt {name}.md is missing the <!-- version: N --> marker"
        )
    version = m.group(1)

    # Drop the version comment + Jinja "{# ... #}" lead so it doesn't
    # leak into the rendered system prompt.
    body = raw[m.end():]
    # Strip leading Jinja2 comment block(s).
    body = re.sub(r"^\s*\{#.*?#\}\s*", "", body, count=1, flags=re.DOTALL)

    sections: dict[str, str] = {}
    last_label: str | None = None
    last_start: int = 0
    for match in _SECTION_RE.finditer(body):
        if last_label is not None:
            sections[last_label] = body[last_start : match.start()].strip()
        last_label = match.group(1)
        last_start = match.end()
    if last_label is not None:
        sections[last_label] = body[last_start:].strip()

    if "system" not in sections or "user" not in sections:
        raise RuntimeError(
            f"prompt {name}.md must contain both '# system' and '# user' sections"
        )

    env = jinja2.Environment(
        autoescape=False,  # noqa: S701 — prompts intentionally render raw.
        keep_trailing_newline=False,
        undefined=jinja2.StrictUndefined,
    )
    return version, env.from_string(sections["system"]), env.from_string(sections["user"])


# ----------------------------------------------------------------------
# Helpers.
# ----------------------------------------------------------------------

def _listing_to_render_dict(listing: ListingDetail) -> dict[str, Any]:
    return {
        "title": listing.title,
        "price": listing.price,
        "currency": listing.currency,
        "region": listing.region,
        "description": listing.description,
        "parameters": listing.parameters or {},
    }


def _hash(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def _safe_json_loads(content: str) -> dict[str, Any] | None:
    """Parse a JSON object out of an LLM response, tolerating markdown fences.

    Some providers wrap the JSON in a fenced ``code block`` even when we
    pass ``response_format={"type": "json_object"}``. We strip the fence
    once before parsing — if the inner blob still doesn't decode, we
    give up and return None so the caller can record an "unknown" entry.
    """
    s = (content or "").strip()
    if not s:
        return None

    candidates: list[str] = []
    fence = _FENCE_RE.search(s)
    if fence:
        candidates.append(fence.group(1).strip())
    # Always try the raw string too, for providers that don't wrap.
    candidates.append(s)

    # Last-ditch: take the substring from the first '{' to the last '}'.
    first_brace = s.find("{")
    last_brace = s.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidates.append(s[first_brace : last_brace + 1])

    for cand in candidates:
        try:
            obj = json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


# ----------------------------------------------------------------------
# Analyzer.
# ----------------------------------------------------------------------

class LLMAnalyzer:
    """Cache-aware adapter that renders a prompt + calls OpenRouter."""

    def __init__(
        self,
        *,
        openrouter: _OpenRouterProto,
        cache: _CacheProto,
        default_text_model: str,
        default_vision_model: str | None = None,
        prompts_dir: Path | None = None,
    ) -> None:
        self._openrouter = openrouter
        self._cache = cache
        self._default_text_model = default_text_model
        self._default_vision_model = default_vision_model or default_text_model
        self._prompts_dir = str(prompts_dir or DEFAULT_PROMPTS_DIR)

    # ------------------------------------------------------------------
    # Cache keys
    # ------------------------------------------------------------------

    def _cache_key_for_condition(self, listing: ListingDetail, model: str) -> str:
        version, _, _ = _read_prompt("classify_condition", self._prompts_dir)
        return _hash(
            "condition",
            model,
            version,
            str(listing.id),
            listing.first_seen or "",
        )

    def _cache_key_for_match(
        self,
        listing: ListingDetail,
        model: str,
        *,
        criteria: str,
        allowed_conditions: list[str],
    ) -> str:
        version, _, _ = _read_prompt("match_listing", self._prompts_dir)
        sorted_conds = ",".join(sorted(allowed_conditions))
        return _hash(
            "match",
            model,
            version,
            str(listing.id),
            listing.first_seen or "",
            criteria,
            sorted_conds,
        )

    def _cache_key_for_compare(
        self,
        competitor: ListingDetail,
        reference: ListingDetail | dict[str, Any],
        model: str,
    ) -> str:
        version, _, _ = _read_prompt("compare_listings", self._prompts_dir)
        ref_id = (
            str(reference.id) if isinstance(reference, ListingDetail)
            else str(reference.get("id") or "")
        )
        ref_seen = (
            reference.first_seen or "" if isinstance(reference, ListingDetail)
            else str(reference.get("first_seen") or "")
        )
        return _hash(
            "compare",
            model,
            version,
            str(competitor.id),
            competitor.first_seen or "",
            ref_id,
            ref_seen,
        )

    # ------------------------------------------------------------------
    # classify_condition
    # ------------------------------------------------------------------

    async def classify_condition(
        self,
        listing: ListingDetail,
        *,
        model: str | None = None,
    ) -> ConditionClassification:
        m = model or self._default_text_model
        cache_key = self._cache_key_for_condition(listing, m)

        cached = await self._cache.get(cache_key)
        if cached is not None:
            return _condition_from_dict(cached)

        version, sys_tpl, usr_tpl = _read_prompt(
            "classify_condition", self._prompts_dir
        )
        ctx = _listing_to_render_dict(listing)
        system_prompt = sys_tpl.render(**ctx)
        user_content = usr_tpl.render(**ctx)

        resp = await self._openrouter.complete_json(
            model=m,
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=0.0,
            max_tokens=400,
        )
        parsed = _safe_json_loads(resp.content)
        if parsed is None:
            log.warning(
                "llm_analyzer.classify.bad_json listing_id=%s model=%s raw=%r",
                listing.id, m, (resp.content or "")[:400],
            )
            result = ConditionClassification(
                condition_class=ConditionClass.UNKNOWN,
                confidence=0.0,
                reasoning="LLM returned invalid JSON",
            )
        else:
            try:
                result = ConditionClassification.model_validate(parsed)
            except Exception as exc:  # pydantic ValidationError or similar
                log.warning(
                    "llm_analyzer.classify.invalid_schema listing_id=%s err=%s",
                    listing.id, exc,
                )
                result = ConditionClassification(
                    condition_class=ConditionClass.UNKNOWN,
                    confidence=0.0,
                    reasoning="LLM JSON did not match schema",
                )

        await self._cache.put(
            cache_key=cache_key,
            type="condition",
            listing_id=listing.id,
            reference_id=None,
            model=m,
            prompt_version=version,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_usd=resp.cost_usd,
            latency_ms=resp.latency_ms,
            result=result.model_dump(mode="json"),
        )
        return result

    # ------------------------------------------------------------------
    # match_criteria
    # ------------------------------------------------------------------

    async def match_criteria(
        self,
        listing: ListingDetail,
        *,
        criteria: str,
        allowed_conditions: list[str],
        condition_class: str | None = None,
        model: str | None = None,
    ) -> MatchResult:
        m = model or self._default_text_model
        cache_key = self._cache_key_for_match(
            listing, m, criteria=criteria, allowed_conditions=allowed_conditions
        )

        cached = await self._cache.get(cache_key)
        if cached is not None:
            return _match_from_dict(cached)

        version, sys_tpl, usr_tpl = _read_prompt("match_listing", self._prompts_dir)
        ctx = _listing_to_render_dict(listing)
        ctx["criteria"] = criteria
        ctx["allowed_conditions"] = allowed_conditions
        ctx["condition_class"] = condition_class
        system_prompt = sys_tpl.render(**ctx)
        user_content = usr_tpl.render(**ctx)

        resp = await self._openrouter.complete_json(
            model=m,
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=0.1,
            max_tokens=600,
        )
        parsed = _safe_json_loads(resp.content)
        if parsed is None:
            log.warning(
                "llm_analyzer.match.bad_json listing_id=%s model=%s",
                listing.id, m,
            )
            result = MatchResult(
                matches=False, score=0,
                reasoning="LLM returned invalid JSON",
                key_pros=[], key_cons=["llm_parse_error"],
            )
        else:
            try:
                result = MatchResult.model_validate(parsed)
            except Exception as exc:
                log.warning(
                    "llm_analyzer.match.invalid_schema listing_id=%s err=%s",
                    listing.id, exc,
                )
                result = MatchResult(
                    matches=False, score=0,
                    reasoning="LLM JSON did not match schema",
                    key_pros=[], key_cons=["llm_schema_error"],
                )

        await self._cache.put(
            cache_key=cache_key,
            type="match",
            listing_id=listing.id,
            reference_id=None,
            model=m,
            prompt_version=version,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_usd=resp.cost_usd,
            latency_ms=resp.latency_ms,
            result=result.model_dump(mode="json"),
        )
        return result

    # ------------------------------------------------------------------
    # compare_to_reference
    # ------------------------------------------------------------------

    async def compare_to_reference(
        self,
        competitor: ListingDetail,
        reference: ListingDetail | dict[str, Any],
        *,
        model: str | None = None,
    ) -> ComparisonResult:
        m = model or self._default_text_model
        cache_key = self._cache_key_for_compare(competitor, reference, m)

        cached = await self._cache.get(cache_key)
        if cached is not None:
            return _comparison_from_dict(cached)

        version, sys_tpl, usr_tpl = _read_prompt(
            "compare_listings", self._prompts_dir
        )
        ref_dict = (
            _listing_to_render_dict(reference)
            if isinstance(reference, ListingDetail)
            else dict(reference)
        )
        ctx = {
            "reference": ref_dict,
            "competitor": _listing_to_render_dict(competitor),
        }
        system_prompt = sys_tpl.render(**ctx)
        user_content = usr_tpl.render(**ctx)

        resp = await self._openrouter.complete_json(
            model=m,
            system_prompt=system_prompt,
            user_content=user_content,
            temperature=0.1,
            max_tokens=600,
        )
        parsed = _safe_json_loads(resp.content)
        if parsed is None:
            result = ComparisonResult(
                comparable=False, score=0,
                key_advantages=[], key_disadvantages=["llm_parse_error"],
                price_delta_estimate=None,
            )
        else:
            try:
                result = ComparisonResult.model_validate(parsed)
            except Exception:
                result = ComparisonResult(
                    comparable=False, score=0,
                    key_advantages=[], key_disadvantages=["llm_schema_error"],
                    price_delta_estimate=None,
                )

        ref_id_for_cache: int | None = None
        if isinstance(reference, ListingDetail):
            ref_id_for_cache = reference.id
        elif isinstance(reference.get("id"), int):
            ref_id_for_cache = int(reference["id"])

        await self._cache.put(
            cache_key=cache_key,
            type="compare",
            listing_id=competitor.id,
            reference_id=ref_id_for_cache,
            model=m,
            prompt_version=version,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            cost_usd=resp.cost_usd,
            latency_ms=resp.latency_ms,
            result=result.model_dump(mode="json"),
        )
        return result


# ----------------------------------------------------------------------
# Cached → typed result helpers.
# ----------------------------------------------------------------------

def _condition_from_dict(d: dict[str, Any]) -> ConditionClassification:
    try:
        return ConditionClassification.model_validate(d)
    except Exception:
        return ConditionClassification(
            condition_class=ConditionClass.UNKNOWN,
            confidence=0.0,
            reasoning="invalid cached payload",
        )


def _match_from_dict(d: dict[str, Any]) -> MatchResult:
    try:
        return MatchResult.model_validate(d)
    except Exception:
        return MatchResult(matches=False, score=0, reasoning="invalid cached payload")


def _comparison_from_dict(d: dict[str, Any]) -> ComparisonResult:
    try:
        return ComparisonResult.model_validate(d)
    except Exception:
        return ComparisonResult(
            comparable=False, score=0,
            key_advantages=[], key_disadvantages=["invalid cached payload"],
        )

"""LLM-driven listing analysis — Price Intelligence + Seller Dialog.

Two entry points:

* ``compare_to_reference`` — Price Intelligence (Block 7). Compares a
  competitor listing against the user's reference lot. Results cached in
  ``llm_analyses`` (shared resource — also used by /llm-budget and
  llm_budget.py cost tracker).

* seller_dialog module-level functions — lightweight one-shot classifiers
  for the messenger pipeline (detect_yes_selling, formulate_question, etc.).
  These skip caching: each invocation is bound to a specific dialog message.

V2 flag-based evaluator (``evaluate_listing`` / ``_eval_batch`` / etc.) was
removed in Phase 2.1 (migration 0016). The defect-features pipeline in
``app/tasks/analysis.py:evaluate_listing`` is now the single source of
bucket assignment.
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
    LLMResponse,
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
# Cached → typed result helper (used by compare_to_reference).
# ----------------------------------------------------------------------

def _comparison_from_dict(d: dict[str, Any]) -> ComparisonResult:
    try:
        return ComparisonResult.model_validate(d)
    except Exception:
        return ComparisonResult(
            comparable=False, score=0,
            key_advantages=[], key_disadvantages=["invalid cached payload"],
        )


# ----------------------------------------------------------------------
# Lightweight standalone classifiers (Seller Dialog Phase A).
#
# These don't fit the full LLMAnalyzer cache/spec machinery — they're
# tiny "single-question" classifiers used by the messenger pipeline
# (e.g. "did the seller say yes?"). They share the OpenRouter client
# but skip caching: each invocation is bound to a specific dialog
# message, and re-classifying is cheap + acceptable.
# ----------------------------------------------------------------------

async def _llm_call_json(prompt: str, max_tokens: int = 256) -> dict[str, Any]:
    """Run a one-shot classifier prompt against OpenRouter, return parsed JSON.

    Thin module-level helper for standalone classifiers (Phase A seller
    dialog and friends). NOT cached — callers using this should
    short-circuit at a higher layer if they need cache semantics.
    Raises if OpenRouter errors or the response isn't valid JSON.
    """
    # Imported lazily so tests can patch this function without dragging
    # in the OpenRouter SDK / settings on import.
    from app.config import get_settings
    from app.integrations.openrouter.client import OpenRouterClient

    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is empty — cannot call LLM")
    client = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        app_base_url=settings.app_base_url,
        app_title="Avito Monitor",
    )
    resp = await client.complete_json(
        model=settings.openrouter_default_text_model,
        system_prompt=prompt,
        user_content="",
        temperature=0.0,
        max_tokens=max_tokens,
    )
    parsed = _safe_json_loads(resp.content)
    if parsed is None:
        raise ValueError("LLM returned non-JSON content")
    return parsed


async def detect_yes_selling(seller_message: str) -> bool:
    """Decide if seller's first reply confirms item is still for sale.

    Returns True only on high-confidence (>=0.7) affirmative. Anything
    else (including LLM error / parse failure) returns False so the
    caller does NOT auto-transition the stage — operator stays in
    control of edge cases.
    """
    prompt_template = (
        DEFAULT_PROMPTS_DIR / "dialog_detect_yes_selling.md"
    ).read_text(encoding="utf-8")
    prompt = prompt_template.replace("{{seller_message}}", seller_message)

    try:
        result = await _llm_call_json(prompt, max_tokens=128)
    except Exception:
        return False
    if not isinstance(result, dict):
        return False
    is_selling = result.get("is_selling")
    confidence = result.get("confidence", 0.0)
    if not isinstance(is_selling, bool) or not isinstance(confidence, (int, float)):
        return False
    return is_selling and confidence >= 0.7


async def formulate_question(topic, history_tail: list[dict] | None = None) -> str:
    """Generate natural-sounding question text for one topic.
    Uses topic.default_phrasing as hint. Live & polite tone (Phase A greeting style).
    Returns the question string. Falls back to default_phrasing on LLM failure.
    """
    prompt_template = (
        DEFAULT_PROMPTS_DIR / "dialog_formulate_question.md"
    ).read_text(encoding="utf-8")
    history_text = "\n".join(
        f"{m.get('direction', '?')}: {m.get('text', '')}"
        for m in (history_tail or [])[-10:]
    ) or "(пусто)"
    prompt = (
        prompt_template
        .replace("{{topic_title}}", topic.title or "")
        .replace("{{topic_hint}}", topic.default_phrasing or "")
        .replace("{{topic_format}}", topic.expected_format or "text")
        .replace("{{history_tail}}", history_text)
    )
    try:
        result = await _llm_call_json(prompt, max_tokens=200)
    except Exception:
        return topic.default_phrasing or topic.title or "Подскажите, пожалуйста?"
    if isinstance(result, dict) and isinstance(result.get("question"), str):
        return result["question"].strip()
    return topic.default_phrasing or topic.title or "Подскажите, пожалуйста?"


async def parse_topic_answer(topic, seller_text: str, open_topics: list[dict] | None = None) -> dict:
    """Parse seller's reply to a specific topic question.
    Returns {"status": "answered"|"unclear"|"off_topic", "extracted": str|None, "side_topics": list}.
    On LLM failure returns unclear so caller may re-ask.
    """
    prompt_template = (
        DEFAULT_PROMPTS_DIR / "dialog_parse_topic_answer.md"
    ).read_text(encoding="utf-8")
    open_text = "\n".join(
        f"- {ot.get('key')}: {ot.get('title')}" for ot in (open_topics or [])
    ) or "(нет)"
    prompt = (
        prompt_template
        .replace("{{topic_title}}", topic.title or "")
        .replace("{{topic_hint}}", topic.default_phrasing or "")
        .replace("{{topic_format}}", topic.expected_format or "text")
        .replace("{{open_topics}}", open_text)
        .replace("{{seller_text}}", seller_text or "")
    )
    safe_default = {"status": "unclear", "extracted": None, "side_topics": []}
    try:
        result = await _llm_call_json(prompt, max_tokens=400)
    except Exception:
        return safe_default
    if not isinstance(result, dict):
        return safe_default
    status = result.get("status")
    if status not in {"answered", "unclear", "off_topic"}:
        return safe_default
    extracted = result.get("extracted")
    side = result.get("side_topics") if isinstance(result.get("side_topics"), list) else []
    side_clean = [
        {"topic_key": s["topic_key"], "extracted": s.get("extracted")}
        for s in side
        if isinstance(s, dict) and isinstance(s.get("topic_key"), str)
    ]
    return {"status": status, "extracted": extracted if isinstance(extracted, str) else None,
            "side_topics": side_clean}


async def formulate_recap(answered: list[tuple]) -> str:
    """Compose a recap message for the seller summarising what they answered.
    Falls back to deterministic template on LLM failure.
    """
    table_text = "\n".join(
        f"- {topic.title}: {answer}" for topic, answer in answered
    )
    prompt_template = (
        DEFAULT_PROMPTS_DIR / "dialog_formulate_recap.md"
    ).read_text(encoding="utf-8")
    prompt = prompt_template.replace("{{topics_table}}", table_text)

    fallback = (
        "Итак: "
        + ", ".join(f"{topic.title} — {answer}" for topic, answer in answered)
        + ". Всё правильно понял? Проверьте, пожалуйста, и подтвердите или поправьте меня."
    )
    try:
        result = await _llm_call_json(prompt, max_tokens=400)
    except Exception:
        return fallback
    if isinstance(result, dict) and isinstance(result.get("recap"), str):
        return result["recap"].strip()
    return fallback


async def parse_seller_agreement(text: str) -> dict:
    """Classify seller's reply to the recap message.
    Returns {"agreement": "yes"|"no"|"unclear", "corrections": str|None}.
    """
    prompt_template = (
        DEFAULT_PROMPTS_DIR / "dialog_parse_seller_agreement.md"
    ).read_text(encoding="utf-8")
    prompt = prompt_template.replace("{{seller_text}}", text or "")
    safe = {"agreement": "unclear", "corrections": None}
    try:
        result = await _llm_call_json(prompt, max_tokens=200)
    except Exception:
        return safe
    if not isinstance(result, dict):
        return safe
    agreement = result.get("agreement")
    if agreement not in {"yes", "no", "unclear"}:
        return safe
    corrections = result.get("corrections")
    return {
        "agreement": agreement,
        "corrections": corrections if isinstance(corrections, str) else None,
    }


@lru_cache(maxsize=256)
def _render_fragment_cached(template_text: str, params_json: str) -> str:
    if not template_text:
        return ""
    if params_json == "null":
        return template_text
    env = jinja2.Environment(
        autoescape=False,  # noqa: S701 — prompts intentionally render raw
        keep_trailing_newline=False,
        undefined=jinja2.StrictUndefined,
    )
    return env.from_string(template_text).render(
        params=json.loads(params_json)
    )


def _render_fragment(template_text: str, params: dict[str, Any] | None) -> str:
    """Pre-render a template's ``{{ params.* }}`` placeholders.

    Most fragments have no placeholders and pass through untouched —
    the cache shortcuts that path. Parametrised templates (e.g.
    ``memory_gte``) get their gb / allowed values inlined here BEFORE
    the prompt is concatenated for the LLM.
    """
    return _render_fragment_cached(
        template_text or "",
        json.dumps(params, sort_keys=True, ensure_ascii=False)
        if params is not None
        else "null",
    )

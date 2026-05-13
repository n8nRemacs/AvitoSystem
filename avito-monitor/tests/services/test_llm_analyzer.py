"""Unit tests for LLMAnalyzer.

Mocks the OpenRouter client and the DB cache layer so the analyzer's
own logic — prompt rendering, JSON parsing, cache key derivation,
fallback on bad JSON — is exercised in isolation.

Real OpenRouter calls live behind ``OPENROUTER_API_KEY`` and are
covered by ``scripts/test_llm.py`` (manual smoke), not here.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.llm_analyzer import LLMAnalyzer
from shared.models.avito import ListingDetail
from shared.models.llm import (
    ConditionClass,
    ConditionClassification,
    LLMResponse,
    MatchResult,
)


def _listing(**overrides) -> ListingDetail:
    base = {
        "id": 4823432,
        "title": "iPhone 12 Pro Max 256GB синий",
        "price": 35000,
        "description": "Рабочий, без iCloud, аккумулятор 88%.",
        "parameters": {"Память": "256 ГБ", "Цвет": "Pacific Blue"},
        "first_seen": "2026-04-20T10:00:00Z",
    }
    base.update(overrides)
    return ListingDetail(**base)


class FakeOpenRouter:
    """Stand-in for OpenRouterClient. Records calls + replays canned answers."""

    def __init__(self, replies: list[LLMResponse | Exception]) -> None:
        self._replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_content": user_content,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if not self._replies:
            raise AssertionError("FakeOpenRouter ran out of canned replies")
        nxt = self._replies.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class FakeCache:
    """In-memory stand-in for the llm_analyses DB cache."""

    def __init__(self) -> None:
        self.entries: dict[str, dict[str, Any]] = {}
        self.put_calls: list[dict[str, Any]] = []

    async def get(self, cache_key: str) -> dict[str, Any] | None:
        return self.entries.get(cache_key)

    async def put(self, **kwargs) -> None:
        self.put_calls.append(kwargs)
        self.entries[kwargs["cache_key"]] = kwargs["result"]


def _llm_response(content: str, model: str = "anthropic/claude-haiku-4.5") -> LLMResponse:
    return LLMResponse(
        content=content,
        model=model,
        input_tokens=120,
        output_tokens=42,
        cost_usd=0.00012,
        latency_ms=350,
    )


# ----------------------------------------------------------------------
# classify_condition
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classify_condition_calls_openrouter_and_returns_parsed_result():
    fake = FakeOpenRouter(
        [
            _llm_response(
                '{"condition_class": "working", "confidence": 0.9, '
                '"reasoning": "Исправно, аккумулятор 88%."}'
            )
        ]
    )
    cache = FakeCache()
    analyzer = LLMAnalyzer(openrouter=fake, cache=cache, default_text_model="anthropic/claude-haiku-4.5")

    result = await analyzer.classify_condition(_listing())

    assert isinstance(result, ConditionClassification)
    assert result.condition_class is ConditionClass.WORKING
    assert result.confidence == 0.9
    assert "аккумулятор" in result.reasoning
    # exactly one upstream call, exactly one cache write
    assert len(fake.calls) == 1
    assert len(cache.put_calls) == 1
    assert cache.put_calls[0]["type"] == "condition"
    assert cache.put_calls[0]["model"] == "anthropic/claude-haiku-4.5"


@pytest.mark.asyncio
async def test_classify_condition_short_circuits_on_cache_hit():
    fake = FakeOpenRouter([])  # empty: any call must blow up
    cache = FakeCache()
    analyzer = LLMAnalyzer(openrouter=fake, cache=cache, default_text_model="anthropic/claude-haiku-4.5")

    listing = _listing()
    cached_payload = {
        "condition_class": "blocked_icloud",
        "confidence": 0.95,
        "reasoning": "iCloud lock present",
    }
    # Pre-seed cache under the key the analyzer would compute.
    cache_key = analyzer._cache_key_for_condition(listing, "anthropic/claude-haiku-4.5")
    cache.entries[cache_key] = cached_payload

    result = await analyzer.classify_condition(listing)
    assert result.condition_class is ConditionClass.BLOCKED_ICLOUD
    assert result.confidence == 0.95
    assert fake.calls == []  # never reached upstream


@pytest.mark.asyncio
async def test_classify_condition_returns_unknown_on_garbage_json():
    fake = FakeOpenRouter([_llm_response("this is not json")])
    cache = FakeCache()
    analyzer = LLMAnalyzer(openrouter=fake, cache=cache, default_text_model="anthropic/claude-haiku-4.5")

    result = await analyzer.classify_condition(_listing())
    assert result.condition_class is ConditionClass.UNKNOWN
    assert result.confidence == 0.0
    # we still record the (failed) attempt for budget bookkeeping, but the
    # cached result is the safe ``unknown`` so future calls don't retry the
    # same garbage.
    assert len(cache.put_calls) == 1


@pytest.mark.asyncio
async def test_classify_condition_uses_explicit_model_override():
    fake = FakeOpenRouter(
        [
            _llm_response(
                '{"condition_class": "working", "confidence": 0.5, "reasoning": "ok"}',
                model="anthropic/claude-sonnet-4.7",
            )
        ]
    )
    cache = FakeCache()
    analyzer = LLMAnalyzer(openrouter=fake, cache=cache, default_text_model="anthropic/claude-haiku-4.5")

    await analyzer.classify_condition(_listing(), model="anthropic/claude-sonnet-4.7")
    assert fake.calls[0]["model"] == "anthropic/claude-sonnet-4.7"


# ----------------------------------------------------------------------
# match_criteria
# ----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_match_criteria_renders_criteria_and_allowed_conditions():
    fake = FakeOpenRouter(
        [
            _llm_response(
                '{"matches": true, "score": 85, '
                '"reasoning": "Подходит по аккумулятору и состоянию", '
                '"key_pros": ["Батарея 88%", "Без iCloud"], '
                '"key_cons": ["Лёгкие потёртости"]}'
            )
        ]
    )
    cache = FakeCache()
    analyzer = LLMAnalyzer(openrouter=fake, cache=cache, default_text_model="anthropic/claude-haiku-4.5")

    result = await analyzer.match_criteria(
        _listing(),
        criteria="аккумулятор не меньше 85%, без iCloud, без трещин",
        allowed_conditions=["working"],
    )
    assert isinstance(result, MatchResult)
    assert result.matches is True
    assert result.score == 85
    assert "Батарея 88%" in result.key_pros

    user_content = fake.calls[0]["user_content"]
    assert "аккумулятор не меньше 85%" in user_content
    assert "working" in user_content


@pytest.mark.asyncio
async def test_match_criteria_short_circuits_on_cache_hit():
    fake = FakeOpenRouter([])
    cache = FakeCache()
    analyzer = LLMAnalyzer(openrouter=fake, cache=cache, default_text_model="anthropic/claude-haiku-4.5")

    listing = _listing()
    criteria = "аккумулятор >= 85%"
    allowed = ["working"]
    cache_key = analyzer._cache_key_for_match(
        listing, "anthropic/claude-haiku-4.5", criteria=criteria, allowed_conditions=allowed
    )
    cache.entries[cache_key] = {
        "matches": False,
        "score": 25,
        "reasoning": "cached",
        "key_pros": [],
        "key_cons": ["criteria not met"],
    }

    result = await analyzer.match_criteria(
        listing, criteria=criteria, allowed_conditions=allowed
    )
    assert result.score == 25
    assert fake.calls == []


@pytest.mark.asyncio
async def test_match_criteria_returns_no_match_fallback_on_bad_json():
    fake = FakeOpenRouter([_llm_response("garbage")])
    cache = FakeCache()
    analyzer = LLMAnalyzer(openrouter=fake, cache=cache, default_text_model="anthropic/claude-haiku-4.5")

    result = await analyzer.match_criteria(
        _listing(), criteria="any", allowed_conditions=["working"]
    )
    # On parse failure we MUST NOT report ``matches=true`` — that would
    # generate spurious notifications. Default is the safe non-match.
    assert result.matches is False
    assert result.score == 0


# ----------------------------------------------------------------------
# Cache-key stability
# ----------------------------------------------------------------------

def test_cache_key_for_condition_is_stable_across_calls():
    fake = FakeOpenRouter([])
    cache = FakeCache()
    analyzer = LLMAnalyzer(openrouter=fake, cache=cache, default_text_model="anthropic/claude-haiku-4.5")

    a = analyzer._cache_key_for_condition(_listing(), "anthropic/claude-haiku-4.5")
    b = analyzer._cache_key_for_condition(_listing(), "anthropic/claude-haiku-4.5")
    assert a == b
    # Different model → different key (so model upgrades invalidate the cache).
    c = analyzer._cache_key_for_condition(_listing(), "anthropic/claude-sonnet-4.7")
    assert a != c
    # Different listing id → different key.
    d = analyzer._cache_key_for_condition(_listing(id=999999), "anthropic/claude-haiku-4.5")
    assert a != d


def test_cache_key_for_match_includes_criteria_and_conditions():
    fake = FakeOpenRouter([])
    cache = FakeCache()
    analyzer = LLMAnalyzer(openrouter=fake, cache=cache, default_text_model="anthropic/claude-haiku-4.5")

    a = analyzer._cache_key_for_match(
        _listing(), "anthropic/claude-haiku-4.5",
        criteria="x", allowed_conditions=["working"],
    )
    b = analyzer._cache_key_for_match(
        _listing(), "anthropic/claude-haiku-4.5",
        criteria="x", allowed_conditions=["working"],
    )
    assert a == b
    # Criteria change → new key.
    c = analyzer._cache_key_for_match(
        _listing(), "anthropic/claude-haiku-4.5",
        criteria="y", allowed_conditions=["working"],
    )
    assert a != c
    # Conditions order shouldn't matter (we sort).
    d = analyzer._cache_key_for_match(
        _listing(), "anthropic/claude-haiku-4.5",
        criteria="x", allowed_conditions=["broken_screen", "working"],
    )
    e = analyzer._cache_key_for_match(
        _listing(), "anthropic/claude-haiku-4.5",
        criteria="x", allowed_conditions=["working", "broken_screen"],
    )
    assert d == e

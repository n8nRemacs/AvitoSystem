"""Tests for Phase B LLM dispatchers."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_formulate_question_returns_text():
    from app.services.llm_analyzer import formulate_question

    fake_topic = type("T", (), dict(
        title="АКБ здоровье (%)",
        default_phrasing="Спроси про % АКБ",
        expected_format="percent",
    ))()

    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(return_value={"question": "Подскажите процент здоровья АКБ?"}),
    ):
        out = await formulate_question(fake_topic, history_tail=[])
    assert out == "Подскажите процент здоровья АКБ?"


@pytest.mark.asyncio
async def test_formulate_question_falls_back_on_llm_error():
    from app.services.llm_analyzer import formulate_question

    fake_topic = type("T", (), dict(
        title="АКБ здоровье (%)",
        default_phrasing="Спроси про % АКБ",
        expected_format="percent",
    ))()

    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(side_effect=RuntimeError("openrouter 503")),
    ):
        out = await formulate_question(fake_topic, history_tail=[])
    assert "АКБ" in out or "%" in out


@pytest.mark.asyncio
async def test_parse_topic_answer_extracts_and_classifies():
    from app.services.llm_analyzer import parse_topic_answer

    topic = type("T", (), dict(
        title="АКБ здоровье (%)",
        default_phrasing="х",
        expected_format="percent",
    ))()

    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(return_value={
            "status": "answered",
            "extracted": "87%",
            "side_topics": [],
        }),
    ):
        out = await parse_topic_answer(topic, "87 процентов", open_topics=[])
    assert out["status"] == "answered"
    assert out["extracted"] == "87%"
    assert out["side_topics"] == []


@pytest.mark.asyncio
async def test_parse_topic_answer_returns_unclear_on_llm_failure():
    from app.services.llm_analyzer import parse_topic_answer

    topic = type("T", (), dict(title="x", default_phrasing="", expected_format="text"))()
    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(side_effect=RuntimeError("oops")),
    ):
        out = await parse_topic_answer(topic, "blah", open_topics=[])
    assert out["status"] == "unclear"
    assert out["extracted"] is None
    assert out["side_topics"] == []


@pytest.mark.asyncio
async def test_formulate_recap_returns_message():
    from app.services.llm_analyzer import formulate_recap

    topic_a = type("T", (), dict(title="АКБ здоровье (%)"))()
    topic_b = type("T", (), dict(title="Face ID работает"))()

    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(return_value={
            "recap": "Итак: АКБ 87%, Face ID работает. Всё правильно понял? Проверьте, пожалуйста.",
        }),
    ):
        out = await formulate_recap([(topic_a, "87%"), (topic_b, "да")])
    assert "Итак" in out
    assert "АКБ" in out


@pytest.mark.asyncio
async def test_formulate_recap_falls_back_on_llm_error():
    from app.services.llm_analyzer import formulate_recap

    topic_a = type("T", (), dict(title="АКБ здоровье (%)"))()
    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(side_effect=RuntimeError("oops")),
    ):
        out = await formulate_recap([(topic_a, "87%")])
    assert "Итак" in out
    assert "АКБ" in out
    assert "правильно понял" in out.lower()


@pytest.mark.asyncio
async def test_parse_seller_agreement_yes():
    from app.services.llm_analyzer import parse_seller_agreement

    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(return_value={"agreement": "yes", "corrections": None}),
    ):
        out = await parse_seller_agreement("Да, все верно")
    assert out["agreement"] == "yes"
    assert out["corrections"] is None


@pytest.mark.asyncio
async def test_parse_seller_agreement_unclear_on_llm_failure():
    from app.services.llm_analyzer import parse_seller_agreement

    with patch(
        "app.services.llm_analyzer._llm_call_json",
        new=AsyncMock(side_effect=RuntimeError("oops")),
    ):
        out = await parse_seller_agreement("...")
    assert out["agreement"] == "unclear"
    assert out["corrections"] is None

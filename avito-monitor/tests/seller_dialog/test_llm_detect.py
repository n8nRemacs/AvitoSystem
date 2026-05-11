"""LLM classifier: does the seller's reply confirm the item is still for sale?

Mock the LLM call — we test prompt construction + result parsing, not the
model itself.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.llm_analyzer import detect_yes_selling


@pytest.mark.asyncio
async def test_detect_yes_selling_returns_true_on_affirmative():
    with patch(
        "app.services.llm_analyzer._llm_call_json", new_callable=AsyncMock
    ) as m:
        m.return_value = {"is_selling": True, "confidence": 0.95}
        result = await detect_yes_selling("Да, продается. Что хотели?")
    assert result is True


@pytest.mark.asyncio
async def test_detect_yes_selling_returns_false_on_negative():
    with patch(
        "app.services.llm_analyzer._llm_call_json", new_callable=AsyncMock
    ) as m:
        m.return_value = {"is_selling": False, "confidence": 0.9}
        result = await detect_yes_selling("Уже продал, извините")
    assert result is False


@pytest.mark.asyncio
async def test_detect_yes_selling_returns_false_on_low_confidence():
    """Below 0.7 confidence — treat as unknown (do NOT auto-transition)."""
    with patch(
        "app.services.llm_analyzer._llm_call_json", new_callable=AsyncMock
    ) as m:
        m.return_value = {"is_selling": True, "confidence": 0.5}
        result = await detect_yes_selling("Хм, ну в принципе")
    assert result is False

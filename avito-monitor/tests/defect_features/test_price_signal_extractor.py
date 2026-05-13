"""Phase 2.1 Task 7: price_signal extractor tests."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from app.services.defect_features.price_signal_extractor import extract_price_signal_features


@pytest.mark.asyncio
async def test_extracts_battery_health_percent(mocker):
    mock_llm = AsyncMock(return_value={
        "battery_health": {"percent": 87},
        "repaired_components": None,
    })
    mocker.patch(
        "app.services.defect_features.price_signal_extractor._llm_call_json",
        mock_llm,
    )

    result = await extract_price_signal_features(
        title="iPhone 12 PM 256",
        description="АКБ 87%, оригинал",
    )
    assert result["battery_health"] == {"percent": 87}
    assert result["repaired_components"] is None


@pytest.mark.asyncio
async def test_extracts_battery_health_text(mocker):
    mock_llm = AsyncMock(return_value={
        "battery_health": {"text": "новый АКБ"},
        "repaired_components": None,
    })
    mocker.patch(
        "app.services.defect_features.price_signal_extractor._llm_call_json",
        mock_llm,
    )

    result = await extract_price_signal_features(
        title="iPhone X",
        description="новый АКБ поставил недавно",
    )
    assert result["battery_health"] == {"text": "новый АКБ"}


@pytest.mark.asyncio
async def test_extracts_repaired_components_with_quality(mocker):
    mock_llm = AsyncMock(return_value={
        "battery_health": None,
        "repaired_components": {
            "items": [
                {"component": "screen", "quality": "aftermarket", "evidence": "менял экран на копию"},
                {"component": "battery", "quality": "original", "evidence": "АКБ оригинал service center"},
            ]
        },
    })
    mocker.patch(
        "app.services.defect_features.price_signal_extractor._llm_call_json",
        mock_llm,
    )

    result = await extract_price_signal_features(
        title="iPhone 11",
        description="менял экран на копию + АКБ оригинал service center",
    )
    items = result["repaired_components"]["items"]
    assert len(items) == 2
    assert items[0]["quality"] == "aftermarket"
    assert items[1]["quality"] == "original"


@pytest.mark.asyncio
async def test_returns_nulls_on_no_mentions(mocker):
    mock_llm = AsyncMock(return_value={
        "battery_health": None,
        "repaired_components": None,
    })
    mocker.patch(
        "app.services.defect_features.price_signal_extractor._llm_call_json",
        mock_llm,
    )

    result = await extract_price_signal_features(
        title="iPhone 13",
        description="продаю срочно",
    )
    assert result == {"battery_health": None, "repaired_components": None}


@pytest.mark.asyncio
async def test_llm_failure_returns_nulls(mocker):
    """Phase 2.1 Task 7: LLM error → safe fallback null values, no exception."""
    mock_llm = AsyncMock(side_effect=Exception("LLM API down"))
    mocker.patch(
        "app.services.defect_features.price_signal_extractor._llm_call_json",
        mock_llm,
    )

    result = await extract_price_signal_features(
        title="iPhone 12",
        description="АКБ 90%",
    )
    assert result == {"battery_health": None, "repaired_components": None}

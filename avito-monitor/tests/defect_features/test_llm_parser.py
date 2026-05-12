"""Per-section LLM parser tests — mock the LLM, verify parsing + safe fallback."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.defect_features.llm_parser import parse_section_defects
from app.services.defect_features.taxonomy import FeatureSpec


DISPLAY = [
    FeatureSpec(
        key="display.replaced", section="display",
        title="Дисплей менялся", default_phrasing="Менялся?",
        expected_format="yesno", severity_hint="green",
        opener_phrasing="дисплей менялся",
    ),
    FeatureSpec(
        key="display.glass_broken", section="display",
        title="Стекло разбито", default_phrasing="Стекло целое?",
        expected_format="yesno", severity_hint="green",
        opener_phrasing="разбито стекло",
    ),
]


@pytest.mark.asyncio
async def test_parses_valid_llm_response():
    fake_llm_resp = {
        "display.replaced": {"state": "ok", "confidence": 0.9, "evidence": "Оригинальный экран"},
        "display.glass_broken": {"state": "defect", "confidence": 0.85, "evidence": "есть трещина"},
    }
    with patch(
        "app.services.defect_features.llm_parser._llm_call_json",
        new=AsyncMock(return_value=fake_llm_resp),
    ):
        out = await parse_section_defects(
            section="display",
            features=DISPLAY,
            title="iPhone 12 Pro Max 256gb",
            description="Оригинальный экран, есть небольшая трещина на стекле",
            parameters={},
        )
    assert out["display.replaced"]["state"] == "ok"
    assert out["display.replaced"]["source"] == "llm"
    assert out["display.glass_broken"]["state"] == "defect"


@pytest.mark.asyncio
async def test_llm_failure_returns_unknown_for_all():
    with patch(
        "app.services.defect_features.llm_parser._llm_call_json",
        new=AsyncMock(side_effect=RuntimeError("network error")),
    ):
        out = await parse_section_defects(
            section="display", features=DISPLAY,
            title="x", description="y", parameters={},
        )
    assert out["display.replaced"]["state"] == "unknown"
    assert out["display.glass_broken"]["state"] == "unknown"


@pytest.mark.asyncio
async def test_invalid_state_value_is_clamped_to_unknown():
    bad_resp = {"display.replaced": {"state": "yes", "confidence": 0.9}}
    with patch(
        "app.services.defect_features.llm_parser._llm_call_json",
        new=AsyncMock(return_value=bad_resp),
    ):
        out = await parse_section_defects(
            section="display", features=DISPLAY,
            title="x", description="y", parameters={},
        )
    assert out["display.replaced"]["state"] == "unknown"
    assert out["display.glass_broken"]["state"] == "unknown"  # not in response


@pytest.mark.asyncio
async def test_empty_features_returns_empty_no_llm_call():
    """If caller passed no features for this section, dispatcher must NOT call LLM."""
    mock_llm = AsyncMock(return_value={})
    with patch("app.services.defect_features.llm_parser._llm_call_json", new=mock_llm):
        out = await parse_section_defects(
            section="display", features=[],
            title="x", description="y", parameters={},
        )
    assert out == {}
    mock_llm.assert_not_called()

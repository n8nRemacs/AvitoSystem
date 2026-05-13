"""Per-section LLM parser tests — mock the LLM, verify parsing + safe fallback."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.defect_features.llm_parser import parse_defect_features, parse_section_defects
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


@pytest.mark.asyncio
async def test_orchestrator_skips_features_already_resolved_by_avito_params():
    """Avito-param matcher resolved locks.icloud_linked → LLM should NOT
    be asked about it; LLM still asked about everything else."""
    captured_features = []

    async def _fake_section(*, section, features, **kw):
        captured_features.append((section, [f.key for f in features]))
        return {
            f.key: {"state": "unknown", "confidence": None,
                    "evidence": None, "source": "llm"}
            for f in features
        }

    with patch(
        "app.services.defect_features.llm_parser.parse_section_defects",
        new=_fake_section,
    ):
        out = await parse_defect_features(
            title="iPhone 12 PM",
            description="...",
            parameters={"Привязка к iCloud": "Привязан"},
            active_keys={
                "locks.icloud_linked", "display.glass_broken",
                "case.back_broken", "sensors.face_id",
            },
        )
    # Avito-resolved
    assert out["locks.icloud_linked"]["source"] == "avito_parameters"
    assert out["locks.icloud_linked"]["state"] == "defect"
    # LLM-resolved (unknown in fake)
    assert out["display.glass_broken"]["source"] == "llm"
    # LLM was NOT asked about locks.icloud_linked (already resolved by Avito)
    locks_sections = [feats for sect, feats in captured_features if sect == "locks"]
    assert all("locks.icloud_linked" not in feats for feats in locks_sections)


@pytest.mark.asyncio
async def test_orchestrator_skips_sections_with_no_active_keys():
    """If active_keys doesn't include any operability features, that
    section's LLM call must be skipped."""
    called_sections = []

    async def _fake_section(*, section, features, **kw):
        called_sections.append(section)
        return {f.key: {"state": "unknown", "confidence": None,
                        "evidence": None, "source": "llm"}
                for f in features}

    with patch(
        "app.services.defect_features.llm_parser.parse_section_defects",
        new=_fake_section,
    ):
        await parse_defect_features(
            title="x", description="y", parameters={},
            active_keys={"display.glass_broken"},
        )
    assert called_sections == ["display"]


@pytest.mark.asyncio
async def test_parser_recognizes_touch_id_defect_key(mocker):
    """Phase 2.1 Task 6: sensors section parser handles touch_id key."""
    mock_llm = AsyncMock(return_value={
        "sensors.face_id": {"state": "ok", "evidence": "Face ID работает"},
        "sensors.touch_id": {"state": "defect", "evidence": "Touch ID сломан"},
    })
    mocker.patch("app.services.defect_features.llm_parser._llm_call_json", mock_llm)

    result = await parse_section_defects(
        title="iPhone SE",
        description="Touch ID сломан, Face ID работает",
        parameters={},
        section="sensors",
        active_keys=["sensors.face_id", "sensors.touch_id"],
    )
    assert result["sensors.touch_id"].state == "defect"


@pytest.mark.asyncio
async def test_parser_recognizes_frp_and_vendor_account(mocker):
    """Phase 2.1 Task 6: locks section parser handles frp_locked + vendor_account."""
    mock_llm = AsyncMock(return_value={
        "locks.frp_locked": {"state": "defect", "evidence": "FRP блок"},
        "locks.vendor_account": {"state": "ok", "evidence": "чистый"},
    })
    mocker.patch("app.services.defect_features.llm_parser._llm_call_json", mock_llm)

    result = await parse_section_defects(
        title="Xiaomi Mi 11",
        description="Привязан к Google аккаунту",
        parameters={},
        section="locks",
        active_keys=["locks.frp_locked", "locks.vendor_account"],
    )
    assert result["locks.frp_locked"].state == "defect"


@pytest.mark.asyncio
async def test_parser_recognizes_parts_only(mocker):
    """Phase 2.1 Task 6: operability parser handles parts_only intent."""
    mock_llm = AsyncMock(return_value={
        "operability.parts_only": {"state": "defect", "evidence": "на запчасти"},
    })
    mocker.patch("app.services.defect_features.llm_parser._llm_call_json", mock_llm)

    result = await parse_section_defects(
        title="iPhone X на запчасти",
        description="Не работает, только на разбор",
        parameters={},
        section="operability",
        active_keys=["operability.parts_only"],
    )
    assert result["operability.parts_only"].state == "defect"

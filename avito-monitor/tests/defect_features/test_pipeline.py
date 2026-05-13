"""Integration-style tests for analyze_listing_features:
   parser → DB upsert → compute_bucket → bucket+reason returned.

Phase 2.1: also verifies price_signal + info_api kinds land in DB.
"""
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.db.models import ListingFeature
from app.services.defect_features.pipeline import analyze_listing_features


pytestmark = pytest.mark.asyncio


async def test_writes_features_and_returns_bucket(db_session,
                                                  sample_listing_id,
                                                  sample_profile_id):
    # Seed a red-flag rule on the profile
    from app.services.defect_features import repository
    await repository.upsert_profile_rule(
        db_session, profile_id=sample_profile_id,
        feature_key="locks.icloud_linked", rule="red",
    )

    fake_parsed = {
        "locks.icloud_linked": {"state": "defect", "source": "llm",
                                "evidence": "Привязан", "confidence": 0.9},
    }
    fake_price_signal = {"battery_health": None, "repaired_components": None}
    fake_info_api = {"memory_gb": None, "color": None, "vendor_model": None}

    with (
        patch(
            "app.services.defect_features.pipeline.parse_defect_features",
            new=AsyncMock(return_value=fake_parsed),
        ),
        patch(
            "app.services.defect_features.pipeline.extract_price_signal_features",
            new=AsyncMock(return_value=fake_price_signal),
        ),
        patch(
            "app.services.defect_features.pipeline.read_info_api_features",
            return_value=fake_info_api,
        ),
    ):
        bucket, reason = await analyze_listing_features(
            session=db_session,
            listing_id=sample_listing_id,
            profile_id=sample_profile_id,
            title="x", description="y", parameters={},
        )
    assert bucket == "red"
    assert reason == "locks.icloud_linked"
    rows = await repository.load_listing_features(db_session, sample_listing_id)
    assert rows["locks.icloud_linked"]["state"] == "defect"


async def test_no_active_rules_yields_green(db_session,
                                            sample_listing_id, sample_profile_id):
    """Profile with no rules at all → bucket=green, no LLM call."""
    with patch(
        "app.services.defect_features.pipeline.parse_defect_features",
        new=AsyncMock(),
    ) as m_parse:
        bucket, reason = await analyze_listing_features(
            session=db_session,
            listing_id=sample_listing_id,
            profile_id=sample_profile_id,
            title="x", description="y", parameters={},
        )
    assert bucket == "green"
    assert reason is None
    m_parse.assert_not_called()


async def test_all_three_kinds_land_in_db(db_session,
                                          sample_listing_id,
                                          sample_profile_id):
    """Phase 2.1: analyze_listing_features populates listing_features with
    defect + price_signal + info_api rows with correct kind discrimination."""
    from app.services.defect_features import repository

    # Seed one defect rule so pipeline doesn't short-circuit early.
    await repository.upsert_profile_rule(
        db_session, profile_id=sample_profile_id,
        feature_key="display.glass_broken", rule="red",
    )

    fake_parsed = {
        "display.glass_broken": {"state": "ok", "source": "llm",
                                  "evidence": "", "confidence": 0.95},
    }
    fake_price_signal = {
        "battery_health": {"percent": 85},
        "repaired_components": None,
    }
    fake_info_api = {
        "memory_gb": {"gb": 128},
        "color": {"text": "Чёрный"},
        "vendor_model": {"text": "Apple iPhone 12 Pro Max"},
    }

    with (
        patch(
            "app.services.defect_features.pipeline.parse_defect_features",
            new=AsyncMock(return_value=fake_parsed),
        ),
        patch(
            "app.services.defect_features.pipeline.extract_price_signal_features",
            new=AsyncMock(return_value=fake_price_signal),
        ),
        patch(
            "app.services.defect_features.pipeline.read_info_api_features",
            return_value=fake_info_api,
        ),
    ):
        bucket, reason = await analyze_listing_features(
            session=db_session,
            listing_id=sample_listing_id,
            profile_id=sample_profile_id,
            title="iPhone 12 Pro Max 256gb",
            description="АКБ 85%. Стекло целое.",
            parameters={
                "Встроенная память": "128 ГБ",
                "Цвет": "Чёрный",
                "Производитель": "Apple",
                "Модель": "iPhone 12 Pro Max",
            },
        )

    await db_session.flush()

    rows = (await db_session.execute(
        select(ListingFeature).where(ListingFeature.listing_id == sample_listing_id)
    )).scalars().all()

    by_kind: dict[str, list] = {}
    for r in rows:
        by_kind.setdefault(r.kind, []).append(r)

    assert "defect" in by_kind, "defect rows missing"
    assert "price_signal" in by_kind, "price_signal rows missing"
    assert "info_api" in by_kind, "info_api rows missing"

    # Spot-check defect row
    defect_row = next(r for r in by_kind["defect"]
                      if r.feature_key == "display.glass_broken")
    assert defect_row.state == "ok"
    assert defect_row.source == "llm"

    # Spot-check price_signal: battery_health has value, repaired_components is None
    bh = next(r for r in by_kind["price_signal"] if r.feature_key == "battery_health")
    assert bh.state is None  # non-defect rows have no state
    assert bh.value == {"percent": 85}

    rc = next(r for r in by_kind["price_signal"] if r.feature_key == "repaired_components")
    assert rc.value is None

    # Spot-check info_api: memory_gb
    mem = next(r for r in by_kind["info_api"] if r.feature_key == "memory_gb")
    assert mem.value == {"gb": 128}
    assert mem.state is None

    # bucket is still determined by defect-only (display.glass_broken=ok → green)
    assert bucket == "green"

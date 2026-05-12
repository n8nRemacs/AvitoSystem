"""Integration-style tests for analyze_listing_features:
   parser → DB upsert → compute_bucket → bucket+reason returned."""
from unittest.mock import AsyncMock, patch

import pytest

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
    with patch(
        "app.services.defect_features.pipeline.parse_defect_features",
        new=AsyncMock(return_value=fake_parsed),
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

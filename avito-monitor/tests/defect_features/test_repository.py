"""Smoke tests for SQLAlchemy models — table names, columns, constraints."""
from app.db.models import ListingFeature, ProfileFeatureRule


def test_listing_feature_table_name():
    assert ListingFeature.__tablename__ == "listing_features"


def test_listing_feature_required_columns():
    cols = {c.name for c in ListingFeature.__table__.columns}
    assert {"id", "listing_id", "feature_key", "state",
            "confidence", "source", "evidence", "parsed_at"} <= cols


def test_listing_feature_unique_constraint():
    constraints = ListingFeature.__table__.constraints
    uniq = [c for c in constraints if getattr(c, "name", "") ==
            "uq_listing_features_listing_key"]
    assert len(uniq) == 1


def test_profile_feature_rule_table_name():
    assert ProfileFeatureRule.__tablename__ == "profile_feature_rules"


def test_profile_feature_rule_required_columns():
    cols = {c.name for c in ProfileFeatureRule.__table__.columns}
    assert {"id", "profile_id", "feature_key", "rule", "updated_at"} <= cols


# ---------------------------------------------------------------------------
# Repository helpers — exercised against an in-memory SQLite via the
# conftest fixture `db_session`.
# ---------------------------------------------------------------------------
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.defect_features import repository


@pytest.mark.asyncio
async def test_upsert_listing_features_inserts_new(db_session: AsyncSession,
                                                   sample_listing_id):
    await repository.upsert_listing_features(
        db_session,
        listing_id=sample_listing_id,
        features={
            "locks.icloud_linked": {"state": "defect", "source": "avito_parameters",
                                    "evidence": "Привязка: Привязан", "confidence": None},
        },
    )
    rows = await repository.load_listing_features(db_session, sample_listing_id)
    assert rows["locks.icloud_linked"]["state"] == "defect"
    assert rows["locks.icloud_linked"]["source"] == "avito_parameters"


@pytest.mark.asyncio
async def test_upsert_listing_features_updates_existing(db_session, sample_listing_id):
    """Second upsert with same key overrides the row (last-write-wins)."""
    await repository.upsert_listing_features(
        db_session,
        listing_id=sample_listing_id,
        features={"locks.icloud_linked": {"state": "ok", "source": "llm",
                                          "evidence": None, "confidence": 0.8}},
    )
    await repository.upsert_listing_features(
        db_session,
        listing_id=sample_listing_id,
        features={"locks.icloud_linked": {"state": "defect", "source": "seller_dialog",
                                          "evidence": "Продавец сказал привязан",
                                          "confidence": 0.95}},
    )
    rows = await repository.load_listing_features(db_session, sample_listing_id)
    assert rows["locks.icloud_linked"]["state"] == "defect"
    assert rows["locks.icloud_linked"]["source"] == "seller_dialog"


@pytest.mark.asyncio
async def test_load_profile_rules(db_session, sample_profile_id):
    await repository.upsert_profile_rule(
        db_session, profile_id=sample_profile_id,
        feature_key="locks.icloud_linked", rule="red",
    )
    rules = await repository.load_profile_rules(db_session, sample_profile_id)
    assert rules["locks.icloud_linked"] == "red"


@pytest.mark.asyncio
async def test_active_keys_excludes_ignore(db_session, sample_profile_id):
    await repository.upsert_profile_rule(db_session, profile_id=sample_profile_id,
                                         feature_key="locks.icloud_linked", rule="red")
    await repository.upsert_profile_rule(db_session, profile_id=sample_profile_id,
                                         feature_key="sensors.truetone", rule="ignore")
    active = await repository.load_active_feature_keys(db_session, sample_profile_id)
    assert "locks.icloud_linked" in active
    assert "sensors.truetone" not in active

"""Smoke tests for SQLAlchemy models — table names, columns, constraints."""
from app.db.models import ListingFeature, ProfileFeatureRule


def test_listing_feature_table_name():
    assert ListingFeature.__tablename__ == "listing_features"


def test_listing_feature_required_columns():
    cols = {c.name for c in ListingFeature.__table__.columns}
    assert {"id", "listing_id", "feature_key", "kind", "state", "value",
            "confidence", "source", "evidence", "parsed_at"} <= cols


def test_listing_feature_unique_constraint():
    constraints = ListingFeature.__table__.constraints
    uniq = [c for c in constraints if getattr(c, "name", "") ==
            "uq_listing_features_listing_key"]
    assert len(uniq) == 1


def test_listing_feature_kind_not_nullable():
    """kind column must be NOT NULL (required by Phase 2.1 schema)."""
    kind_col = ListingFeature.__table__.columns["kind"]
    assert not kind_col.nullable


def test_listing_feature_state_nullable():
    """state is now nullable — non-defect rows (price_signal/info_api) omit it."""
    state_col = ListingFeature.__table__.columns["state"]
    assert state_col.nullable


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
        sample_listing_id,
        [
            {"feature_key": "locks.icloud_linked", "kind": "defect",
             "state": "defect", "source": "avito_parameters",
             "evidence": "Привязка: Привязан", "confidence": None},
        ],
    )
    rows = await repository.load_listing_features(db_session, sample_listing_id)
    assert rows["locks.icloud_linked"]["state"] == "defect"
    assert rows["locks.icloud_linked"]["source"] == "avito_parameters"
    assert rows["locks.icloud_linked"]["kind"] == "defect"


@pytest.mark.asyncio
async def test_upsert_listing_features_updates_existing(db_session, sample_listing_id):
    """Second upsert with same key overrides the row (last-write-wins)."""
    await repository.upsert_listing_features(
        db_session,
        sample_listing_id,
        [{"feature_key": "locks.icloud_linked", "kind": "defect",
          "state": "ok", "source": "llm", "evidence": None, "confidence": 0.8}],
    )
    await repository.upsert_listing_features(
        db_session,
        sample_listing_id,
        [{"feature_key": "locks.icloud_linked", "kind": "defect",
          "state": "defect", "source": "seller_dialog",
          "evidence": "Продавец сказал привязан", "confidence": 0.95}],
    )
    rows = await repository.load_listing_features(db_session, sample_listing_id)
    assert rows["locks.icloud_linked"]["state"] == "defect"
    assert rows["locks.icloud_linked"]["source"] == "seller_dialog"


@pytest.mark.asyncio
async def test_upsert_listing_features_price_signal_kind(db_session, sample_listing_id):
    """Phase 2.1: price_signal rows have kind='price_signal', value=dict, state=None."""
    await repository.upsert_listing_features(
        db_session,
        sample_listing_id,
        [
            {"feature_key": "battery_health", "kind": "price_signal",
             "value": {"percent": 91}},
            {"feature_key": "repaired_components", "kind": "price_signal",
             "value": None},
        ],
    )
    rows = await repository.load_listing_features(db_session, sample_listing_id)

    bh = rows["battery_health"]
    assert bh["kind"] == "price_signal"
    assert bh["state"] is None
    assert bh["value"] == {"percent": 91}

    rc = rows["repaired_components"]
    assert rc["kind"] == "price_signal"
    assert rc["value"] is None


@pytest.mark.asyncio
async def test_upsert_listing_features_info_api_kind(db_session, sample_listing_id):
    """Phase 2.1: info_api rows have kind='info_api', value=dict, state=None."""
    await repository.upsert_listing_features(
        db_session,
        sample_listing_id,
        [
            {"feature_key": "memory_gb", "kind": "info_api", "value": {"gb": 256}},
            {"feature_key": "color", "kind": "info_api", "value": {"text": "Space Gray"}},
            {"feature_key": "vendor_model", "kind": "info_api",
             "value": {"text": "Apple iPhone 13 Pro"}},
        ],
    )
    rows = await repository.load_listing_features(db_session, sample_listing_id)

    mem = rows["memory_gb"]
    assert mem["kind"] == "info_api"
    assert mem["state"] is None
    assert mem["value"] == {"gb": 256}

    col = rows["color"]
    assert col["value"] == {"text": "Space Gray"}


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

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

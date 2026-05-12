"""Tests for the defect-feature taxonomy loader."""
from app.services.defect_features.taxonomy import (
    load_taxonomy,
    SECTIONS,
    FeatureSpec,
)


def test_load_taxonomy_returns_all_22_features():
    """The yaml must define exactly 22 defect features in 6 categories."""
    features = load_taxonomy()
    assert len(features) == 22
    assert all(isinstance(f, FeatureSpec) for f in features)


def test_taxonomy_covers_all_sections():
    """Every section in SECTIONS must have at least one feature."""
    features = load_taxonomy()
    by_section = {s: 0 for s in SECTIONS}
    for f in features:
        assert f.section in SECTIONS, f"unknown section: {f.section}"
        by_section[f.section] += 1
    assert all(c >= 1 for c in by_section.values()), by_section


def test_keys_are_dotted_section_first():
    features = load_taxonomy()
    for f in features:
        assert f.key.startswith(f"{f.section}."), f.key


def test_icloud_is_red_flag_hint():
    """icloud_linked should default to red-flag (auto-reject hint)."""
    feats = {f.key: f for f in load_taxonomy()}
    assert "locks.icloud_linked" in feats
    assert feats["locks.icloud_linked"].severity_hint == "red"


def test_each_feature_has_required_fields():
    for f in load_taxonomy():
        assert f.key and f.title and f.section
        assert f.severity_hint in {"red", "green", "info"}
        assert f.expected_format in {"yesno", "text"}
        assert f.opener_phrasing

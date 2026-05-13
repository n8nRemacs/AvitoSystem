"""Tests for the defect-feature taxonomy loader."""
import textwrap

import pytest

from app.services.defect_features.taxonomy import (
    load_taxonomy,
    SECTIONS,
    FeatureSpec,
)
from app.services.defect_features import taxonomy as tmod


def test_taxonomy_returns_31_features_total():
    """Phase 2.1: 22 existing defects + 4 new defects + 2 price_signal + 3 info_api = 31."""
    features = load_taxonomy()
    assert len(features) == 31
    assert all(isinstance(f, FeatureSpec) for f in features)


def test_taxonomy_covers_all_sections():
    """Every section in SECTIONS must have at least one defect feature."""
    features = load_taxonomy()
    defect_features = [f for f in features if f.kind == "defect"]
    by_section = {s: 0 for s in SECTIONS}
    for f in defect_features:
        assert f.section in SECTIONS, f"unknown section: {f.section}"
        by_section[f.section] += 1
    assert all(c >= 1 for c in by_section.values()), by_section


def test_keys_are_dotted_section_first():
    features = load_taxonomy()
    for f in features:
        if f.kind == "defect":
            assert f.key.startswith(f"{f.section}."), f.key


def test_icloud_is_red_flag_hint():
    """icloud_linked should default to red-flag (auto-reject hint)."""
    feats = {f.key: f for f in load_taxonomy()}
    assert "locks.icloud_linked" in feats
    assert feats["locks.icloud_linked"].severity_hint == "red"


def test_each_defect_feature_has_required_fields():
    for f in load_taxonomy():
        assert f.key and f.title
        if f.kind == "defect":
            assert f.section
            assert f.severity_hint in {"red", "green", "info"}
            assert f.expected_format in {"yesno", "text"}
            assert f.opener_phrasing


def _patch_yaml(monkeypatch, tmp_path, content: str):
    """Helper: write bad yaml to tmp + point loader at it + clear cache."""
    p = tmp_path / "dialog_topics.yaml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    monkeypatch.setattr(tmod, "_YAML_PATH", p)
    tmod.load_taxonomy.cache_clear()


def test_duplicate_keys_raises(monkeypatch, tmp_path):
    _patch_yaml(monkeypatch, tmp_path, """
        - key: display.glass_broken
          section: display
          title: A
          default_phrasing: x
          expected_format: yesno
          severity_hint: green
          opener_phrasing: x
        - key: display.glass_broken
          section: display
          title: B
          default_phrasing: x
          expected_format: yesno
          severity_hint: green
          opener_phrasing: x
    """)
    with pytest.raises(ValueError, match="duplicate feature keys"):
        tmod.load_taxonomy()
    tmod.load_taxonomy.cache_clear()  # don't pollute next test


def test_unknown_section_raises(monkeypatch, tmp_path):
    _patch_yaml(monkeypatch, tmp_path, """
        - key: display.glass_broken
          section: oopsie
          title: A
          default_phrasing: x
          expected_format: yesno
          severity_hint: green
          opener_phrasing: x
    """)
    with pytest.raises(ValueError, match="unknown sections"):
        tmod.load_taxonomy()
    tmod.load_taxonomy.cache_clear()


def test_unknown_kind_raises(monkeypatch, tmp_path):
    """Phase 2.1: invalid kind values are rejected at load time."""
    _patch_yaml(monkeypatch, tmp_path, """
        - key: display.glass_broken
          kind: bogus
          section: display
          title: A
          default_phrasing: x
          expected_format: yesno
          severity_hint: green
          opener_phrasing: x
    """)
    with pytest.raises(ValueError, match="unknown kind"):
        tmod.load_taxonomy()
    tmod.load_taxonomy.cache_clear()


# ---------- Phase 2.1 tests ----------

def test_taxonomy_kind_distribution():
    """Phase 2.1: correct kind distribution per spec §5."""
    features = load_taxonomy()
    by_kind = {}
    for f in features:
        by_kind[f.kind] = by_kind.get(f.kind, 0) + 1
    assert by_kind == {"defect": 26, "price_signal": 2, "info_api": 3}


def test_new_defect_keys_present():
    """Phase 2.1: 4 new defect keys added."""
    features = load_taxonomy()
    keys = {f.key for f in features}
    assert "sensors.touch_id" in keys
    assert "locks.frp_locked" in keys
    assert "locks.vendor_account" in keys
    assert "operability.parts_only" in keys


def test_price_signal_features_present():
    """Phase 2.1: price_signal kind features."""
    features = [f for f in load_taxonomy() if f.kind == "price_signal"]
    keys = {f.key for f in features}
    assert keys == {"battery_health", "repaired_components"}


def test_info_api_features_present():
    """Phase 2.1: info_api kind features."""
    features = [f for f in load_taxonomy() if f.kind == "info_api"]
    keys = {f.key for f in features}
    assert keys == {"memory_gb", "color", "vendor_model"}


def test_load_defect_features_filters_by_kind():
    """Phase 2.1: load_defect_features() returns only kind=defect."""
    from app.services.defect_features.taxonomy import load_defect_features
    features = load_defect_features()
    assert len(features) == 26
    assert all(f.kind == "defect" for f in features)

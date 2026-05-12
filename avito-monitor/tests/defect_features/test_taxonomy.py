"""Tests for the defect-feature taxonomy loader."""
import textwrap

import pytest

from app.services.defect_features.taxonomy import (
    load_taxonomy,
    SECTIONS,
    FeatureSpec,
)
from app.services.defect_features import taxonomy as tmod


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

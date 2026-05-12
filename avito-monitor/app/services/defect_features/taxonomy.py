"""Defect-feature taxonomy: load 22 features from yaml into FeatureSpec dataclasses.

The taxonomy is shared by parser, bucketer and UI — single source of truth.
Loader is cached in process (taxonomy doesn't change at runtime).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml


SECTIONS = ("display", "case", "locks", "sensors", "charging", "operability")

SeverityHint = Literal["red", "green", "info"]
FeatureFormat = Literal["yesno", "text"]


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    section: str
    title: str
    default_phrasing: str
    expected_format: FeatureFormat
    severity_hint: SeverityHint
    opener_phrasing: str


_YAML_PATH = Path(__file__).parent.parent.parent / "data" / "dialog_topics.yaml"


@lru_cache(maxsize=1)
def load_taxonomy() -> tuple[FeatureSpec, ...]:
    """Read app/data/dialog_topics.yaml and return tuple of FeatureSpec.

    Fail-fast on duplicate keys or unknown sections so downstream
    consumers (parser, bucketer) can trust the data.
    """
    raw = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8"))
    specs = tuple(
        FeatureSpec(
            key=item["key"],
            section=item["section"],
            title=item["title"],
            default_phrasing=item["default_phrasing"],
            expected_format=item["expected_format"],
            severity_hint=item["severity_hint"],
            opener_phrasing=item["opener_phrasing"],
        )
        for item in raw
    )
    # Validators
    keys = [s.key for s in specs]
    if len(keys) != len(set(keys)):
        from collections import Counter
        dupes = sorted(k for k, c in Counter(keys).items() if c > 1)
        raise ValueError(f"duplicate feature keys in dialog_topics.yaml: {dupes}")
    bad_sections = sorted({s.section for s in specs} - set(SECTIONS))
    if bad_sections:
        raise ValueError(
            f"unknown sections in dialog_topics.yaml: {bad_sections} "
            f"(allowed: {list(SECTIONS)})"
        )
    return specs

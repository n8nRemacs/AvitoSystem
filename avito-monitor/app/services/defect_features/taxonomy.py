"""Defect-feature taxonomy: load features from yaml into FeatureSpec dataclasses.

The taxonomy is shared by parser, bucketer and UI — single source of truth.
Loader is cached in process (taxonomy doesn't change at runtime).

Phase 2.1: extended from 22 → 31 features with 'kind' discriminator:
  - defect (26): original 22 + 4 new (touch_id, frp_locked, vendor_account, parts_only)
  - price_signal (2): battery_health, repaired_components
  - info_api (3): memory_gb, color, vendor_model
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Union

import yaml


SECTIONS = ("display", "case", "locks", "sensors", "charging", "operability")

SeverityHint = Literal["red", "green", "info"]
FeatureFormat = Literal["yesno", "text"]
FeatureKind = Literal["defect", "price_signal", "info_api"]

_VALID_KINDS = {"defect", "price_signal", "info_api"}


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    title: str
    kind: FeatureKind = "defect"
    # defect-only fields (None for price_signal / info_api)
    section: Optional[str] = None
    default_phrasing: Optional[str] = None
    expected_format: Optional[FeatureFormat] = None
    severity_hint: Optional[SeverityHint] = None
    opener_phrasing: Optional[str] = None
    # price_signal / info_api fields
    prompt_fragment: Optional[str] = None
    # info_api fields
    api_path: Optional[Union[str, list[str]]] = None
    parser: Optional[str] = None


_YAML_PATH = Path(__file__).parent.parent.parent / "data" / "dialog_topics.yaml"


@functools.lru_cache(maxsize=1)
def load_taxonomy() -> tuple[FeatureSpec, ...]:
    """Read app/data/dialog_topics.yaml and return tuple of FeatureSpec.

    Fail-fast on duplicate keys or unknown sections (for defect kind) so
    downstream consumers (parser, bucketer) can trust the data.
    """
    raw = yaml.safe_load(_YAML_PATH.read_text(encoding="utf-8"))
    specs_list: list[FeatureSpec] = []
    for item in raw:
        kind = item.get("kind", "defect")
        if kind not in _VALID_KINDS:
            raise ValueError(
                f"unknown kind {kind!r} in dialog_topics.yaml for key {item.get('key')!r} "
                f"(allowed: {sorted(_VALID_KINDS)})"
            )
        specs_list.append(
            FeatureSpec(
                key=item["key"],
                title=item["title"],
                kind=kind,
                section=item.get("section"),
                default_phrasing=item.get("default_phrasing"),
                expected_format=item.get("expected_format"),
                severity_hint=item.get("severity_hint"),
                opener_phrasing=item.get("opener_phrasing"),
                prompt_fragment=item.get("prompt_fragment"),
                api_path=item.get("api_path"),
                parser=item.get("parser"),
            )
        )
    specs = tuple(specs_list)

    # Validator: duplicate keys
    keys = [s.key for s in specs]
    if len(keys) != len(set(keys)):
        from collections import Counter
        dupes = sorted(k for k, c in Counter(keys).items() if c > 1)
        raise ValueError(f"duplicate feature keys in dialog_topics.yaml: {dupes}")

    # Validator: unknown sections (defect kind only)
    defect_sections = {s.section for s in specs if s.kind == "defect" and s.section}
    bad_sections = sorted(defect_sections - set(SECTIONS))
    if bad_sections:
        raise ValueError(
            f"unknown sections in dialog_topics.yaml: {bad_sections} "
            f"(allowed: {list(SECTIONS)})"
        )
    return specs


def load_defect_features() -> tuple[FeatureSpec, ...]:
    """Return only kind=defect features (26 in Phase 2.1).

    Not cached at this layer — load_taxonomy() is cached, and filtering 31 items
    is trivial. Avoids stale-cache risk if tests patch _YAML_PATH and only call
    load_taxonomy.cache_clear() (helper caches wouldn't invalidate).
    """
    return tuple(f for f in load_taxonomy() if f.kind == "defect")


def load_price_signal_features() -> tuple[FeatureSpec, ...]:
    """Return only kind=price_signal features (2 in Phase 2.1)."""
    return tuple(f for f in load_taxonomy() if f.kind == "price_signal")


def load_info_api_features() -> tuple[FeatureSpec, ...]:
    """Return only kind=info_api features (3 in Phase 2.1)."""
    return tuple(f for f in load_taxonomy() if f.kind == "info_api")

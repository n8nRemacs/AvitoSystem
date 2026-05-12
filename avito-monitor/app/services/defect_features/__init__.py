"""Defect-feature analyzer package — taxonomy, parser, bucketing."""
from app.services.defect_features.taxonomy import (
    FeatureSpec,
    SECTIONS,
    load_taxonomy,
)

__all__ = ["FeatureSpec", "SECTIONS", "load_taxonomy"]

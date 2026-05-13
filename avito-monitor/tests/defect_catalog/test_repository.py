"""Tests for defect_catalog repository — Tasks 7, 8, 9."""
from __future__ import annotations

import uuid
import pytest
from app.services.defect_catalog.repository import validate_slug


# ---------------------------------------------------------------------------
# Task 7: slug validator
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("good", ["icloud_linked", "iphone_12_pro_max", "x", "abc_123"])
def test_validate_slug_accepts_snake_case(good):
    validate_slug(good)  # no exception


@pytest.mark.parametrize("bad", ["", "WithCaps", "with space", "with-dash", "лат", "_leading"])
def test_validate_slug_rejects_invalid(bad):
    with pytest.raises(ValueError, match="slug"):
        validate_slug(bad)

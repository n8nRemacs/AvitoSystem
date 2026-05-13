"""CRUD + invariants for feature_nodes / device_nodes / device_feature_bindings."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_slug(slug: str) -> None:
    """Slug must be ^[a-z][a-z0-9_]*$ (snake-case, starting with a letter)."""
    if not _SLUG_RE.match(slug):
        raise ValueError(
            f"Invalid slug {slug!r}: must match ^[a-z][a-z0-9_]*$"
        )

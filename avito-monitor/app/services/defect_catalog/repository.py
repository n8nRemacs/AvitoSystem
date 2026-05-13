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


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class FeatureNodeRow:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    kind: str
    slug: str
    title: str
    sort_order: int
    prompt_hint: str | None


def _row_to_fn(row) -> FeatureNodeRow:
    return FeatureNodeRow(
        id=uuid.UUID(str(row.id)),
        parent_id=uuid.UUID(str(row.parent_id)) if row.parent_id else None,
        kind=row.kind,
        slug=row.slug,
        title=row.title,
        sort_order=row.sort_order,
        prompt_hint=row.prompt_hint,
    )


# ---------------------------------------------------------------------------
# CRUD — feature_nodes
# ---------------------------------------------------------------------------

async def create_feature_node(
    session: AsyncSession,
    *,
    parent_id: uuid.UUID | None,
    kind: str,
    slug: str,
    title: str,
    prompt_hint: str | None = None,
    sort_order: int = 0,
) -> uuid.UUID:
    validate_slug(slug)
    if kind not in ("node", "defect"):
        raise ValueError(f"Invalid kind {kind!r}")
    nid = uuid.uuid4()
    await session.execute(
        text("""
            INSERT INTO feature_nodes
                (id, parent_id, kind, slug, title, sort_order, prompt_hint)
            VALUES (:id, :pid, :kind, :slug, :title, :sort, :hint)
        """),
        {
            "id": str(nid),
            "pid": str(parent_id) if parent_id else None,
            "kind": kind,
            "slug": slug,
            "title": title,
            "sort": sort_order,
            "hint": prompt_hint,
        },
    )
    await session.commit()
    return nid


async def get_feature_node(
    session: AsyncSession, nid: uuid.UUID
) -> FeatureNodeRow | None:
    row = (
        await session.execute(
            text("SELECT * FROM feature_nodes WHERE id = :id"),
            {"id": str(nid)},
        )
    ).first()
    return _row_to_fn(row) if row else None


async def list_feature_children(
    session: AsyncSession, parent_id: uuid.UUID | None
) -> list[FeatureNodeRow]:
    if parent_id is None:
        rows = (
            await session.execute(
                text(
                    "SELECT * FROM feature_nodes"
                    " WHERE parent_id IS NULL"
                    " ORDER BY sort_order, slug"
                )
            )
        ).all()
    else:
        rows = (
            await session.execute(
                text(
                    "SELECT * FROM feature_nodes"
                    " WHERE parent_id = :pid"
                    " ORDER BY sort_order, slug"
                ),
                {"pid": str(parent_id)},
            )
        ).all()
    return [_row_to_fn(r) for r in rows]

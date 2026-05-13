"""Resolve applicable defects for a target device via inheritance walk-up."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ResolvedBinding:
    binding_id: uuid.UUID
    feature_node_id: uuid.UUID
    feature_path: list[str]
    defect_action: Literal["block", "info"]
    unknown_action: Literal["ask", "skip"]
    inherited_from: uuid.UUID | None


async def _walk_up_device(session: AsyncSession, start_id: uuid.UUID) -> list[uuid.UUID]:
    """Return [target, parent, ..., root]."""
    out: list[uuid.UUID] = []
    cursor: uuid.UUID | None = start_id
    while cursor is not None:
        out.append(cursor)
        row = (await session.execute(
            text("SELECT parent_id FROM device_nodes WHERE id = :id"),
            {"id": str(cursor)},
        )).first()
        if row is None or row.parent_id is None:
            break
        cursor = uuid.UUID(str(row.parent_id))
    return out


async def _feature_path(session: AsyncSession, leaf_id: uuid.UUID) -> list[str]:
    """Walk feature tree up; return titles ordered root → leaf."""
    titles: list[str] = []
    cursor: uuid.UUID | None = leaf_id
    while cursor is not None:
        row = (await session.execute(
            text("SELECT title, parent_id FROM feature_nodes WHERE id = :id"),
            {"id": str(cursor)},
        )).first()
        if row is None:
            break
        titles.append(row.title)
        cursor = uuid.UUID(str(row.parent_id)) if row.parent_id else None
    return list(reversed(titles))


async def resolve_applicable_defects(
    session: AsyncSession, target_device_node_id: uuid.UUID,
) -> list[ResolvedBinding]:
    """Walk device tree up from target; for each feature take nearest-ancestor binding.
    Drop disabled. Sort by feature_path."""
    ancestors = await _walk_up_device(session, target_device_node_id)
    resolved: dict[uuid.UUID, tuple[uuid.UUID, uuid.UUID, str, str, bool]] = {}
    for anc in ancestors:
        rows = (await session.execute(
            text("""
                SELECT id, feature_node_id, defect_action, unknown_action, disabled
                FROM device_feature_bindings WHERE device_node_id = :dn
            """),
            {"dn": str(anc)},
        )).all()
        for r in rows:
            fnid = uuid.UUID(str(r.feature_node_id))
            if fnid in resolved:
                continue
            resolved[fnid] = (
                uuid.UUID(str(r.id)), anc,
                r.defect_action, r.unknown_action, bool(r.disabled),
            )

    out: list[ResolvedBinding] = []
    for fnid, (bid, source, da, ua, dis) in resolved.items():
        if dis:
            continue
        path = await _feature_path(session, fnid)
        out.append(ResolvedBinding(
            binding_id=bid, feature_node_id=fnid, feature_path=path,
            defect_action=da, unknown_action=ua,
            inherited_from=(None if source == target_device_node_id else source),
        ))
    out.sort(key=lambda r: r.feature_path)
    return out

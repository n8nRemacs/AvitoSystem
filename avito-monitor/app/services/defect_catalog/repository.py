"""CRUD + invariants for feature_nodes / device_nodes / device_feature_bindings."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _now_expr(session: AsyncSession) -> str:
    """SQL expression for current timestamp, dialect-aware.

    SQLite uses ``datetime('now')``, Postgres uses ``now()``.
    """
    return "now()" if session.bind.dialect.name != "sqlite" else "datetime('now')"


def validate_slug(slug: str) -> None:
    """Slug must be ^[a-z][a-z0-9_]*$ (snake-case, starting with a letter)."""
    if not _SLUG_RE.match(slug):
        raise ValueError(
            f"Invalid slug {slug!r}: must match ^[a-z][a-z0-9_]*$"
        )


_TRANSLIT_RU = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e',
    'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k',
    'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def title_to_slug(title: str) -> str:
    """Derive a slug ([a-z][a-z0-9_]*) from a human title.

    Russian letters are transliterated, other non-[a-z0-9_] chars become '_',
    underscores collapsed, leading/trailing stripped. If the result starts
    with a digit, prefix with 'n_'. Returns '' if no valid chars remain —
    caller validates the result via validate_slug or treats empty as error.
    """
    s = title.strip().lower()
    out: list[str] = []
    for ch in s:
        if ch in _TRANSLIT_RU:
            out.append(_TRANSLIT_RU[ch])
        elif ch.isascii() and (ch.isalnum() or ch == '_'):
            out.append(ch)
        else:
            out.append('_')
    s = ''.join(out)
    while '__' in s:
        s = s.replace('__', '_')
    s = s.strip('_')
    if s and s[0].isdigit():
        s = 'n_' + s
    return s


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


async def list_all_defect_leaves(session: AsyncSession) -> list[FeatureNodeRow]:
    """All feature_nodes with kind='defect', sorted by title.
    Used by the «Добавить дефект» UI on /defects/devices/{id}."""
    rows = (
        await session.execute(
            text("SELECT * FROM feature_nodes WHERE kind = 'defect' ORDER BY title")
        )
    ).all()
    return [_row_to_fn(r) for r in rows]


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


# Sentinel for "not provided" (distinguishes None from "not passed")
_UNSET = object()


async def update_feature_node(
    session: AsyncSession,
    nid: uuid.UUID,
    *,
    title: str | None = None,
    slug: str | None = None,
    parent_id: object = _UNSET,
    sort_order: int | None = None,
    prompt_hint: object = _UNSET,
    kind: str | None = None,
) -> None:
    if parent_id is not _UNSET and parent_id is not None:
        if str(parent_id) == str(nid):
            raise ValueError("cycle: node cannot be its own parent")
        cursor = parent_id
        while cursor is not None:
            row = (await session.execute(
                text("SELECT parent_id FROM feature_nodes WHERE id = :id"),
                {"id": str(cursor)},
            )).first()
            if row is None:
                break
            if row.parent_id is not None and str(row.parent_id) == str(nid):
                raise ValueError("cycle: parent would create a loop")
            cursor = uuid.UUID(str(row.parent_id)) if row.parent_id else None

    sets: list[str] = []
    params: dict = {"id": str(nid)}

    if title is not None:
        sets.append("title = :title")
        params["title"] = title
    if slug is not None:
        validate_slug(slug)
        sets.append("slug = :slug")
        params["slug"] = slug
    if parent_id is not _UNSET:
        sets.append("parent_id = :pid")
        params["pid"] = str(parent_id) if parent_id else None
    if sort_order is not None:
        sets.append("sort_order = :sort")
        params["sort"] = sort_order
    if prompt_hint is not _UNSET:
        sets.append("prompt_hint = :hint")
        params["hint"] = prompt_hint
    if kind is not None:
        if kind not in ("node", "defect"):
            raise ValueError(f"Invalid kind {kind!r}")
        sets.append("kind = :kind")
        params["kind"] = kind

    if not sets:
        return

    sets.append(f"updated_at = {_now_expr(session)}")
    await session.execute(
        text(f"UPDATE feature_nodes SET {', '.join(sets)} WHERE id = :id"),
        params,
    )
    await session.commit()


async def delete_feature_node(session: AsyncSession, nid: uuid.UUID) -> None:
    await session.execute(
        text("DELETE FROM feature_nodes WHERE id = :id"),
        {"id": str(nid)},
    )
    await session.commit()


# ---------------------------------------------------------------------------
# CRUD — device_nodes
# ---------------------------------------------------------------------------

@dataclass
class DeviceNodeRow:
    id: uuid.UUID
    parent_id: uuid.UUID | None
    slug: str
    title: str
    kind: str | None
    sort_order: int


def _row_to_dn(row) -> DeviceNodeRow:
    return DeviceNodeRow(
        id=uuid.UUID(str(row.id)),
        parent_id=uuid.UUID(str(row.parent_id)) if row.parent_id is not None else None,
        slug=row.slug, title=row.title, kind=row.kind,
        sort_order=row.sort_order,
    )


async def create_device_node(
    session: AsyncSession, *, parent_id: uuid.UUID | None,
    slug: str, title: str, kind: str | None = None, sort_order: int = 0,
) -> uuid.UUID:
    validate_slug(slug)
    nid = uuid.uuid4()
    await session.execute(text("""
        INSERT INTO device_nodes (id, parent_id, slug, title, kind, sort_order)
        VALUES (:id, :pid, :slug, :title, :kind, :sort)
    """), {
        "id": str(nid),
        "pid": str(parent_id) if parent_id is not None else None,
        "slug": slug, "title": title, "kind": kind, "sort": sort_order,
    })
    await session.commit()
    return nid


async def get_device_node(session: AsyncSession, nid: uuid.UUID) -> DeviceNodeRow | None:
    row = (await session.execute(
        text("SELECT * FROM device_nodes WHERE id = :id"), {"id": str(nid)},
    )).first()
    return _row_to_dn(row) if row else None


async def list_device_children(
    session: AsyncSession, parent_id: uuid.UUID | None,
) -> list[DeviceNodeRow]:
    if parent_id is None:
        rows = (await session.execute(
            text("SELECT * FROM device_nodes WHERE parent_id IS NULL ORDER BY sort_order, slug")
        )).all()
    else:
        rows = (await session.execute(
            text("SELECT * FROM device_nodes WHERE parent_id = :pid ORDER BY sort_order, slug"),
            {"pid": str(parent_id)},
        )).all()
    return [_row_to_dn(r) for r in rows]


async def update_device_node(
    session: AsyncSession, nid: uuid.UUID, *,
    title: str | None = None, slug: str | None = None,
    parent_id: object = _UNSET, kind: object = _UNSET,
    sort_order: int | None = None,
) -> None:
    if parent_id is not _UNSET and parent_id is not None:
        if str(parent_id) == str(nid):
            raise ValueError("cycle: device cannot be its own parent")
        cursor = parent_id
        while cursor is not None:
            row = (await session.execute(
                text("SELECT parent_id FROM device_nodes WHERE id = :id"),
                {"id": str(cursor)},
            )).first()
            if row is None:
                break
            if row.parent_id is not None and str(row.parent_id) == str(nid):
                raise ValueError("cycle: parent would create a loop")
            cursor = uuid.UUID(str(row.parent_id)) if row.parent_id else None

    sets, params = [], {"id": str(nid)}
    if title is not None:
        sets.append("title = :title"); params["title"] = title
    if slug is not None:
        validate_slug(slug); sets.append("slug = :slug"); params["slug"] = slug
    if parent_id is not _UNSET:
        sets.append("parent_id = :pid")
        params["pid"] = str(parent_id) if parent_id is not None else None
    if kind is not _UNSET:
        sets.append("kind = :kind"); params["kind"] = kind
    if sort_order is not None:
        sets.append("sort_order = :sort"); params["sort"] = sort_order
    if not sets:
        return
    sets.append(f"updated_at = {_now_expr(session)}")
    await session.execute(
        text(f"UPDATE device_nodes SET {', '.join(sets)} WHERE id = :id"),
        params,
    )
    await session.commit()


async def delete_device_node(session: AsyncSession, nid: uuid.UUID) -> None:
    await session.execute(
        text("DELETE FROM device_nodes WHERE id = :id"), {"id": str(nid)},
    )
    await session.commit()


# ---------------------------------------------------------------------------
# CRUD — device_feature_bindings
# ---------------------------------------------------------------------------

@dataclass
class BindingRow:
    id: uuid.UUID
    device_node_id: uuid.UUID
    feature_node_id: uuid.UUID
    defect_action: str
    unknown_action: str
    disabled: bool


def _row_to_b(row) -> BindingRow:
    return BindingRow(
        id=uuid.UUID(str(row.id)),
        device_node_id=uuid.UUID(str(row.device_node_id)),
        feature_node_id=uuid.UUID(str(row.feature_node_id)),
        defect_action=row.defect_action,
        unknown_action=row.unknown_action,
        disabled=bool(row.disabled),
    )


async def create_binding(
    session: AsyncSession, *,
    device_node_id: uuid.UUID, feature_node_id: uuid.UUID,
    defect_action: str, unknown_action: str, disabled: bool = False,
) -> uuid.UUID:
    if defect_action not in ("block", "info"):
        raise ValueError(f"Invalid defect_action {defect_action!r}")
    if unknown_action not in ("ask", "skip"):
        raise ValueError(f"Invalid unknown_action {unknown_action!r}")
    row = (await session.execute(
        text("SELECT kind FROM feature_nodes WHERE id = :id"),
        {"id": str(feature_node_id)},
    )).first()
    if row is None:
        raise ValueError(f"feature_node {feature_node_id} not found")
    if row.kind != "defect":
        raise ValueError(
            f"feature_node {feature_node_id} is kind={row.kind!r}; "
            "bindings can only point to kind='defect' leaves"
        )

    bid = uuid.uuid4()
    await session.execute(text("""
        INSERT INTO device_feature_bindings
            (id, device_node_id, feature_node_id, defect_action, unknown_action, disabled)
        VALUES (:id, :dn, :fn, :da, :ua, :dis)
    """), {
        "id": str(bid),
        "dn": str(device_node_id), "fn": str(feature_node_id),
        "da": defect_action, "ua": unknown_action,
        "dis": 1 if disabled else 0,
    })
    await session.commit()
    return bid


async def get_binding(session: AsyncSession, bid: uuid.UUID) -> BindingRow | None:
    row = (await session.execute(
        text("SELECT * FROM device_feature_bindings WHERE id = :id"),
        {"id": str(bid)},
    )).first()
    return _row_to_b(row) if row else None


async def list_bindings_at_device(
    session: AsyncSession, device_node_id: uuid.UUID,
) -> list[BindingRow]:
    rows = (await session.execute(
        text("SELECT * FROM device_feature_bindings WHERE device_node_id = :dn"),
        {"dn": str(device_node_id)},
    )).all()
    return [_row_to_b(r) for r in rows]


async def update_binding(
    session: AsyncSession, bid: uuid.UUID, *,
    defect_action: str | None = None, unknown_action: str | None = None,
    disabled: bool | None = None,
) -> None:
    sets, params = [], {"id": str(bid)}
    if defect_action is not None:
        if defect_action not in ("block", "info"):
            raise ValueError(f"Invalid defect_action {defect_action!r}")
        sets.append("defect_action = :da"); params["da"] = defect_action
    if unknown_action is not None:
        if unknown_action not in ("ask", "skip"):
            raise ValueError(f"Invalid unknown_action {unknown_action!r}")
        sets.append("unknown_action = :ua"); params["ua"] = unknown_action
    if disabled is not None:
        sets.append("disabled = :dis"); params["dis"] = 1 if disabled else 0
    if not sets:
        return
    sets.append(f"updated_at = {_now_expr(session)}")
    await session.execute(
        text(f"UPDATE device_feature_bindings SET {', '.join(sets)} WHERE id = :id"),
        params,
    )
    await session.commit()


async def delete_binding(session: AsyncSession, bid: uuid.UUID) -> None:
    await session.execute(
        text("DELETE FROM device_feature_bindings WHERE id = :id"), {"id": str(bid)},
    )
    await session.commit()

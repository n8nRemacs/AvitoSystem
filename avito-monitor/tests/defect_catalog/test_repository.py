"""Tests for defect_catalog repository — Tasks 7, 8, 9."""
from __future__ import annotations

import uuid
import pytest
from app.services.defect_catalog.repository import (
    validate_slug,
    create_feature_node,
    get_feature_node,
    list_feature_children,
    update_feature_node,
    delete_feature_node,
)


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


# ---------------------------------------------------------------------------
# Task 8: feature_node create / get / list_children
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_root_feature_node(db_session):
    nid = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="Корпус",
    )
    assert isinstance(nid, uuid.UUID)
    fn = await get_feature_node(db_session, nid)
    assert fn.title == "Корпус"
    assert fn.parent_id is None


@pytest.mark.asyncio
async def test_create_child_defect(db_session):
    case_id = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="Корпус",
    )
    leaf_id = await create_feature_node(
        db_session, parent_id=case_id, kind="defect",
        slug="back_broken", title="Задняя крышка разбита",
    )
    children = await list_feature_children(db_session, case_id)
    assert len(children) == 1
    assert children[0].id == leaf_id


@pytest.mark.asyncio
async def test_create_rejects_invalid_slug(db_session):
    with pytest.raises(ValueError, match="slug"):
        await create_feature_node(
            db_session, parent_id=None, kind="node", slug="Bad Slug", title="x",
        )


# ---------------------------------------------------------------------------
# Task 9: feature_node update / delete + duplicate-slug guard
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_feature_node_title(db_session):
    nid = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="Корпус",
    )
    await update_feature_node(db_session, nid, title="Корпус (обновлено)")
    fn = await get_feature_node(db_session, nid)
    assert fn.title == "Корпус (обновлено)"


@pytest.mark.asyncio
async def test_delete_cascade(db_session):
    case_id = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="Корпус",
    )
    leaf_id = await create_feature_node(
        db_session, parent_id=case_id, kind="defect",
        slug="back_broken", title="x",
    )
    await delete_feature_node(db_session, case_id)
    assert await get_feature_node(db_session, leaf_id) is None


@pytest.mark.asyncio
async def test_duplicate_slug_in_parent_rejected(db_session):
    pid = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="Корпус",
    )
    await create_feature_node(
        db_session, parent_id=pid, kind="defect", slug="back_broken", title="A",
    )
    with pytest.raises(Exception):  # IntegrityError
        await create_feature_node(
            db_session, parent_id=pid, kind="defect", slug="back_broken", title="B",
        )

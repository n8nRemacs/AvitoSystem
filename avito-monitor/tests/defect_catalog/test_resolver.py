"""Tests for defect_catalog resolver — Tasks 13-17."""
from __future__ import annotations

import pytest
import pytest_asyncio
from app.services.defect_catalog.repository import (
    create_device_node, create_feature_node, create_binding,
)
from app.services.defect_catalog.resolver import resolve_applicable_defects


@pytest_asyncio.fixture
async def basic_tree(db_session):
    """Phone → Apple → iPhone 12 PM; one defect Стекло разбито bound at Phone."""
    phone = await create_device_node(db_session, parent_id=None, slug="phone", title="Phone")
    apple = await create_device_node(db_session, parent_id=phone, slug="apple", title="Apple")
    ipm = await create_device_node(
        db_session, parent_id=apple, slug="ipm", title="iPhone 12 PM",
    )
    display = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="display", title="Дисплей",
    )
    glass = await create_feature_node(
        db_session, parent_id=display, kind="defect",
        slug="glass_broken", title="Стекло разбито",
    )
    bid = await create_binding(
        db_session, device_node_id=phone, feature_node_id=glass,
        defect_action="info", unknown_action="ask",
    )
    return {"phone": phone, "apple": apple, "ipm": ipm,
            "display": display, "glass": glass, "binding": bid}


@pytest.mark.asyncio
async def test_resolver_returns_own_binding(db_session, basic_tree):
    """Bindings on the target device itself are returned."""
    resolved = await resolve_applicable_defects(db_session, basic_tree["phone"])
    assert len(resolved) == 1
    r = resolved[0]
    assert r.feature_node_id == basic_tree["glass"]
    assert r.defect_action == "info"
    assert r.unknown_action == "ask"
    assert r.inherited_from is None
    assert r.feature_path == ["Дисплей", "Стекло разбито"]


# ---------------------------------------------------------------------------
# Task 14: Inheritance from ancestor
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolver_inherits_from_ancestor(db_session, basic_tree):
    """Binding on Phone is visible from iPhone 12 PM, marked as inherited."""
    resolved = await resolve_applicable_defects(db_session, basic_tree["ipm"])
    assert len(resolved) == 1
    r = resolved[0]
    assert r.feature_node_id == basic_tree["glass"]
    assert r.defect_action == "info"
    assert r.inherited_from == basic_tree["phone"]


# ---------------------------------------------------------------------------
# Task 15: Child override
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolver_child_overrides_ancestor(db_session, basic_tree):
    """Phone-level (info, ask). iPhone 12 PM overrides to (block, skip).
    Resolution returns iPhone-level binding."""
    await create_binding(
        db_session, device_node_id=basic_tree["ipm"],
        feature_node_id=basic_tree["glass"],
        defect_action="block", unknown_action="skip",
    )
    resolved = await resolve_applicable_defects(db_session, basic_tree["ipm"])
    assert len(resolved) == 1
    r = resolved[0]
    assert r.defect_action == "block"
    assert r.unknown_action == "skip"
    assert r.inherited_from is None


# ---------------------------------------------------------------------------
# Task 16: Disabled drops binding
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolver_disabled_drops_inherited(db_session, basic_tree):
    """iPhone 12 PM marks the inherited binding as disabled — resolver drops it."""
    from app.services.defect_catalog.repository import create_binding as _cb
    await _cb(
        db_session, device_node_id=basic_tree["ipm"],
        feature_node_id=basic_tree["glass"],
        defect_action="info", unknown_action="ask",
        disabled=True,
    )
    resolved = await resolve_applicable_defects(db_session, basic_tree["ipm"])
    assert resolved == []


# ---------------------------------------------------------------------------
# Task 17: Sorted by feature_path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolver_sorts_by_feature_path(db_session, basic_tree):
    """Multiple defects across two узлы — output sorted by [section, title]."""
    case = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="Корпус",
    )
    back = await create_feature_node(
        db_session, parent_id=case, kind="defect",
        slug="back_broken", title="Задняя крышка разбита",
    )
    await create_binding(
        db_session, device_node_id=basic_tree["phone"], feature_node_id=back,
        defect_action="info", unknown_action="skip",
    )
    resolved = await resolve_applicable_defects(db_session, basic_tree["ipm"])
    assert [r.feature_path for r in resolved] == [
        ["Дисплей", "Стекло разбито"],
        ["Корпус", "Задняя крышка разбита"],
    ]

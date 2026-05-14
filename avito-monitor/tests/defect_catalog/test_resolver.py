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


# ---------------------------------------------------------------------------
# 2026-05-15: section binding expansion to descendant defects
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolver_expands_section_binding_to_descendants(db_session):
    """User feedback 2026-05-15: bind section «Блокировки» → all defects under it
    appear in resolver output as synthetic rows (inherited_from_section set),
    severity inherited from section binding."""
    phone = await create_device_node(db_session, parent_id=None, slug="phone", title="Phone")
    locks = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="locks", title="Блокировки",
    )
    fmi = await create_feature_node(
        db_session, parent_id=locks, kind="defect", slug="icloud_fmi", title="iCloud FMI",
    )
    passcode = await create_feature_node(
        db_session, parent_id=locks, kind="defect", slug="passcode", title="Экранный код",
    )
    # Bind ONLY the section
    section_bid = await create_binding(
        db_session, device_node_id=phone, feature_node_id=locks,
        defect_action="block", unknown_action="ask",
    )

    resolved = await resolve_applicable_defects(db_session, phone)
    # Expect 3 rows: section + 2 synthetic descendants
    assert len(resolved) == 3
    by_path = {tuple(r.feature_path): r for r in resolved}
    # Section row — own (no inherited_from_section)
    section_row = by_path[("Блокировки",)]
    assert section_row.inherited_from_section is None
    assert section_row.binding_id == section_bid
    # Defect rows — synthetic, severity inherited from section
    fmi_row = by_path[("Блокировки", "iCloud FMI")]
    assert fmi_row.inherited_from_section == locks
    assert fmi_row.defect_action == "block"
    assert fmi_row.unknown_action == "ask"
    assert fmi_row.binding_id == section_bid  # source = section binding
    pc_row = by_path[("Блокировки", "Экранный код")]
    assert pc_row.inherited_from_section == locks


@pytest.mark.asyncio
async def test_resolver_defect_override_wins_over_section(db_session):
    """If both section binding AND direct defect binding exist for the same defect,
    the direct binding wins (own row, not synthetic)."""
    phone = await create_device_node(db_session, parent_id=None, slug="phone", title="Phone")
    locks = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="locks", title="Блокировки",
    )
    fmi = await create_feature_node(
        db_session, parent_id=locks, kind="defect", slug="icloud_fmi", title="iCloud FMI",
    )
    await create_binding(
        db_session, device_node_id=phone, feature_node_id=locks,
        defect_action="block", unknown_action="ask",  # section default
    )
    direct_bid = await create_binding(
        db_session, device_node_id=phone, feature_node_id=fmi,
        defect_action="info", unknown_action="skip",  # override
    )
    resolved = await resolve_applicable_defects(db_session, phone)
    fmi_rows = [r for r in resolved if r.feature_node_id == fmi]
    assert len(fmi_rows) == 1
    r = fmi_rows[0]
    assert r.inherited_from_section is None  # not synthetic — direct binding wins
    assert r.binding_id == direct_bid
    assert r.defect_action == "info"  # the override severity, not section default

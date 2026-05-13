"""Tests for defect_catalog repository — Tasks 7, 8, 9, 10, 11, 12."""
from __future__ import annotations

import uuid
import pytest
import pytest_asyncio
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
# title_to_slug — auto-derive slug from human title
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("title, expected", [
    ("iPhone 13", "iphone_13"),
    ("iPhone 13 Pro Max", "iphone_13_pro_max"),
    ("Apple", "apple"),
    ("Дисплей", "displey"),
    ("Корпус", "korpus"),
    ("  Padded  ", "padded"),
    ("123 leading-digit", "n_123_leading_digit"),
    ("a__b___c", "a_b_c"),
    ("___trim___", "trim"),
])
def test_title_to_slug_derives_valid_slug(title, expected):
    from app.services.defect_catalog.repository import title_to_slug, validate_slug
    result = title_to_slug(title)
    assert result == expected
    # And the derived slug must pass validate_slug
    validate_slug(result)


def test_title_to_slug_returns_empty_for_unmappable():
    """If title has no letters/digits and no Russian/ASCII alphanumerics,
    return '' so caller can present a user error."""
    from app.services.defect_catalog.repository import title_to_slug
    assert title_to_slug("!@#$%^&*()") == ""
    assert title_to_slug("   ") == ""
    assert title_to_slug("") == ""


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


@pytest.mark.asyncio
async def test_now_expr_sqlite(db_session):
    """SQLite session should pick datetime('now')."""
    from app.services.defect_catalog.repository import _now_expr
    assert _now_expr(db_session) == "datetime('now')"


# ---------------------------------------------------------------------------
# Task 10: cycle detection for feature_node parent change
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_parent_to_self_rejected(db_session):
    nid = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="case", title="x",
    )
    with pytest.raises(ValueError, match="cycle"):
        await update_feature_node(db_session, nid, parent_id=nid)


@pytest.mark.asyncio
async def test_update_parent_to_descendant_rejected(db_session):
    root = await create_feature_node(
        db_session, parent_id=None, kind="node", slug="root", title="r",
    )
    mid = await create_feature_node(
        db_session, parent_id=root, kind="node", slug="mid", title="m",
    )
    leaf = await create_feature_node(
        db_session, parent_id=mid, kind="defect", slug="leaf", title="l",
    )
    with pytest.raises(ValueError, match="cycle"):
        await update_feature_node(db_session, root, parent_id=leaf)


# ---------------------------------------------------------------------------
# Task 11: device_node CRUD with cycle detection
# ---------------------------------------------------------------------------

from app.services.defect_catalog.repository import (
    create_device_node, get_device_node, list_device_children,
    update_device_node, delete_device_node,
)


@pytest.mark.asyncio
async def test_device_node_crud(db_session):
    root = await create_device_node(
        db_session, parent_id=None, slug="phone", title="Phone", kind="type",
    )
    brand = await create_device_node(
        db_session, parent_id=root, slug="apple", title="Apple", kind="brand",
    )
    model = await create_device_node(
        db_session, parent_id=brand, slug="iphone_12_pm",
        title="iPhone 12 Pro Max", kind="model",
    )
    assert (await get_device_node(db_session, model)).title == "iPhone 12 Pro Max"
    assert len(await list_device_children(db_session, root)) == 1
    await delete_device_node(db_session, brand)
    assert await get_device_node(db_session, model) is None


@pytest.mark.asyncio
async def test_device_node_cycle_detection(db_session):
    a = await create_device_node(db_session, parent_id=None, slug="a", title="A")
    b = await create_device_node(db_session, parent_id=a, slug="b", title="B")
    with pytest.raises(ValueError, match="cycle"):
        await update_device_node(db_session, a, parent_id=b)


# ---------------------------------------------------------------------------
# Task 12: binding CRUD + kind='defect' validation
# ---------------------------------------------------------------------------

from app.services.defect_catalog.repository import (
    create_binding, get_binding, list_bindings_at_device,
    update_binding, delete_binding,
)


@pytest_asyncio.fixture
async def seeded(db_session):
    """Seed a minimal tree: Phone device, Корпус node, Стекло defect."""
    phone = await create_device_node(db_session, parent_id=None, slug="phone", title="Phone")
    case = await create_feature_node(db_session, parent_id=None, kind="node", slug="case", title="Корпус")
    leaf = await create_feature_node(
        db_session, parent_id=case, kind="defect", slug="back_broken", title="Задняя крышка",
    )
    return {"phone": phone, "case": case, "leaf": leaf}


@pytest.mark.asyncio
async def test_create_binding_on_defect(db_session, seeded):
    bid = await create_binding(
        db_session, device_node_id=seeded["phone"],
        feature_node_id=seeded["leaf"],
        defect_action="block", unknown_action="ask",
    )
    b = await get_binding(db_session, bid)
    assert b.defect_action == "block"
    assert b.disabled is False


@pytest.mark.asyncio
async def test_binding_on_node_kind_rejected(db_session, seeded):
    """Cannot bind a non-leaf feature_node (kind='node')."""
    with pytest.raises(ValueError, match="defect"):
        await create_binding(
            db_session, device_node_id=seeded["phone"],
            feature_node_id=seeded["case"],
            defect_action="block", unknown_action="ask",
        )


@pytest.mark.asyncio
async def test_binding_update_severity(db_session, seeded):
    bid = await create_binding(
        db_session, device_node_id=seeded["phone"],
        feature_node_id=seeded["leaf"],
        defect_action="block", unknown_action="ask",
    )
    await update_binding(db_session, bid, defect_action="info", unknown_action="skip")
    b = await get_binding(db_session, bid)
    assert b.defect_action == "info"
    assert b.unknown_action == "skip"


@pytest.mark.asyncio
async def test_binding_toggle_disabled(db_session, seeded):
    bid = await create_binding(
        db_session, device_node_id=seeded["phone"],
        feature_node_id=seeded["leaf"],
        defect_action="block", unknown_action="ask",
    )
    await update_binding(db_session, bid, disabled=True)
    assert (await get_binding(db_session, bid)).disabled is True


@pytest.mark.asyncio
async def test_binding_unique_per_device_feature(db_session, seeded):
    await create_binding(
        db_session, device_node_id=seeded["phone"],
        feature_node_id=seeded["leaf"],
        defect_action="block", unknown_action="ask",
    )
    with pytest.raises(Exception):
        await create_binding(
            db_session, device_node_id=seeded["phone"],
            feature_node_id=seeded["leaf"],
            defect_action="info", unknown_action="skip",
        )

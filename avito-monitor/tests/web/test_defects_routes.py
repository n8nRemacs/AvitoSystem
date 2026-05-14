"""Smoke tests for /defects/* routes."""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.models import User
from app.deps import db_session, require_user
from app.main import create_app


USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


class _ListResult:
    """Fake execute result that supports .all() and .first()."""

    def all(self) -> list:
        return []

    def first(self) -> None:
        return None

    # Keep scalar_one* for sidebar context queries used in _layout.html
    def scalar_one(self) -> int:
        return 0

    def scalar_one_or_none(self) -> Any:
        return None


class DefectFakeSession:
    """Minimal async session double for defect catalog routes.

    - execute() returns _ListResult (supports .all(), .first(), scalar_one*)
    - commit() is a no-op
    """

    async def execute(self, stmt: Any, params: Any = None) -> _ListResult:
        return _ListResult()

    async def commit(self) -> None:
        return None

    async def get(self, model: Any, ident: Any) -> None:
        return None


def _fake_user() -> User:
    user = User()
    user.id = USER_ID
    user.username = "testuser"
    user.password_hash = "x"
    user.is_active = True
    user.is_admin = False
    return user


@pytest.fixture
def defects_client(monkeypatch):
    """TestClient with DB + auth overridden; sufficient for defect catalog routes."""
    from app.web import routers
    from app.services import search_profiles as svc

    async def _fake_get_profile(session, user_id, profile_id):
        return None

    async def _fake_load_rules(session, profile_id):
        return {}

    monkeypatch.setattr(svc, "get_profile", _fake_get_profile)
    monkeypatch.setattr(routers.feat_repo, "load_profile_rules", _fake_load_rules)
    monkeypatch.setattr(routers, "_load_regions", lambda: [])

    app = create_app()
    fake_session = DefectFakeSession()

    async def _fake_db():
        yield fake_session

    async def _fake_user_dep():
        return _fake_user()

    app.dependency_overrides[db_session] = _fake_db
    app.dependency_overrides[require_user] = _fake_user_dep
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_defects_root_redirects(defects_client):
    resp = defects_client.get("/defects", follow_redirects=False)
    assert resp.status_code in (303, 307)
    assert resp.headers["location"] == "/defects/devices"


def test_defects_devices_page_200(defects_client):
    resp = defects_client.get("/defects/devices")
    assert resp.status_code == 200
    assert "Настройки дефектов" in resp.text
    assert "Загрузка" in resp.text  # Loading → Загрузка
    assert 'hx-get="/defects/devices/new"' in resp.text  # root-add button
    assert "Добавить корневое устройство" in resp.text


def test_defects_catalog_page_200(defects_client):
    resp = defects_client.get("/defects/catalog")
    assert resp.status_code == 200
    assert "Каталог признаков" in resp.text
    assert "Загрузка" in resp.text
    assert 'hx-get="/defects/catalog/new"' in resp.text
    assert "Добавить корневой признак" in resp.text


def test_defects_devices_tree_empty_200(defects_client):
    resp = defects_client.get("/defects/devices/tree")
    assert resp.status_code == 200


def test_defects_catalog_tree_empty_200(defects_client):
    resp = defects_client.get("/defects/catalog/tree")
    assert resp.status_code == 200


def test_defects_device_detail_renders_with_sidebar(defects_client, monkeypatch):
    """Regression: /defects/devices/{id} extends global _layout.html and so the
    route must populate sidebar context (sidebar_profiles_count, etc.). Without
    it Jinja raises UndefinedError → 500."""
    from app.services.defect_catalog import repository as repo
    from app.services.defect_catalog.repository import DeviceNodeRow
    from app.web import defects as defects_mod

    fake_id = uuid.UUID("14e54f9a-6155-5e4c-8f27-63e5f9317f9b")
    fake_device = DeviceNodeRow(
        id=fake_id, parent_id=None, slug="iphone_12_pm",
        title="iPhone 12 Pro Max", kind=None, sort_order=0,
    )

    async def _fake_get_device_node(session, nid):
        return fake_device

    async def _fake_resolve(session, device_id):
        return []

    monkeypatch.setattr(defects_mod, "get_device_node", _fake_get_device_node)
    monkeypatch.setattr(defects_mod, "resolve_applicable_defects", _fake_resolve)

    resp = defects_client.get(f"/defects/devices/{fake_id}")
    assert resp.status_code == 200, resp.text[:500]
    assert "iPhone 12 Pro Max" in resp.text
    # Sidebar must be rendered (proves _layout_context was passed)
    assert "Avito Monitor" in resp.text


def test_severity_ru_filter():
    """Unit-test severity_ru filter — maps DB values to Russian display labels."""
    from app.web.defects import severity_ru
    assert severity_ru("block") == "блок"
    assert severity_ru("info") == "инфо"
    assert severity_ru("ask") == "уточнить"
    assert severity_ru("skip") == "пропустить"
    # Unknown values pass through unchanged (defensive)
    assert severity_ru("unknown") == "unknown"
    assert severity_ru("") == ""


def test_get_device_form_add_root(defects_client):
    """GET /defects/devices/new → 200, partial form, hx-post target /defects/devices."""
    resp = defects_client.get("/defects/devices/new")
    assert resp.status_code == 200
    assert "node-form-inline" in resp.text
    assert 'hx-post="/defects/devices"' in resp.text
    # No parent_id hidden input for root
    assert 'name="parent_id"' not in resp.text


def test_get_device_form_add_child(defects_client):
    """GET /defects/devices/{parent_id}/new → 200, parent_id hidden input present."""
    parent_id = "11111111-1111-1111-1111-111111111111"
    resp = defects_client.get(f"/defects/devices/{parent_id}/new")
    assert resp.status_code == 200
    assert "node-form-inline" in resp.text
    assert 'hx-post="/defects/devices"' in resp.text
    assert f'name="parent_id" value="{parent_id}"' in resp.text


def test_get_device_form_edit(defects_client, monkeypatch):
    """GET /defects/devices/{id}/edit → 200, prefill values + hx-patch target."""
    import uuid as _uuid
    from app.services.defect_catalog.repository import DeviceNodeRow
    from app.web import defects as defects_mod

    nid = _uuid.UUID("22222222-2222-2222-2222-222222222222")
    fake_device = DeviceNodeRow(
        id=nid, parent_id=None, slug="apple", title="Apple",
        kind=None, sort_order=0,
    )

    async def _fake_get_device_node(session, _nid):
        return fake_device

    monkeypatch.setattr(defects_mod, "get_device_node", _fake_get_device_node)

    resp = defects_client.get(f"/defects/devices/{nid}/edit")
    assert resp.status_code == 200
    assert "node-form-inline" in resp.text
    assert f'hx-patch="/defects/devices/{nid}/edit"' in resp.text
    assert 'value="apple"' in resp.text
    assert 'value="Apple"' in resp.text


def test_binding_row_uses_ru_labels(defects_client, monkeypatch):
    """GET /defects/devices/{id} renders bindings with Russian severity labels
    + inherited/set-here/Override translations."""
    import uuid as _uuid
    from app.services.defect_catalog.repository import DeviceNodeRow
    from app.services.defect_catalog.resolver import ResolvedBinding
    from app.web import defects as defects_mod

    fake_dev_id = _uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    fake_feat_id = _uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    fake_bind_id = _uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    fake_device = DeviceNodeRow(
        id=fake_dev_id, parent_id=None, slug="phone",
        title="Phone", kind=None, sort_order=0,
    )
    # Two bindings: one inherited (block/ask), one set-here (info/skip)
    inherited = ResolvedBinding(
        binding_id=fake_bind_id, feature_node_id=fake_feat_id,
        feature_path=["Корпус", "Midframe сломан"],
        defect_action="block", unknown_action="ask",
        inherited_from=_uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
    )
    set_here = ResolvedBinding(
        binding_id=_uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        feature_node_id=fake_feat_id,
        feature_path=["Дисплей", "Стекло разбито"],
        defect_action="info", unknown_action="skip",
        inherited_from=None,
    )

    async def _fake_get_device_node(session, nid):
        return fake_device

    async def _fake_resolve(session, device_id):
        return [inherited, set_here]

    monkeypatch.setattr(defects_mod, "get_device_node", _fake_get_device_node)
    monkeypatch.setattr(defects_mod, "resolve_applicable_defects", _fake_resolve)

    resp = defects_client.get(f"/defects/devices/{fake_dev_id}")
    assert resp.status_code == 200, resp.text[:500]
    # Inherited display uses ru labels
    assert "блок" in resp.text
    assert "уточнить" in resp.text
    # Set-here dropdowns also use ru in option labels
    assert "инфо" in resp.text
    assert "пропустить" in resp.text
    # Translated annotations
    assert "← унаследовано" in resp.text
    assert "← задано здесь" in resp.text
    # Override button translated
    assert "Задать здесь" in resp.text


def test_get_feature_form_add_root(defects_client):
    """GET /defects/catalog/new → 200, partial form has kind+prompt_hint inputs."""
    resp = defects_client.get("/defects/catalog/new")
    assert resp.status_code == 200
    assert "node-form-inline" in resp.text
    assert 'hx-post="/defects/catalog"' in resp.text
    # Feature-specific fields present in add mode
    assert 'name="kind"' in resp.text
    assert 'name="prompt_hint"' in resp.text
    assert 'name="parent_id"' not in resp.text


def test_get_feature_form_add_child(defects_client):
    parent_id = "33333333-3333-3333-3333-333333333333"
    resp = defects_client.get(f"/defects/catalog/{parent_id}/new")
    assert resp.status_code == 200
    assert f'name="parent_id" value="{parent_id}"' in resp.text


def test_get_feature_form_edit(defects_client, monkeypatch):
    """GET /defects/catalog/{id}/edit → 200, prefill including prompt_hint."""
    import uuid as _uuid
    from app.services.defect_catalog.repository import FeatureNodeRow
    from app.web import defects as defects_mod

    nid = _uuid.UUID("44444444-4444-4444-4444-444444444444")
    fake_feat = FeatureNodeRow(
        id=nid, parent_id=None, kind="section", slug="display",
        title="Дисплей", sort_order=0, prompt_hint="Дисплей телефона",
    )

    async def _fake_get(session, _nid):
        return fake_feat

    # get_feature_node is in repository — defects.py uses it indirectly via resolver path.
    # For form-edit, we need defects.py to call get_feature_node(session, node_id).
    # Patch on defects module — same import path pattern as device case.
    monkeypatch.setattr(defects_mod, "get_feature_node", _fake_get)

    resp = defects_client.get(f"/defects/catalog/{nid}/edit")
    assert resp.status_code == 200
    assert "node-form-inline" in resp.text
    assert f'hx-patch="/defects/catalog/{nid}/edit"' in resp.text
    assert 'value="display"' in resp.text
    assert 'value="Дисплей"' in resp.text
    assert 'value="Дисплей телефона"' in resp.text


def test_post_device_derives_slug_from_title(defects_client, monkeypatch):
    """POST /defects/devices with empty slug auto-derives from title via title_to_slug."""
    captured: dict = {}

    async def _fake_create(session, *, parent_id, slug, title, kind=None, sort_order=0):
        captured["slug"] = slug
        captured["title"] = title
        return uuid.uuid4()

    async def _fake_list_children(session, parent_id):
        return []

    from app.web import defects as defects_mod
    monkeypatch.setattr(defects_mod, "create_device_node", _fake_create)
    monkeypatch.setattr(defects_mod, "list_device_children", _fake_list_children)

    resp = defects_client.post("/defects/devices", data={"title": "iPhone 13", "slug": ""})
    assert resp.status_code == 200, resp.text[:300]
    assert captured["slug"] == "iphone_13"
    assert captured["title"] == "iPhone 13"


def test_post_device_uses_explicit_slug_when_provided(defects_client, monkeypatch):
    """If slug is provided explicitly, backend uses it as-is (does not override)."""
    captured: dict = {}

    async def _fake_create(session, *, parent_id, slug, title, kind=None, sort_order=0):
        captured["slug"] = slug
        return uuid.uuid4()

    async def _fake_list_children(session, parent_id):
        return []

    from app.web import defects as defects_mod
    monkeypatch.setattr(defects_mod, "create_device_node", _fake_create)
    monkeypatch.setattr(defects_mod, "list_device_children", _fake_list_children)

    resp = defects_client.post(
        "/defects/devices",
        data={"title": "iPhone 13", "slug": "custom_alias"},
    )
    assert resp.status_code == 200
    assert captured["slug"] == "custom_alias"


def test_post_device_returns_400_on_duplicate_slug(defects_client, monkeypatch):
    """Если backend репо бросает IntegrityError (нарушение uq_device_nodes_parent_slug),
    handler должен поймать и вернуть 400 с понятным русским сообщением — не 500."""
    from sqlalchemy.exc import IntegrityError
    from app.web import defects as defects_mod

    async def _fake_create_dupe(session, **kwargs):
        raise IntegrityError("INSERT INTO ...", {}, Exception("duplicate key"))

    async def _fake_rollback():
        return None

    async def _fake_list_children(session, parent_id):
        return []

    # Patch session.rollback on the real session — easier to monkeypatch
    # the create function only and let session.rollback be a no-op against
    # the fake session (DefectFakeSession already has commit; we add rollback).
    monkeypatch.setattr(defects_mod, "create_device_node", _fake_create_dupe)
    monkeypatch.setattr(defects_mod, "list_device_children", _fake_list_children)
    # Ensure DefectFakeSession.rollback exists (add via setattr on class instance via fixture):
    # Simpler — monkeypatch the DefectFakeSession class for this test:
    from tests.web.test_defects_routes import DefectFakeSession
    async def _rb(self):
        return None
    monkeypatch.setattr(DefectFakeSession, "rollback", _rb, raising=False)

    resp = defects_client.post("/defects/devices", data={"title": "iPhone 13", "slug": ""})
    assert resp.status_code == 400, resp.text[:500]
    assert "уже существует" in resp.text.lower()
    assert "iphone_13" in resp.text  # mentions the derived slug
    assert "iPhone 13" in resp.text  # mentions the title


def test_post_feature_returns_400_on_duplicate_slug(defects_client, monkeypatch):
    """Симметрично: catalog endpoint ловит IntegrityError → 400 с русским сообщением."""
    from sqlalchemy.exc import IntegrityError
    from app.web import defects as defects_mod

    async def _fake_create_dupe(session, **kwargs):
        raise IntegrityError("INSERT INTO ...", {}, Exception("duplicate key"))

    async def _fake_list_children(session, parent_id):
        return []

    monkeypatch.setattr(defects_mod, "create_feature_node", _fake_create_dupe)
    monkeypatch.setattr(defects_mod, "list_feature_children", _fake_list_children)
    from tests.web.test_defects_routes import DefectFakeSession
    async def _rb(self):
        return None
    monkeypatch.setattr(DefectFakeSession, "rollback", _rb, raising=False)

    resp = defects_client.post(
        "/defects/catalog",
        data={"title": "Дисплей", "slug": "", "kind": "section"},
    )
    assert resp.status_code == 400
    assert "уже существует" in resp.text.lower()


def test_patch_device_returns_400_on_duplicate_slug(defects_client, monkeypatch):
    """Reviewer Issue 1: PATCH /defects/devices/{id}/edit must catch IntegrityError
    (uq_device_nodes_parent_slug) → 400 с русским сообщением, не 500."""
    import uuid as _uuid
    from sqlalchemy.exc import IntegrityError
    from app.web import defects as defects_mod

    async def _fake_update_dupe(session, nid, **kw):
        raise IntegrityError("UPDATE ...", {}, Exception("duplicate key"))

    monkeypatch.setattr(defects_mod, "update_device_node", _fake_update_dupe)
    from tests.web.test_defects_routes import DefectFakeSession
    async def _rb(self):
        return None
    monkeypatch.setattr(DefectFakeSession, "rollback", _rb, raising=False)

    nid = _uuid.UUID("99999999-9999-9999-9999-999999999999")
    resp = defects_client.patch(
        f"/defects/devices/{nid}/edit",
        data={"title": "iPhone 13", "slug": "iphone_13"},
    )
    assert resp.status_code == 400, resp.text[:300]
    assert "уже существует" in resp.text.lower()


def test_patch_feature_returns_400_on_duplicate_slug(defects_client, monkeypatch):
    """Reviewer Issue 1 — симметрично для catalog PATCH."""
    import uuid as _uuid
    from sqlalchemy.exc import IntegrityError
    from app.web import defects as defects_mod

    async def _fake_update_dupe(session, nid, **kw):
        raise IntegrityError("UPDATE ...", {}, Exception("duplicate key"))

    monkeypatch.setattr(defects_mod, "update_feature_node", _fake_update_dupe)
    from tests.web.test_defects_routes import DefectFakeSession
    async def _rb(self):
        return None
    monkeypatch.setattr(DefectFakeSession, "rollback", _rb, raising=False)

    nid = _uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    resp = defects_client.patch(
        f"/defects/catalog/{nid}/edit",
        data={"title": "Дисплей", "slug": "display"},
    )
    assert resp.status_code == 400
    assert "уже существует" in resp.text.lower()


def test_feature_edit_form_shows_kind_dropdown_with_prefill(defects_client, monkeypatch):
    """User feedback 2026-05-15: edit-форма дефекта/раздела должна позволять
    менять Тип (Раздел/Дефект). Раньше dropdown был только в add-режиме."""
    import uuid as _uuid
    from app.services.defect_catalog.repository import FeatureNodeRow
    from app.web import defects as defects_mod

    nid = _uuid.UUID("11111111-aaaa-bbbb-cccc-222222222222")
    # Existing defect — kind dropdown should show «Дефект» selected
    fake_defect = FeatureNodeRow(
        id=nid, parent_id=None, kind="defect", slug="cracked",
        title="Разбит", sort_order=0, prompt_hint=None,
    )

    async def _fake_get(session, _nid):
        return fake_defect

    monkeypatch.setattr(defects_mod, "get_feature_node", _fake_get)

    resp = defects_client.get(f"/defects/catalog/{nid}/edit")
    assert resp.status_code == 200
    # Dropdown present in edit mode too
    assert 'name="kind"' in resp.text
    # «Дефект» preselected for this defect node
    assert '<option value="defect" selected>' in resp.text or '<option value="defect"  selected' in resp.text


def test_feature_edit_form_prefills_section_kind(defects_client, monkeypatch):
    """Edit form for kind=node feature shows «Раздел» preselected."""
    import uuid as _uuid
    from app.services.defect_catalog.repository import FeatureNodeRow
    from app.web import defects as defects_mod

    nid = _uuid.UUID("33333333-aaaa-bbbb-cccc-444444444444")
    fake_section = FeatureNodeRow(
        id=nid, parent_id=None, kind="node", slug="display",
        title="Дисплей", sort_order=0, prompt_hint=None,
    )

    async def _fake_get(session, _nid):
        return fake_section

    monkeypatch.setattr(defects_mod, "get_feature_node", _fake_get)

    resp = defects_client.get(f"/defects/catalog/{nid}/edit")
    assert resp.status_code == 200
    # Раздел selected (kind=node maps to «Раздел»)
    assert '<option value="node" selected>' in resp.text


def test_patch_feature_can_change_kind(defects_client, monkeypatch):
    """PATCH /defects/catalog/{id}/edit propagates kind field to update_feature_node."""
    captured: dict = {}

    async def _fake_update(session, nid, **kw):
        captured.update(kw)

    async def _fake_list_children(session, parent_id):
        return []

    from app.web import defects as defects_mod
    monkeypatch.setattr(defects_mod, "update_feature_node", _fake_update)
    monkeypatch.setattr(defects_mod, "list_feature_children", _fake_list_children)

    import uuid as _uuid
    nid = _uuid.UUID("55555555-aaaa-bbbb-cccc-666666666666")
    resp = defects_client.patch(
        f"/defects/catalog/{nid}/edit",
        data={"title": "Корпус", "slug": "case", "kind": "node"},
    )
    assert resp.status_code == 200, resp.text[:300]
    assert captured.get("kind") == "node"


def test_post_device_rejects_unmappable_title(defects_client):
    """If title contains only special chars, derivation yields '' → 400 with Russian error."""
    resp = defects_client.post("/defects/devices", data={"title": "!@#$%", "slug": ""})
    assert resp.status_code == 400
    assert "идентификатор" in resp.text.lower()


def test_device_add_form_hides_slug_input(defects_client):
    """Add-mode form should NOT contain a slug input (it's auto-derived).
    The user only enters Название."""
    resp = defects_client.get("/defects/devices/new")
    assert resp.status_code == 200
    assert 'name="slug"' not in resp.text
    assert "Название" in resp.text


def test_device_edit_form_shows_slug_input(defects_client, monkeypatch):
    """Edit-mode form should show slug input as 'Идентификатор' for power-user rename."""
    import uuid as _uuid
    from app.services.defect_catalog.repository import DeviceNodeRow
    from app.web import defects as defects_mod

    nid = _uuid.UUID("77777777-7777-7777-7777-777777777777")
    fake_device = DeviceNodeRow(
        id=nid, parent_id=None, slug="apple", title="Apple",
        kind=None, sort_order=0,
    )

    async def _fake_get(session, _nid):
        return fake_device

    monkeypatch.setattr(defects_mod, "get_device_node", _fake_get)

    resp = defects_client.get(f"/defects/devices/{nid}/edit")
    assert resp.status_code == 200
    assert 'name="slug"' in resp.text
    assert "Идентификатор" in resp.text
    assert "Название" in resp.text


def test_device_tree_renders_action_icons(defects_client, monkeypatch):
    """GET /defects/devices/tree renders [+][✏][🗑] icons per node + hx-confirm для delete."""
    import uuid as _uuid
    from app.services.defect_catalog.repository import DeviceNodeRow
    from app.web import defects as defects_mod

    nid = _uuid.UUID("55555555-5555-5555-5555-555555555555")
    fake_node = DeviceNodeRow(
        id=nid, parent_id=None, slug="apple", title="Apple",
        kind=None, sort_order=0,
    )

    call_count = {"n": 0}

    async def _fake_list_children(session, parent_id):
        call_count["n"] += 1
        # First call (parent_id=None) returns the apple node; recursive calls return [].
        if call_count["n"] == 1:
            return [fake_node]
        return []

    monkeypatch.setattr(defects_mod, "list_device_children", _fake_list_children)

    resp = defects_client.get("/defects/devices/tree")
    assert resp.status_code == 200
    # Icon buttons for the apple node
    assert f'hx-get="/defects/devices/{nid}/new"'  in resp.text  # [+]
    assert f'hx-get="/defects/devices/{nid}/edit"' in resp.text  # [✏]
    assert f'hx-delete="/defects/devices/{nid}"'   in resp.text  # [🗑]
    # Native confirm на delete
    assert "hx-confirm=" in resp.text
    assert "Apple" in resp.text


def test_feature_form_kind_dropdown_uses_node_value(defects_client):
    """B1: dropdown «Раздел» must use value="node" (matches backend constraint
    feature_nodes.kind IN ('node','defect')), not "section". Otherwise selecting
    «Раздел» causes POST → 400 → silent HTMX fail."""
    resp = defects_client.get("/defects/catalog/new")
    assert resp.status_code == 200
    assert '<option value="node"' in resp.text
    assert '<option value="section"' not in resp.text
    # Label "Раздел" still shown to user — only the internal value changes
    assert "Раздел" in resp.text


def test_form_cancel_targets_whole_form(defects_client):
    """B2: «Отмена» must swap the whole form (not just the button itself).
    With hx-target="this" hx-swap="outerHTML" only the button vanished, form persisted.
    Fix: hx-target="closest form" replaces the entire form element."""
    resp = defects_client.get("/defects/catalog/new")
    assert resp.status_code == 200
    # Cancel button must target the form, not itself
    assert 'hx-target="closest form"' in resp.text
    # And must NOT have the old buggy target
    assert 'hx-target="this" hx-swap="outerHTML"' not in resp.text


def test_form_clears_mount_after_successful_post(defects_client):
    """B3: after successful POST the form must self-remove from #feature-form-mount /
    #device-form-mount. Otherwise user sees no «saved» feedback (tree updates below
    but form stays). Fix: hx-on::htmx:after-request listener that clears the parent
    on successful response."""
    resp = defects_client.get("/defects/catalog/new")
    assert resp.status_code == 200
    # Form has an after-request listener that clears its parent mount on success.
    assert "htmx:after-request" in resp.text
    assert "event.detail.successful" in resp.text


def test_kind_ru_filter():
    """Unit-test kind_ru filter — maps DB kind values to Russian display labels.
    'node' (used in seed, schema accepts node|defect) → «Раздел».
    'section' (spec value, future rename) → «Раздел» too for forward compat.
    'defect' → «Дефект»."""
    from app.web.defects import kind_ru
    assert kind_ru("node") == "Раздел"
    assert kind_ru("section") == "Раздел"
    assert kind_ru("defect") == "Дефект"
    # Unknown values pass through unchanged (defensive)
    assert kind_ru("unknown") == "unknown"
    assert kind_ru("") == ""


def test_node_color_filter():
    """Unit-test node_color(kind, depth) Jinja-filter.
    Sections: blue palette graduated darker→lighter by depth.
    Defects: slate (light gray) regardless of depth."""
    from app.web.defects import node_color
    # Defects — slate gray at any depth
    assert node_color("defect", 0) == "text-slate-500"
    assert node_color("defect", 3) == "text-slate-500"
    # Sections (kind=node or section) — darker→lighter
    assert node_color("node", 0)    == "text-blue-900"
    assert node_color("section", 0) == "text-blue-900"
    assert node_color("node", 1)    == "text-blue-700"
    assert node_color("node", 2)    == "text-blue-500"
    assert node_color("node", 3)    == "text-blue-400"
    assert node_color("node", 10)   == "text-blue-400"  # clamped
    # Unknown kind passes through with no color (defensive)
    assert node_color("unknown", 0) == ""


def test_feature_tree_applies_depth_aware_colors(defects_client, monkeypatch):
    """Tree-render integration: root section row gets text-blue-900, nested defect
    row gets text-slate-500 (light gray). Verifies recursive macro passes depth."""
    import uuid as _uuid
    from app.services.defect_catalog.repository import FeatureNodeRow
    from app.web import defects as defects_mod

    root_id = _uuid.UUID("90000000-0000-0000-0000-000000000001")
    child_id = _uuid.UUID("90000000-0000-0000-0000-000000000002")
    root_section = FeatureNodeRow(
        id=root_id, parent_id=None, kind="node", slug="display",
        title="Дисплей", sort_order=0, prompt_hint=None,
    )
    child_defect = FeatureNodeRow(
        id=child_id, parent_id=root_id, kind="defect", slug="cracked",
        title="Разбит", sort_order=0, prompt_hint=None,
    )

    call_count = {"n": 0}

    async def _fake_list_children(session, parent_id):
        call_count["n"] += 1
        if parent_id is None:
            return [root_section]
        if str(parent_id) == str(root_id):
            return [child_defect]
        return []

    monkeypatch.setattr(defects_mod, "list_feature_children", _fake_list_children)

    resp = defects_client.get("/defects/catalog/tree")
    assert resp.status_code == 200
    assert "text-blue-900" in resp.text   # root section
    assert "text-slate-500" in resp.text  # nested defect


def test_feature_tree_shows_russian_kind_label(defects_client, monkeypatch):
    """B-cosmetic: kind suffix in tree («[node]» рядом с «Дисплей») must
    render as «[Раздел]» / «[Дефект]» — no English «node» visible to user."""
    import uuid as _uuid
    from app.services.defect_catalog.repository import FeatureNodeRow
    from app.web import defects as defects_mod

    nid = _uuid.UUID("88888888-8888-8888-8888-888888888888")
    fake_section = FeatureNodeRow(
        id=nid, parent_id=None, kind="node", slug="display",
        title="Дисплей", sort_order=0, prompt_hint=None,
    )

    call_count = {"n": 0}

    async def _fake_list_children(session, parent_id):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [fake_section]
        return []

    monkeypatch.setattr(defects_mod, "list_feature_children", _fake_list_children)

    resp = defects_client.get("/defects/catalog/tree")
    assert resp.status_code == 200
    assert "[Раздел]" in resp.text
    assert "[node]" not in resp.text


def test_post_feature_accepts_kind_node(defects_client, monkeypatch):
    """B1 integration: POST /defects/catalog with kind=node (from dropdown «Раздел»)
    must succeed — backend already supports node, dropdown was the broken side."""
    captured: dict = {}

    async def _fake_create(session, *, parent_id, kind, slug, title, prompt_hint=None, sort_order=0):
        captured["kind"] = kind
        captured["slug"] = slug
        return uuid.uuid4()

    async def _fake_list_children(session, parent_id):
        return []

    from app.web import defects as defects_mod
    monkeypatch.setattr(defects_mod, "create_feature_node", _fake_create)
    monkeypatch.setattr(defects_mod, "list_feature_children", _fake_list_children)

    resp = defects_client.post(
        "/defects/catalog",
        data={"title": "Камера", "slug": "", "kind": "node"},
    )
    assert resp.status_code == 200, resp.text[:300]
    assert captured["kind"] == "node"
    assert captured["slug"] == "kamera"


def test_feature_tree_renders_action_icons(defects_client, monkeypatch):
    import uuid as _uuid
    from app.services.defect_catalog.repository import FeatureNodeRow
    from app.web import defects as defects_mod

    nid = _uuid.UUID("66666666-6666-6666-6666-666666666666")
    fake_feat = FeatureNodeRow(
        id=nid, parent_id=None, kind="section", slug="display",
        title="Дисплей", sort_order=0, prompt_hint=None,
    )

    call_count = {"n": 0}

    async def _fake_list_children(session, parent_id):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return [fake_feat]
        return []

    monkeypatch.setattr(defects_mod, "list_feature_children", _fake_list_children)

    resp = defects_client.get("/defects/catalog/tree")
    assert resp.status_code == 200
    assert f'hx-get="/defects/catalog/{nid}/new"'  in resp.text
    assert f'hx-get="/defects/catalog/{nid}/edit"' in resp.text
    assert f'hx-delete="/defects/catalog/{nid}"'   in resp.text
    assert "hx-confirm=" in resp.text
    assert "Дисплей" in resp.text

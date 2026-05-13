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
    assert "Дефекты" in resp.text or "Настройки дефектов" in resp.text


def test_defects_catalog_page_200(defects_client):
    resp = defects_client.get("/defects/catalog")
    assert resp.status_code == 200
    assert "Каталог признаков" in resp.text


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

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

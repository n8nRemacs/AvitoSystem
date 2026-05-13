"""Tests for Phase 2.0: feature-rules partial extraction + form tabs."""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.models import SearchProfile, User
from app.deps import db_session, require_user
from app.main import create_app


PROFILE_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


class _ScalarOne:
    def __init__(self, value: Any = None) -> None:
        self._value = value

    def scalar_one(self) -> Any:
        return self._value if self._value is not None else 0

    def scalar_one_or_none(self) -> Any:
        return self._value


class FakeSession:
    """Async session double — returns counts=0 for sidebar context."""

    async def execute(self, stmt: Any) -> _ScalarOne:
        return _ScalarOne(value=0)

    async def get(self, model: Any, ident: Any) -> Any:
        if model is SearchProfile and ident == PROFILE_ID:
            p = SearchProfile()
            p.id = PROFILE_ID
            p.user_id = USER_ID
            p.name = "iPhone 12 PM"
            p.avito_search_url = "https://www.avito.ru/test"
            p.is_active = True
            return p
        return None

    async def commit(self) -> None:
        return None


def _fake_user() -> User:
    user = User()
    user.id = USER_ID
    user.username = "owner"
    user.password_hash = "x"
    user.is_active = True
    user.is_admin = False
    return user


@pytest.fixture
def client(monkeypatch):
    # Mock service-layer + repo so we don't hit the DB
    from app.web import routers
    from app.services import search_profiles as svc

    async def _fake_get_profile(session, user_id, profile_id):
        if profile_id == PROFILE_ID:
            p = SearchProfile()
            p.id = PROFILE_ID
            p.user_id = USER_ID
            p.name = "iPhone 12 PM"
            p.avito_search_url = "https://www.avito.ru/test"
            p.import_source = None
            p.is_active = True
            return p
        return None

    async def _fake_load_rules(session, profile_id):
        return {}  # no rules set

    async def _fake_load_lib(session):
        return []  # empty V2 library

    async def _fake_load_state(session, profile_id):
        return {}

    monkeypatch.setattr(svc, "get_profile", _fake_get_profile)
    monkeypatch.setattr(routers.feat_repo, "load_profile_rules", _fake_load_rules)
    monkeypatch.setattr(routers, "_load_criteria_library", _fake_load_lib)
    monkeypatch.setattr(routers, "_load_profile_criteria_state", _fake_load_state)
    monkeypatch.setattr(routers, "_load_regions", lambda: [])

    app = create_app()
    fake_session = FakeSession()

    async def _fake_db():
        yield fake_session

    async def _fake_user_dep():
        return _fake_user()

    app.dependency_overrides[db_session] = _fake_db
    app.dependency_overrides[require_user] = _fake_user_dep
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_standalone_feature_rules_page_renders_partial(client):
    """Phase 2.0 Task 1: feature_rules.html includes _partials/feature_rules_section.html"""
    resp = client.get(f"/profiles/{PROFILE_ID}/feature-rules")
    assert resp.status_code == 200
    body = resp.text
    # Markup из partial (был в feature_rules.html, теперь в partial). Используем
    # data-rules-root как стабильный hook — id="rules-form" мы убираем, т.к.
    # partial может теоретически попасть на страницу дважды → дубликаты ID.
    assert 'data-rules-root' in body
    assert 'data-profile-id="' in body
    assert 'rule-seg' in body  # 3-state segment class
    # Section legends ОБЯЗАТЕЛЬНО есть
    assert 'Дисплей' in body
    assert 'Работоспособность' in body


def test_patch_feature_rule_still_works(client, monkeypatch):
    """Phase 2.0 Task 1: PATCH endpoint /profiles/{id}/feature-rules/{key} unchanged."""
    from app.web import routers

    upserts = []

    async def _fake_upsert(session, *, profile_id, feature_key, rule):
        upserts.append((str(profile_id), feature_key, rule))

    async def _fake_recompute(session, profile_id):
        return {"green": 0, "grey": 0, "red": 0}

    monkeypatch.setattr(routers.feat_repo, "upsert_profile_rule", _fake_upsert)
    monkeypatch.setattr(routers, "recompute_buckets_for_profile", _fake_recompute)

    resp = client.patch(
        f"/profiles/{PROFILE_ID}/feature-rules/display.glass_broken",
        json={"rule": "red"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "recompute": {"green": 0, "grey": 0, "red": 0}}
    assert upserts == [(str(PROFILE_ID), "display.glass_broken", "red")]

"""Shared fixtures for tests/web/.

Owns the FakeSession + client fixture used by Phase 2.0 + 2.1 profile-form
tests. Centralising here avoids the pytest_plugins-in-non-top-level-conftest
deprecation that was triggered when we tried to re-export from a test module.
"""
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
        return {}

    monkeypatch.setattr(svc, "get_profile", _fake_get_profile)
    monkeypatch.setattr(routers.feat_repo, "load_profile_rules", _fake_load_rules)
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

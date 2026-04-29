"""Tests for /settings/accounts page."""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.db.models import User
from app.deps import db_session, require_user
from app.main import create_app


class _FakeScalarResult:
    def __init__(self, value: Any = None) -> None:
        self._value = value

    def scalar_one(self) -> Any:
        return self._value if self._value is not None else 0


class FakeSession:
    """Async session double sufficient for the layout sidebar counts."""

    async def execute(self, stmt: Any) -> _FakeScalarResult:
        return _FakeScalarResult(value=0)

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _fake_user() -> User:
    user = User()
    user.id = uuid.uuid4()
    user.username = "owner"
    user.password_hash = "x"
    user.is_active = True
    user.is_admin = False
    return user


@pytest.fixture
def client():
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


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


def test_get_settings_accounts_renders_table(client, monkeypatch):
    """Replace _get_pool_for_request with a fake pool that returns 2 accounts."""
    fake_pool = AsyncMock()
    fake_pool.list_all_accounts.return_value = [
        {
            "id": "acc-1",
            "nickname": "Clone",
            "state": "active",
            "android_user_id": 10,
            "phone_serial": "110139ce",
            "consecutive_cooldowns": 0,
            "last_polled_at": "2026-04-28T12:00:00Z",
            "last_403_body": None,
            "cooldown_until": None,
        },
        {
            "id": "acc-2",
            "nickname": "Main",
            "state": "dead",
            "android_user_id": 0,
            "phone_serial": "110139ce",
            "consecutive_cooldowns": 5,
            "last_403_body": "<firewall>banned</firewall>",
            "cooldown_until": None,
            "last_polled_at": None,
        },
    ]
    fake_pool.xapi = AsyncMock()  # has aclose method

    async def fake_get_pool():
        return fake_pool

    from app.web import routers as web_routers_mod
    monkeypatch.setattr(web_routers_mod, "_get_pool_for_request", fake_get_pool)

    r = client.get("/settings/accounts")
    assert r.status_code == 200
    body = r.text
    assert "Clone" in body
    assert "Main" in body
    assert "active" in body or "🟢" in body
    assert "dead" in body or "🔴" in body
    assert "<firewall>banned</firewall>" in body or "&lt;firewall&gt;" in body


def test_get_settings_accounts_empty_state(client, monkeypatch):
    """When pool returns empty list, renders empty-state message."""
    fake_pool = AsyncMock()
    fake_pool.list_all_accounts.return_value = []
    fake_pool.xapi = AsyncMock()

    async def fake_get_pool():
        return fake_pool

    from app.web import routers as web_routers_mod
    monkeypatch.setattr(web_routers_mod, "_get_pool_for_request", fake_get_pool)

    r = client.get("/settings/accounts")
    assert r.status_code == 200
    assert "Нет аккаунтов в pool" in r.text


def test_get_settings_accounts_error_fallback(client, monkeypatch):
    """When pool raises, page renders 200 with empty accounts (graceful fallback)."""
    fake_pool = AsyncMock()
    fake_pool.list_all_accounts.side_effect = Exception("xapi down")
    fake_pool.xapi = AsyncMock()

    async def fake_get_pool():
        return fake_pool

    from app.web import routers as web_routers_mod
    monkeypatch.setattr(web_routers_mod, "_get_pool_for_request", fake_get_pool)

    r = client.get("/settings/accounts")
    assert r.status_code == 200
    assert "Нет аккаунтов в pool" in r.text

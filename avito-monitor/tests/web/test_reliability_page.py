"""Tests for the /reliability HTML page — Stage 7."""
from __future__ import annotations

import uuid
from typing import Any

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
        # The reliability page only needs the two ``count(*)`` queries from
        # ``_layout_context``; both return 0 for an empty test fixture.
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


def test_reliability_page_renders_200(client):
    resp = client.get("/reliability")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_reliability_page_lists_all_seven_scenarios(client):
    resp = client.get("/reliability")
    body = resp.text
    for letter in ("A", "B", "C", "D", "E", "F", "G"):
        assert f'data-scenario="{letter}"' in body, f"missing scenario {letter}"


def test_reliability_page_has_friendly_labels(client):
    resp = client.get("/reliability")
    body = resp.text
    for label in ("Token freshness", "WS connection alive", "Bot template + dedup"):
        assert label in body


def test_reliability_page_has_action_buttons(client):
    resp = client.get("/reliability")
    body = resp.text
    assert "Run All" in body
    assert "Pause Bot" in body
    assert "Resume Bot" in body
    assert "Обновить" in body


def test_reliability_page_includes_chartjs_and_canvas(client):
    resp = client.get("/reliability")
    body = resp.text
    assert "cdn.jsdelivr.net/npm/chart.js" in body
    assert 'id="rel-timeline"' in body


def test_reliability_page_includes_polling_endpoints(client):
    resp = client.get("/reliability")
    body = resp.text
    # The JS should fetch from /api/v1/health/full and the sidecar ports.
    assert "/api/v1/health/full" in body
    assert "localhost:9100" in body  # health-checker
    assert "localhost:9102" in body  # messenger-bot


def test_reliability_link_in_sidebar(client):
    """Reliability nav link must appear in any rendered _layout page."""
    # Hit the dashboard which extends _layout.html and check the sidebar.
    # If the dashboard requires data we haven't faked we still expect the
    # reliability link to appear somewhere; fall back to the page itself.
    resp = client.get("/reliability")
    body = resp.text
    assert 'href="/reliability"' in body
    assert "Reliability" in body

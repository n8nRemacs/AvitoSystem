"""Tests for the aggregated reliability snapshot — Stage 7.

We do NOT spin up Postgres for these unit tests — instead we override the
``db_session`` and ``require_user`` FastAPI deps so they yield a fake session
that returns canned ``health_checks`` rows. Sidecar ``/healthz`` traffic is
mocked with ``respx``.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.api import health_full as hf_module
from app.db.models import HealthCheck, User
from app.deps import db_session, require_user
from app.main import create_app


# ---------------------------------------------------------------------------
# Fakes — minimal SQLAlchemy session double, just enough for the aggregator.
# ---------------------------------------------------------------------------


class _FakeScalarResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = list(rows)

    def scalars(self) -> "_FakeScalarResult":
        return self

    def all(self) -> list[Any]:
        return self._rows


class FakeSession:
    """Async session double for the health-full aggregator.

    The aggregator runs at most two SELECTs:

    1. ``SELECT * FROM health_checks ORDER BY scenario, ts DESC`` — list mode
    2. ``SELECT ... WHERE scenario = X`` for the per-card history endpoint

    We pop pre-queued result lists in order.
    """

    def __init__(self, rows: list[HealthCheck]) -> None:
        self._all_rows = rows

    async def execute(self, stmt: Any) -> _FakeScalarResult:
        # Crude but sufficient: inspect the str() of the statement and decide
        # whether this is the global list or a per-scenario filter.
        sql = str(stmt).lower()
        # Default: global list — sorted by scenario, ts desc.
        if "scenario =" in sql or "scenario_1" in sql:
            # Pull the bound param if available; otherwise return everything.
            params = getattr(stmt, "compile", None)
            wanted: str | None = None
            try:
                # SQLAlchemy 2.0 — best-effort param extraction.
                compiled = stmt.compile(compile_kwargs={"literal_binds": False})
                for k, v in compiled.params.items():
                    if isinstance(v, str) and len(v) <= 4 and v.upper() in {
                        "A", "B", "C", "D", "E", "F", "G",
                    }:
                        wanted = v.upper()
                        break
            except Exception:
                pass
            del params
            if wanted is None:
                return _FakeScalarResult(self._all_rows)
            return _FakeScalarResult(
                [r for r in self._all_rows if r.scenario == wanted]
            )
        return _FakeScalarResult(self._all_rows)

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def _make_row(
    scenario: str, status: str, latency_ms: int, ts: datetime, details: dict | None = None
) -> HealthCheck:
    row = HealthCheck()
    row.id = abs(hash((scenario, ts.isoformat()))) % (10**9)
    row.scenario = scenario
    row.status = status
    row.latency_ms = latency_ms
    row.ts = ts
    row.details = details or {}
    return row


def _fake_user() -> User:
    user = User()
    user.id = uuid.uuid4()
    user.username = "test"
    user.password_hash = "x"
    user.is_active = True
    user.is_admin = False
    return user


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_rows() -> list[HealthCheck]:
    """Five canned rows: A pass (fresh), B fail (fresh), older A pass, etc."""
    now = datetime.now(UTC)
    return [
        _make_row("A", "pass", 732, now - timedelta(minutes=2),
                  {"hours_left": 18.1, "is_valid": True}),
        _make_row("A", "pass", 700, now - timedelta(minutes=10),
                  {"hours_left": 18.5, "is_valid": True}),
        _make_row("B", "fail", 105, now - timedelta(minutes=3),
                  {"reason": "no rotation in 24h", "rotations_24h": 0}),
        _make_row("C", "pass", 250, now - timedelta(minutes=4),
                  {"status_code": 200}),
        _make_row("G", "pass", 880, now - timedelta(minutes=6),
                  {"replies": 1}),
    ]


@pytest.fixture
def app_with_overrides(sample_rows):
    """FastAPI app with deps overridden to use FakeSession + a fake user."""
    app = create_app()
    fake_session = FakeSession(sample_rows)

    async def _fake_db():
        yield fake_session

    async def _fake_user_dep():
        return _fake_user()

    app.dependency_overrides[db_session] = _fake_db
    app.dependency_overrides[require_user] = _fake_user_dep
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def client(app_with_overrides):
    return TestClient(app_with_overrides)


def _mock_all_sidecars_pass() -> None:
    """Mock every sidecar /healthz to return 200 with realistic bodies."""
    urls = hf_module._resolve_service_urls()
    respx.get(urls["health-checker"]).mock(
        return_value=httpx.Response(200, json={
            "service": "health-checker", "uptime_sec": 1234, "scenarios": ["A","B","C","D","E","F","G"],
        })
    )
    respx.get(urls["messenger-bot"]).mock(
        return_value=httpx.Response(200, json={
            "service": "messenger-bot", "uptime_sec": 999, "sse_state": "connected",
            "total_replies": 6, "bot_enabled": True, "rate_used_last_hour": 0,
        })
    )
    respx.get(urls["activity-simulator"]).mock(
        return_value=httpx.Response(200, json={
            "service": "activity-simulator", "uptime_sec": 4321, "total_actions_today": 12,
        })
    )
    respx.get(urls["avito-mcp"]).mock(
        return_value=httpx.Response(200, json={"service": "avito-mcp", "uptime_sec": 50})
    )
    respx.get(urls["xapi"]).mock(
        return_value=httpx.Response(200, json={"status": "ok", "session_ttl_hours": 18.1})
    )


# ---------------------------------------------------------------------------
# Tests.
# ---------------------------------------------------------------------------


@respx.mock
def test_health_full_returns_top_level_keys(client):
    _mock_all_sidecars_pass()
    resp = client.get("/api/v1/health/full")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) >= {"ts", "scenarios", "services", "summary"}


@respx.mock
def test_health_full_picks_latest_per_scenario(client):
    """Two rows for A → only the most recent one ends up in the response."""
    _mock_all_sidecars_pass()
    resp = client.get("/api/v1/health/full")
    body = resp.json()
    a = body["scenarios"]["A"]
    assert a["status"] == "pass"
    assert a["latency_ms"] == 732  # the newer row, not 700
    assert a["details_summary"] == "TTL 18.1h"
    assert a["label"] == "Token freshness"


@respx.mock
def test_health_full_marks_unknown_when_scenario_missing(client):
    _mock_all_sidecars_pass()
    resp = client.get("/api/v1/health/full")
    body = resp.json()
    # D, E, F have no sample rows -> marked unknown.
    for letter in ("D", "E", "F"):
        assert body["scenarios"][letter]["status"] == "unknown"
        assert body["scenarios"][letter]["latency_ms"] is None


@respx.mock
def test_health_full_includes_scenario_b_failure(client):
    _mock_all_sidecars_pass()
    resp = client.get("/api/v1/health/full")
    body = resp.json()
    assert body["scenarios"]["B"]["status"] == "fail"
    assert body["summary"]["all_green"] is False
    assert "B" in body["summary"]["fail_scenarios"]


@respx.mock
def test_health_full_services_reachable(client):
    _mock_all_sidecars_pass()
    resp = client.get("/api/v1/health/full")
    body = resp.json()
    services = body["services"]
    assert set(services.keys()) == {
        "health-checker", "messenger-bot", "activity-simulator", "avito-mcp", "xapi",
    }
    for name, payload in services.items():
        assert payload["reachable"] is True, f"{name} should be reachable"
    assert services["messenger-bot"]["sse_state"] == "connected"
    assert services["xapi"]["session_ttl_hours"] == 18.1
    assert body["summary"]["unreachable_services"] == []


@respx.mock
def test_health_full_handles_unreachable_service(client):
    """When a sidecar refuses connections, the field is reachable=false + error."""
    urls = hf_module._resolve_service_urls()
    # All others return 200, but messenger-bot raises ConnectError.
    respx.get(urls["health-checker"]).mock(
        return_value=httpx.Response(200, json={"service": "health-checker", "uptime_sec": 1})
    )
    respx.get(urls["messenger-bot"]).mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    respx.get(urls["activity-simulator"]).mock(
        return_value=httpx.Response(200, json={"service": "activity-simulator", "uptime_sec": 1})
    )
    respx.get(urls["avito-mcp"]).mock(
        return_value=httpx.Response(200, json={"service": "avito-mcp"})
    )
    respx.get(urls["xapi"]).mock(
        return_value=httpx.Response(500, text="oops")
    )
    resp = client.get("/api/v1/health/full")
    body = resp.json()
    assert body["services"]["messenger-bot"]["reachable"] is False
    assert "ConnectError" in body["services"]["messenger-bot"]["error"]
    assert body["services"]["xapi"]["reachable"] is False
    assert body["services"]["xapi"]["status_code"] == 500
    assert body["summary"]["all_green"] is False
    assert "messenger-bot" in body["summary"]["unreachable_services"]
    assert "xapi" in body["summary"]["unreachable_services"]


@respx.mock
def test_health_full_requires_auth():
    """Without the override, ``require_user`` should redirect / 4xx — NEVER 200."""
    app = create_app()  # no overrides
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/api/v1/health/full")
    # require_user raises 303 redirect to /login when there's no session cookie.
    assert resp.status_code in (303, 401, 403, 307)


@respx.mock
def test_scenario_history_endpoint(client):
    _mock_all_sidecars_pass()
    resp = client.get("/api/v1/health/scenario/A?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert body["scenario"] == "A"
    assert body["label"] == "Token freshness"
    assert len(body["rows"]) == 2
    # Should be sorted desc — first row is the freshest.
    assert body["rows"][0]["latency_ms"] == 732


@respx.mock
def test_scenario_history_unknown_letter_returns_error_field(client):
    _mock_all_sidecars_pass()
    resp = client.get("/api/v1/health/scenario/Z")
    assert resp.status_code == 200
    body = resp.json()
    assert body["error"] == "unknown scenario"
    assert body["rows"] == []


def test_summarise_details_branches():
    """The summariser handles each scenario letter cleanly."""
    fn = hf_module._summarise_details
    assert fn("A", {"hours_left": 18.123}) == "TTL 18.1h"
    assert fn("B", {"rotations_24h": 3}) == "3 rot/24h"
    assert fn("C", {"status_code": 200}) == "HTTP 200"
    assert fn("E", {"round_trip_ms": 871}) == "RTT 871 ms"
    assert fn("G", {"replies": 1}) == "1 replies"
    assert fn("F", {"reason": "timeout"}) == "HTTP None" or fn("F", {"reason": "timeout"}) == "timeout"
    assert fn("A", None) is None
    assert fn("A", {"error": "boom"}) == "boom"

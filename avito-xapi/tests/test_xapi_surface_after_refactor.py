"""Pin-down test: xapi keeps these endpoints after Phase 3 refactor."""
from fastapi.testclient import TestClient

EXPECTED_ROUTES = {
    "POST /api/v1/sessions",
    "GET /api/v1/sessions/current",
    "DELETE /api/v1/sessions",
    "GET /api/v1/sessions/history",
    "GET /api/v1/sessions/token-details",
    "GET /api/v1/sessions/alerts",
    "GET /api/v1/accounts",
    "POST /api/v1/accounts/poll-claim",
    "POST /api/v1/accounts/{account_id}/report",
    "GET /api/v1/accounts/{account_id}/session-for-sync",
    "PATCH /api/v1/accounts/{account_id}/state",
}

REMOVED_ROUTES = {
    "POST /api/v1/accounts/{account_id}/refresh-cycle",
    "GET /api/v1/devices/me/commands",
    "POST /api/v1/devices/me/commands",
    "POST /api/v1/devices/me/commands/{command_id}/ack",
}


def _route_signatures(app) -> set[str]:
    """Render every HTTP route as ``METHOD path`` strings.

    WebSocket and Mount routes don't expose ``.methods`` so we skip them.
    """
    sigs: set[str] = set()
    for r in app.routes:
        methods = getattr(r, "methods", None) or []
        path = getattr(r, "path", None)
        if not path:
            continue
        for m in methods:
            sigs.add(f"{m} {path}")
    return sigs


def test_expected_routes_present(client: TestClient):
    """All endpoints we keep must exist in the FastAPI app."""
    routes = _route_signatures(client.app)
    missing = EXPECTED_ROUTES - routes
    assert not missing, f"Missing routes after refactor: {missing}"


def test_removed_routes_absent(client: TestClient):
    """All endpoints we removed must NOT exist."""
    routes = _route_signatures(client.app)
    leftover = REMOVED_ROUTES & routes
    assert not leftover, f"Should-be-removed routes still present: {leftover}"

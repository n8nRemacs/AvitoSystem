"""Tests for realtime SSE endpoints."""

from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from tests.conftest import (
    make_authed_sb, make_test_jwt, TEST_API_KEY, TEST_TENANT_ID,
    ALL_FEATURES,
)


def _run_realtime_request(mock_sb, mock_ws_manager, method="GET", path="/api/v1/messenger/realtime/status",
                          headers=None, json_body=None, use_query_auth=False):
    """Run request with ws_manager patched as new= instead of return_value=."""
    from src.main import app

    all_headers = {}
    if not use_query_auth:
        all_headers["X-Api-Key"] = TEST_API_KEY
    if headers:
        all_headers.update(headers)

    sb_patches = [
        patch("src.storage.supabase.get_supabase", return_value=mock_sb),
        patch("src.middleware.auth.get_supabase", return_value=mock_sb),
        patch("src.workers.session_reader.get_supabase", return_value=mock_sb),
    ]
    # ws_manager must be patched with new= (object replacement), not return_value=
    ws_patch = patch("src.routers.realtime.ws_manager", mock_ws_manager)

    all_patches = sb_patches + [ws_patch]
    for p in all_patches:
        p.__enter__()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        url = path
        if use_query_auth:
            url += f"{'&' if '?' in url else '?'}api_key={TEST_API_KEY}"
        if method == "GET":
            return client.get(url, headers=all_headers)
        elif method == "POST":
            return client.post(url, headers=all_headers, json=json_body)
    finally:
        for p in reversed(all_patches):
            p.__exit__(None, None, None)


# ── Status endpoint ──────────────────────────────────

def test_realtime_status():
    """GET /messenger/realtime/status → connection info."""
    mock_sb = make_authed_sb()
    mock_ws_manager = MagicMock()
    mock_ws_manager.get_status = MagicMock(return_value={
        "connected": False, "subscribers": 0,
    })

    resp = _run_realtime_request(mock_sb, mock_ws_manager)
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is False
    assert data["subscribers"] == 0


def test_realtime_status_connected():
    """GET /messenger/realtime/status → connected=True when WS is active."""
    mock_sb = make_authed_sb()
    mock_ws_manager = MagicMock()
    mock_ws_manager.get_status = MagicMock(return_value={
        "connected": True, "subscribers": 2, "tenant_id": TEST_TENANT_ID,
    })

    resp = _run_realtime_request(mock_sb, mock_ws_manager)
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True
    assert data["subscribers"] == 2


# ── Stop endpoint ────────────────────────────────────

def test_realtime_stop():
    """POST /messenger/realtime/stop → ok."""
    mock_sb = make_authed_sb()
    mock_ws_manager = MagicMock()
    mock_ws_manager._stop_connection = AsyncMock()

    resp = _run_realtime_request(mock_sb, mock_ws_manager, method="POST",
                                  path="/api/v1/messenger/realtime/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Feature gating ───────────────────────────────────

def test_realtime_status_no_feature():
    """Status endpoint returns 403 when avito.messenger not in toolkit."""
    mock_sb = make_authed_sb(features=["avito.sessions"])
    mock_ws_manager = MagicMock()

    resp = _run_realtime_request(mock_sb, mock_ws_manager)
    assert resp.status_code == 403


# ── Auth via query param ─────────────────────────────

def test_auth_via_query_param():
    """API key in query string works (for EventSource compatibility)."""
    mock_sb = make_authed_sb()
    mock_ws_manager = MagicMock()
    mock_ws_manager.get_status = MagicMock(return_value={
        "connected": False, "subscribers": 0,
    })

    resp = _run_realtime_request(mock_sb, mock_ws_manager, use_query_auth=True)
    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is False

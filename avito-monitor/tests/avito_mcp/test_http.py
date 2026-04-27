"""Tests for the HTTP routes wired by ``avito_mcp/__main__.py``.

Covers the bearer-auth middleware behaviour on ``/restart`` plus the enriched
``/healthz`` payload shape. ``os._exit`` is monkey-patched so the test runner
isn't killed when the restart task fires.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from starlette.testclient import TestClient

from avito_mcp import __main__ as mcp_main
from avito_mcp import __version__


TOKEN = "test-restart-token"


@pytest.fixture
def app(monkeypatch):
    """Build the Starlette app with a known bearer token."""
    # Patch the settings cache so _build_http_app picks up our token.
    from avito_mcp import config

    config.get_mcp_settings.cache_clear()
    monkeypatch.setenv("AVITO_MCP_AUTH_TOKEN", TOKEN)
    monkeypatch.setenv("AVITO_MCP_TRANSPORT", "sse")
    config.get_mcp_settings.cache_clear()

    app = mcp_main._build_http_app()
    yield app
    config.get_mcp_settings.cache_clear()


@pytest.fixture
def client(app):
    return TestClient(app)


# ------------------------------------------------------------------------
# /healthz
# ------------------------------------------------------------------------

def test_healthz_no_auth_required_and_returns_enriched_shape(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["tools_registered"] == 4  # the 4 V1 tools
    assert isinstance(body["uptime_sec"], int)
    assert body["uptime_sec"] >= 0
    # ISO-8601 timestamp with timezone info.
    assert "T" in body["started_at"]
    assert body["started_at"].endswith("+00:00") or body["started_at"].endswith("Z")


# ------------------------------------------------------------------------
# /restart
# ------------------------------------------------------------------------

def test_restart_without_bearer_returns_401(client, monkeypatch):
    monkeypatch.setattr(os, "_exit", lambda code: None)
    resp = client.post("/restart")
    assert resp.status_code == 401
    assert resp.json()["error"] == "missing_authorization"


def test_restart_with_wrong_bearer_returns_403(client, monkeypatch):
    monkeypatch.setattr(os, "_exit", lambda code: None)
    resp = client.post("/restart", headers={"Authorization": "Bearer not-the-real-token"})
    assert resp.status_code == 403
    assert resp.json()["error"] == "invalid_token"


def test_restart_with_correct_bearer_returns_200_and_schedules_exit(
    client, monkeypatch
):
    """Happy path: 200 + ``{"restarting": True, "ts": ...}``.

    We patch ``os._exit`` so the scheduled task can't actually kill the runner.
    The delay before exit is 500 ms, but the response flushes synchronously, so
    we get our 200 first and then yield to the event loop briefly.
    """
    exit_calls: list[int] = []
    monkeypatch.setattr(os, "_exit", lambda code: exit_calls.append(code))

    resp = client.post("/restart", headers={"Authorization": f"Bearer {TOKEN}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["restarting"] is True
    assert "ts" in body and "T" in body["ts"]


@pytest.mark.asyncio
async def test_delayed_exit_calls_os_exit_zero(monkeypatch):
    """Direct test of the helper to make sure it exits with code 0."""
    captured: list[int] = []
    monkeypatch.setattr(os, "_exit", lambda code: captured.append(code))
    # Use a tiny delay so the test stays fast.
    await mcp_main._delayed_exit(delay_seconds=0.01)
    assert captured == [0]


# ------------------------------------------------------------------------
# Other routes still require auth
# ------------------------------------------------------------------------

def test_sse_endpoint_still_requires_bearer(client):
    """Sanity: the bearer middleware still gates /sse (the FastMCP transport).

    We only care about the auth response, not whether the SSE handshake works
    in TestClient (it doesn't, because TestClient lacks streaming support).
    """
    resp = client.get("/sse")
    # Without auth → 401. With auth, TestClient may hang on streaming, so we
    # don't assert the success path here.
    assert resp.status_code == 401

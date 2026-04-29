"""Tests for subscriptions router: account_id pool-aware dispatch (T17a)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from tests.conftest import (
    ALL_FEATURES,
    TEST_API_KEY,
    TEST_API_KEY_HASH,
    TEST_API_KEY_ID,
    TEST_SUPERVISOR_ID,
    TEST_TENANT_ID,
    TEST_TOOLKIT_ID,
    make_authed_sb,
)


# ── helpers ──────────────────────────────────────────────────────────────

def _make_avito_client_mock(
    deeplink: str = "ru.avito://1/items/search?categoryId=84&locationId=621540",
    list_items: list | None = None,
) -> MagicMock:
    """Build an AvitoHttpClient mock that satisfies subscription endpoint calls."""
    mock = MagicMock()
    mock.get_subscription_deeplink = AsyncMock(return_value=deeplink)
    mock.list_subscriptions = AsyncMock(return_value=list_items or [])
    mock.search_items = AsyncMock(return_value={"items": [], "total": 0})
    return mock


def _make_session(account_id: str = "acc-XYZ") -> MagicMock:
    """Minimal SessionData-like mock."""
    s = MagicMock()
    s.session_token = "JWT"
    s.device_id = "dev1"
    s.fingerprint = "fp1"
    s.remote_device_id = "rdid1"
    s.user_hash = "uh1"
    s.cookies = {}
    s.account_id = account_id
    return s


def _run_authed(mock_sb, method: str, path: str) -> object:
    """Run an authenticated request against the FastAPI app with Supabase patched."""
    from src.main import app

    patches = [
        patch("src.middleware.auth.get_supabase", return_value=mock_sb),
        patch("src.storage.supabase.get_supabase", return_value=mock_sb),
        patch("src.routers.sessions.get_supabase", return_value=mock_sb),
        patch("src.workers.session_reader.get_supabase", return_value=mock_sb),
        patch("src.routers.farm.get_supabase", return_value=mock_sb),
    ]
    for p in patches:
        p.__enter__()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        return client.request(method, path, headers={"X-Api-Key": TEST_API_KEY})
    finally:
        for p in reversed(patches):
            p.__exit__(None, None, None)


# ── _resolve_client unit tests ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_client_no_account_id_calls_load_active_session():
    """_resolve_client(ctx, None) → calls load_active_session (legacy path)."""
    from src.routers.subscriptions import _resolve_client

    session = _make_session()
    avito_client_instance = _make_avito_client_mock()
    ctx = MagicMock()
    ctx.tenant.id = "tenant-001"

    with patch("src.routers.subscriptions.load_active_session", return_value=session) as mock_las, \
         patch("src.routers.subscriptions.AvitoHttpClient", return_value=avito_client_instance):
        result = await _resolve_client(ctx, None)

    mock_las.assert_called_once_with("tenant-001")
    assert result is avito_client_instance


@pytest.mark.asyncio
async def test_resolve_client_with_account_id_calls_load_session_for_account():
    """_resolve_client(ctx, 'acc-X') → calls load_session_for_account(sb, 'acc-X')."""
    from src.routers.subscriptions import _resolve_client

    session = _make_session("acc-X")
    avito_client_instance = _make_avito_client_mock()
    mock_sb = MagicMock()
    ctx = MagicMock()
    ctx.tenant.id = "tenant-001"

    async def fake_load_for_acc(sb, acc_id):
        return session

    with patch("src.routers.subscriptions.get_supabase", return_value=mock_sb), \
         patch("src.routers.subscriptions.load_session_for_account", side_effect=fake_load_for_acc) as mock_lfa, \
         patch("src.routers.subscriptions.AvitoHttpClient", return_value=avito_client_instance):
        result = await _resolve_client(ctx, "acc-X")

    mock_lfa.assert_called_once_with(mock_sb, "acc-X")
    assert result is avito_client_instance


@pytest.mark.asyncio
async def test_resolve_client_with_account_id_no_session_raises_409():
    """_resolve_client raises HTTP 409 when load_session_for_account returns None."""
    from src.routers.subscriptions import _resolve_client

    ctx = MagicMock()
    ctx.tenant.id = "tenant-001"
    mock_sb = MagicMock()

    async def fake_load_none(sb, acc_id):
        return None

    with patch("src.routers.subscriptions.get_supabase", return_value=mock_sb), \
         patch("src.routers.subscriptions.load_session_for_account", side_effect=fake_load_none):
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_client(ctx, "acc-GONE")

    assert exc_info.value.status_code == 409
    assert "acc-GONE" in exc_info.value.detail


@pytest.mark.asyncio
async def test_resolve_client_legacy_no_session_raises_404():
    """_resolve_client raises HTTP 404 when load_active_session returns None."""
    from src.routers.subscriptions import _resolve_client

    ctx = MagicMock()
    ctx.tenant.id = "tenant-001"

    with patch("src.routers.subscriptions.load_active_session", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_client(ctx, None)

    assert exc_info.value.status_code == 404


# ── list_subscriptions endpoint ───────────────────────────────────────────

def test_list_subscriptions_no_account_id_resolves_via_legacy():
    """/subscriptions without ?account_id → _resolve_client called with account_id=None."""
    mock_sb = make_authed_sb()
    avito_client = _make_avito_client_mock(list_items=[{"id": 1, "title": "Test"}])

    called = {}

    async def fake_resolve(ctx, account_id):
        called["account_id"] = account_id
        return avito_client

    with patch("src.routers.subscriptions._resolve_client", new=fake_resolve):
        resp = _run_authed(mock_sb, "GET", "/api/v1/subscriptions")

    assert resp.status_code == 200
    assert called.get("account_id") is None
    assert resp.json()["count"] == 1


def test_list_subscriptions_with_account_id_forwarded():
    """/subscriptions?account_id=acc-XYZ → _resolve_client receives 'acc-XYZ'."""
    mock_sb = make_authed_sb()
    avito_client = _make_avito_client_mock(list_items=[])

    called = {}

    async def fake_resolve(ctx, account_id):
        called["account_id"] = account_id
        return avito_client

    with patch("src.routers.subscriptions._resolve_client", new=fake_resolve):
        resp = _run_authed(mock_sb, "GET", "/api/v1/subscriptions?account_id=acc-XYZ")

    assert resp.status_code == 200
    assert called.get("account_id") == "acc-XYZ"


# ── get_subscription_items endpoint ──────────────────────────────────────

def test_get_subscription_items_no_account_id():
    """/subscriptions/42/items without ?account_id → account_id=None in _resolve_client."""
    mock_sb = make_authed_sb()
    avito_client = _make_avito_client_mock()

    called = {}

    async def fake_resolve(ctx, account_id):
        called["account_id"] = account_id
        return avito_client

    with patch("src.routers.subscriptions._resolve_client", new=fake_resolve):
        resp = _run_authed(mock_sb, "GET", "/api/v1/subscriptions/42/items")

    assert resp.status_code == 200
    assert called.get("account_id") is None


def test_get_subscription_items_with_account_id():
    """/subscriptions/42/items?account_id=acc-XYZ → forwarded to _resolve_client."""
    mock_sb = make_authed_sb()
    avito_client = _make_avito_client_mock()

    called = {}

    async def fake_resolve(ctx, account_id):
        called["account_id"] = account_id
        return avito_client

    with patch("src.routers.subscriptions._resolve_client", new=fake_resolve):
        resp = _run_authed(mock_sb, "GET", "/api/v1/subscriptions/42/items?account_id=acc-XYZ")

    assert resp.status_code == 200
    assert called.get("account_id") == "acc-XYZ"


# ── get_subscription_search_params endpoint ───────────────────────────────

def test_get_subscription_search_params_account_id_forwarded():
    """/subscriptions/42/search-params?account_id=acc-XYZ → forwarded to _resolve_client."""
    mock_sb = make_authed_sb()
    avito_client = _make_avito_client_mock(
        deeplink="ru.avito://1/items/search?categoryId=84&locationId=621540"
    )

    called = {}

    async def fake_resolve(ctx, account_id):
        called["account_id"] = account_id
        return avito_client

    with patch("src.routers.subscriptions._resolve_client", new=fake_resolve):
        resp = _run_authed(mock_sb, "GET", "/api/v1/subscriptions/42/search-params?account_id=acc-XYZ")

    assert resp.status_code == 200
    assert called.get("account_id") == "acc-XYZ"
    data = resp.json()
    assert "search_params" in data
    assert data["search_params"]["categoryId"] == "84"

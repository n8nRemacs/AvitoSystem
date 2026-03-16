from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from src.storage.supabase import QueryResult

TEST_API_KEY = "test_dev_key_123"
TEST_API_KEY_HASH = "6096e738bb666ab4378531d758e3d913dbcddc48a0a1a82fcc01e1450dba9082"
TEST_TENANT_ID = "c0000000-0000-0000-0000-000000000001"
TEST_SUPERVISOR_ID = "a0000000-0000-0000-0000-000000000001"
TEST_TOOLKIT_ID = "b0000000-0000-0000-0000-000000000001"
TEST_API_KEY_ID = "d0000000-0000-0000-0000-000000000001"


def _make_mock_sb(*, key_data=None, tenant_data=None, toolkit_data=None):
    """Create a mock SupabaseClient that returns configured data per table."""
    mock_sb = MagicMock()

    call_counter = {"n": 0}

    responses = []
    if key_data is not None:
        responses.append(QueryResult(data=key_data))
    else:
        responses.append(QueryResult(data=[]))

    if tenant_data is not None:
        responses.append(QueryResult(data=tenant_data))

    if toolkit_data is not None:
        responses.append(QueryResult(data=toolkit_data))

    # Extra responses for update calls etc
    for _ in range(5):
        responses.append(QueryResult(data=[]))

    def make_chain():
        chain = MagicMock()
        chain.select = MagicMock(return_value=chain)
        chain.eq = MagicMock(return_value=chain)
        chain.neq = MagicMock(return_value=chain)
        chain.order = MagicMock(return_value=chain)
        chain.limit = MagicMock(return_value=chain)
        chain.insert = MagicMock(return_value=chain)
        chain.update = MagicMock(return_value=chain)
        chain.delete = MagicMock(return_value=chain)

        def execute():
            idx = min(call_counter["n"], len(responses) - 1)
            call_counter["n"] += 1
            return responses[idx]

        chain.execute = MagicMock(side_effect=execute)
        return chain

    mock_sb.table = MagicMock(side_effect=lambda name: make_chain())
    return mock_sb


def _run_request(mock_sb, path="/api/v1/sessions/current", headers=None, extra_patches=None):
    """Run a request within properly patched context."""
    patches = {
        "src.storage.supabase.get_supabase": mock_sb,
        "src.middleware.auth.get_supabase": mock_sb,
    }
    if extra_patches:
        patches.update(extra_patches)

    from src.main import app

    # Apply all patches
    ctx_managers = [patch(k, return_value=v) for k, v in patches.items()]
    for cm in ctx_managers:
        cm.__enter__()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        return client.get(path, headers=headers or {})
    finally:
        for cm in reversed(ctx_managers):
            cm.__exit__(None, None, None)


def test_no_api_key_returns_401():
    mock_sb = _make_mock_sb()
    resp = _run_request(mock_sb)
    assert resp.status_code == 401
    assert "Missing X-Api-Key" in resp.json()["detail"]


def test_invalid_api_key_returns_401():
    mock_sb = _make_mock_sb(key_data=[])
    resp = _run_request(mock_sb, headers={"X-Api-Key": "wrong_key"})
    assert resp.status_code == 401
    assert "Invalid API key" in resp.json()["detail"]


def test_valid_api_key_resolves_tenant():
    mock_sb = _make_mock_sb(
        key_data=[{"id": TEST_API_KEY_ID, "tenant_id": TEST_TENANT_ID, "key_hash": TEST_API_KEY_HASH, "name": "Dev", "is_active": True}],
        tenant_data=[{"id": TEST_TENANT_ID, "supervisor_id": TEST_SUPERVISOR_ID, "toolkit_id": TEST_TOOLKIT_ID,
                       "name": "TestTenant", "email": "t@t.com", "is_active": True, "subscription_until": "2027-01-01T00:00:00+00:00", "settings": {}}],
        toolkit_data=[{"id": TEST_TOOLKIT_ID, "supervisor_id": TEST_SUPERVISOR_ID, "name": "Full",
                        "features": ["avito.sessions", "avito.messenger", "avito.search", "avito.calls", "avito.farm"],
                        "limits": {}, "price_monthly": 0, "is_active": True}],
    )
    resp = _run_request(mock_sb, headers={"X-Api-Key": TEST_API_KEY},
                        extra_patches={"src.routers.sessions.load_active_session": None})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_deactivated_tenant_returns_403():
    mock_sb = _make_mock_sb(
        key_data=[{"id": TEST_API_KEY_ID, "tenant_id": TEST_TENANT_ID, "key_hash": TEST_API_KEY_HASH, "name": "Dev", "is_active": True}],
        tenant_data=[{"id": TEST_TENANT_ID, "supervisor_id": TEST_SUPERVISOR_ID, "toolkit_id": TEST_TOOLKIT_ID,
                       "name": "TestTenant", "email": "t@t.com", "is_active": False, "subscription_until": "2027-01-01T00:00:00+00:00", "settings": {}}],
    )
    resp = _run_request(mock_sb, headers={"X-Api-Key": TEST_API_KEY})
    assert resp.status_code == 403
    assert "deactivated" in resp.json()["detail"].lower()


def test_expired_subscription_returns_403():
    mock_sb = _make_mock_sb(
        key_data=[{"id": TEST_API_KEY_ID, "tenant_id": TEST_TENANT_ID, "key_hash": TEST_API_KEY_HASH, "name": "Dev", "is_active": True}],
        tenant_data=[{"id": TEST_TENANT_ID, "supervisor_id": TEST_SUPERVISOR_ID, "toolkit_id": TEST_TOOLKIT_ID,
                       "name": "TestTenant", "email": "t@t.com", "is_active": True, "subscription_until": "2020-01-01T00:00:00+00:00", "settings": {}}],
    )
    resp = _run_request(mock_sb, headers={"X-Api-Key": TEST_API_KEY})
    assert resp.status_code == 403
    assert "expired" in resp.json()["detail"].lower()


def test_feature_not_in_toolkit_returns_403():
    mock_sb = _make_mock_sb(
        key_data=[{"id": TEST_API_KEY_ID, "tenant_id": TEST_TENANT_ID, "key_hash": TEST_API_KEY_HASH, "name": "Dev", "is_active": True}],
        tenant_data=[{"id": TEST_TENANT_ID, "supervisor_id": TEST_SUPERVISOR_ID, "toolkit_id": TEST_TOOLKIT_ID,
                       "name": "TestTenant", "email": "t@t.com", "is_active": True, "subscription_until": "2027-01-01T00:00:00+00:00", "settings": {}}],
        toolkit_data=[{"id": TEST_TOOLKIT_ID, "supervisor_id": TEST_SUPERVISOR_ID, "name": "Limited",
                        "features": ["avito.messenger"],
                        "limits": {}, "price_monthly": 0, "is_active": True}],
    )
    resp = _run_request(mock_sb, headers={"X-Api-Key": TEST_API_KEY})
    assert resp.status_code == 403
    assert "not available" in resp.json()["detail"].lower()


def test_health_skips_auth():
    mock_sb = _make_mock_sb()
    resp = _run_request(mock_sb, path="/health")
    assert resp.status_code == 200

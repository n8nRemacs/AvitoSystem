import pytest
import json
import base64
import time
from unittest.mock import MagicMock, patch
from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError

# Seed data constants matching 002_seed.sql
TEST_SUPERVISOR_ID = "a0000000-0000-0000-0000-000000000001"
TEST_TOOLKIT_ID = "b0000000-0000-0000-0000-000000000001"
TEST_TENANT_ID = "c0000000-0000-0000-0000-000000000001"
TEST_API_KEY_ID = "d0000000-0000-0000-0000-000000000001"
TEST_API_KEY = "test_dev_key_123"
TEST_API_KEY_HASH = "6096e738bb666ab4378531d758e3d913dbcddc48a0a1a82fcc01e1450dba9082"

ALL_FEATURES = ["avito.sessions", "avito.messenger", "avito.search", "avito.calls", "avito.farm"]


def make_test_jwt(user_id=99999999, exp_offset=86400):
    """Create a parseable test JWT with configurable expiry offset from now."""
    header = {"alg": "HS512", "typ": "JWT"}
    payload = {
        "user_id": user_id, "sub": user_id,
        "iat": int(time.time()), "exp": int(time.time()) + exp_offset,
        "install_id": "test-install", "client_id": "avito-android", "platform": "android",
    }
    h = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{h}.{p}.MOCK_SIG"


def make_mock_sb(response_data_list):
    """Create mock SupabaseClient with sequential QueryResult responses.

    response_data_list: list of lists, each becomes QueryResult(data=item).
    """
    from src.storage.supabase import QueryResult
    responses = [QueryResult(data=d) for d in response_data_list]
    for _ in range(15):
        responses.append(QueryResult(data=[]))
    call_counter = {"n": 0}

    def _make_chain():
        chain = MagicMock()
        for m in ("select", "eq", "neq", "order", "limit", "insert", "update", "delete", "is_"):
            setattr(chain, m, MagicMock(return_value=chain))

        def execute():
            idx = min(call_counter["n"], len(responses) - 1)
            call_counter["n"] += 1
            return responses[idx]

        chain.execute = MagicMock(side_effect=execute)
        return chain

    mock_sb = MagicMock()
    mock_sb.table = MagicMock(side_effect=lambda name: _make_chain())
    return mock_sb


def make_authed_sb(*extra_data, features=None):
    """Create mock SupabaseClient with auth middleware responses + endpoint responses.

    Auth middleware makes 4 sequential queries:
      1. api_keys lookup
      2. tenants lookup
      3. toolkits lookup
      4. update api_key last_used_at
    Then extra_data provides responses for endpoint-specific queries.
    """
    if features is None:
        features = ALL_FEATURES
    data_list = [
        [{"id": TEST_API_KEY_ID, "tenant_id": TEST_TENANT_ID,
          "key_hash": TEST_API_KEY_HASH, "name": "Dev", "is_active": True}],
        [{"id": TEST_TENANT_ID, "supervisor_id": TEST_SUPERVISOR_ID,
          "toolkit_id": TEST_TOOLKIT_ID, "name": "TestTenant", "email": "t@t.com",
          "is_active": True, "subscription_until": "2027-01-01T00:00:00+00:00", "settings": {}}],
        [{"id": TEST_TOOLKIT_ID, "supervisor_id": TEST_SUPERVISOR_ID, "name": "Full",
          "features": features, "limits": {}, "price_monthly": 0, "is_active": True}],
        [],  # update api_key last_used_at
    ]
    data_list.extend(extra_data)
    return make_mock_sb(data_list)


def run_request(mock_sb, method="GET", path="/api/v1/sessions/current",
                headers=None, json_body=None, extra_patches=None):
    """Run authenticated request via TestClient with all Supabase modules patched."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from src.main import app

    all_headers = {"X-Api-Key": TEST_API_KEY}
    if headers:
        all_headers.update(headers)

    patches_dict = {
        "src.storage.supabase.get_supabase": mock_sb,
        "src.middleware.auth.get_supabase": mock_sb,
        "src.routers.sessions.get_supabase": mock_sb,
        "src.workers.session_reader.get_supabase": mock_sb,
        "src.routers.farm.get_supabase": mock_sb,
    }
    if extra_patches:
        patches_dict.update(extra_patches)

    ctx_managers = [patch(k, return_value=v) for k, v in patches_dict.items()]
    for cm in ctx_managers:
        cm.__enter__()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        if method == "GET":
            return client.get(path, headers=all_headers)
        elif method == "POST":
            return client.post(path, headers=all_headers, json=json_body)
        elif method == "DELETE":
            return client.delete(path, headers=all_headers)
    finally:
        for cm in reversed(ctx_managers):
            cm.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

def _curl_error(status: int) -> CurlHTTPError:
    """Build a curl_cffi HTTPError with a fake response carrying the given status."""
    fake_resp = type("R", (), {"status_code": status, "reason": "Error", "text": ""})()
    return CurlHTTPError(f"HTTP Error {status}: ", 0, fake_resp)


# ---------------------------------------------------------------------------
# Pytest fixtures for accounts router tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_sb():
    """Bare mock SupabaseClient — configure per-test via accounts_in_db or directly."""
    from src.storage.supabase import QueryResult

    # Auth middleware makes 4 calls before any endpoint logic:
    #   1. avito_api_keys lookup
    #   2. tenants lookup
    #   3. toolkits lookup
    #   4. update api_key last_used_at (empty result)
    auth_responses = [
        QueryResult(data=[{
            "id": TEST_API_KEY_ID, "tenant_id": TEST_TENANT_ID,
            "key_hash": TEST_API_KEY_HASH, "name": "Dev", "is_active": True,
        }]),
        QueryResult(data=[{
            "id": TEST_TENANT_ID, "supervisor_id": TEST_SUPERVISOR_ID,
            "toolkit_id": TEST_TOOLKIT_ID, "name": "TestTenant", "email": "t@t.com",
            "is_active": True, "subscription_until": "2027-01-01T00:00:00+00:00",
            "settings": {},
        }]),
        QueryResult(data=[{
            "id": TEST_TOOLKIT_ID, "supervisor_id": TEST_SUPERVISOR_ID, "name": "Full",
            "features": ALL_FEATURES, "limits": {}, "price_monthly": 0, "is_active": True,
        }]),
        QueryResult(data=[]),  # last_used_at update
    ]

    # endpoint_response will be set by accounts_in_db fixture
    state = {"endpoint_data": []}
    call_counter = {"n": 0}

    all_responses = auth_responses  # mutable list — accounts_in_db appends

    def _make_chain():
        chain = MagicMock()
        for m in ("select", "eq", "neq", "order", "limit", "insert", "update", "delete", "is_"):
            setattr(chain, m, MagicMock(return_value=chain))

        def execute():
            idx = min(call_counter["n"], len(all_responses) - 1)
            call_counter["n"] += 1
            return all_responses[idx]

        chain.execute = MagicMock(side_effect=execute)
        return chain

    sb = MagicMock()
    sb.table = MagicMock(side_effect=lambda name: _make_chain())
    sb._state = state
    sb._auth_responses = auth_responses
    sb._all_responses = all_responses
    sb._call_counter = call_counter
    return sb


@pytest.fixture()
def accounts_in_db(mock_sb):
    """Return a callable that seeds endpoint response rows into mock_sb."""
    from src.storage.supabase import QueryResult

    def _seed(rows: list):
        mock_sb._all_responses.append(QueryResult(data=rows))

    return _seed


@pytest.fixture()
def client(mock_sb):
    """FastAPI TestClient with Supabase fully mocked via mock_sb fixture."""
    from fastapi.testclient import TestClient
    from src.main import app

    patches = [
        patch("src.middleware.auth.get_supabase", return_value=mock_sb),
        patch("src.routers.accounts.get_supabase", return_value=mock_sb),
    ]
    for p in patches:
        p.__enter__()
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        for p in reversed(patches):
            p.__exit__(None, None, None)

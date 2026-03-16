"""Tests for farm router: devices, bindings, token upload, heartbeat."""
from tests.conftest import (
    make_test_jwt, make_authed_sb, run_request,
    TEST_TENANT_ID,
)


def test_create_device():
    """POST /farm/devices → 201, device created."""
    mock_sb = make_authed_sb(
        [{"id": "dev-001", "name": "OnePlus 8T #1", "model": "OnePlus 8T",
          "serial": "SN001", "max_profiles": 100}],  # insert response
    )

    resp = run_request(mock_sb, method="POST", path="/api/v1/farm/devices",
                       json_body={
                           "name": "OnePlus 8T #1",
                           "model": "OnePlus 8T",
                           "serial": "SN001",
                           "max_profiles": 100,
                       })
    assert resp.status_code == 201
    assert resp.json()["status"] == "ok"
    assert resp.json()["device"]["name"] == "OnePlus 8T #1"


def test_list_devices():
    """GET /farm/devices → device list with profile counts."""
    # Auth (4) + devices select (5th) + bindings count for each device (6th)
    mock_sb = make_authed_sb(
        [{"id": "dev-001", "name": "OnePlus 8T", "model": "OnePlus 8T",
          "max_profiles": 100, "status": "online"}],  # devices
        [{"id": "bind-1"}, {"id": "bind-2"}],  # bindings for dev-001
    )

    resp = run_request(mock_sb, path="/api/v1/farm/devices")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["devices"]) == 1
    assert data["devices"][0]["name"] == "OnePlus 8T"
    assert data["devices"][0]["profile_count"] == 2


def test_create_binding():
    """POST /farm/bindings → 201, binding created."""
    mock_sb = make_authed_sb(
        [{"id": "bind-001", "tenant_id": TEST_TENANT_ID,
          "farm_device_id": "dev-001", "android_profile_id": 10}],  # insert
    )

    resp = run_request(mock_sb, method="POST", path="/api/v1/farm/bindings",
                       json_body={
                           "tenant_id": TEST_TENANT_ID,
                           "farm_device_id": "dev-001",
                           "android_profile_id": 10,
                           "avito_user_id": 12345678,
                       })
    assert resp.status_code == 201
    assert resp.json()["status"] == "ok"


def test_list_bindings():
    """GET /farm/bindings → binding list."""
    mock_sb = make_authed_sb(
        [
            {"id": "b1", "tenant_id": TEST_TENANT_ID, "farm_device_id": "dev-001",
             "android_profile_id": 10, "status": "active"},
            {"id": "b2", "tenant_id": TEST_TENANT_ID, "farm_device_id": "dev-001",
             "android_profile_id": 11, "status": "active"},
        ],
    )

    resp = run_request(mock_sb, path="/api/v1/farm/bindings")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["bindings"]) == 2


def test_delete_binding():
    """DELETE /farm/bindings/{id} → 200."""
    mock_sb = make_authed_sb([])

    resp = run_request(mock_sb, method="DELETE", path="/api/v1/farm/bindings/bind-001")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_heartbeat():
    """POST /farm/heartbeat → 200 (updates device status)."""
    mock_sb = make_authed_sb([])

    resp = run_request(mock_sb, method="POST", path="/api/v1/farm/heartbeat",
                       json_body={"device_id": "OnePlus-001"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_upload_farm_token():
    """POST /farm/tokens → token saved for bound tenant."""
    jwt = make_test_jwt(user_id=55555555)

    # Auth (4) + binding lookup (5th) + deactivate old sessions (6th) +
    # insert new session (7th) + update binding (8th) + audit (9th)
    mock_sb = make_authed_sb(
        [{"id": "bind-001", "tenant_id": TEST_TENANT_ID,
          "farm_device_id": "dev-001", "android_profile_id": 10}],  # binding lookup
        [],  # deactivate old sessions
        [],  # insert new session
        [],  # update binding
        [],  # audit log
    )

    resp = run_request(mock_sb, method="POST", path="/api/v1/farm/tokens",
                       json_body={
                           "device_id": "dev-001",
                           "android_profile_id": 10,
                           "session_token": jwt,
                           "refresh_token": "rf_farm_123",
                           "fingerprint": "A2.farm_fp",
                       })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["user_id"] == 55555555

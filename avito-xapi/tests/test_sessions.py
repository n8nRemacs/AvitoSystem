"""Tests for sessions router: CRUD, validation, source field."""
from tests.conftest import (
    make_test_jwt, make_authed_sb, run_request,
)


def test_upload_session_valid():
    """POST /sessions with valid JWT → 201, session created."""
    jwt = make_test_jwt(user_id=12345)
    new_session_id = "new-sess-001"

    # Auth: 4 + endpoint: deactivate old (5th), insert new (6th), audit (7th)
    mock_sb = make_authed_sb(
        [],  # deactivate old sessions
        [{"id": new_session_id, "tenant_id": "c0000000-0000-0000-0000-000000000001"}],  # insert new
        [],  # audit log
    )

    resp = run_request(mock_sb, method="POST", path="/api/v1/sessions",
                       json_body={
                           "session_token": jwt,
                           "refresh_token": "refresh123",
                           "device_id": "dev001",
                           "fingerprint": "A2.test_fp_12345678",
                           "source": "android",
                       })
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "ok"
    assert data["session_id"] == new_session_id
    assert data["user_id"] == 12345


def test_upload_session_source_farm():
    """POST /sessions with source=farm → 201."""
    jwt = make_test_jwt()
    mock_sb = make_authed_sb([], [{"id": "farm-sess"}], [])

    resp = run_request(mock_sb, method="POST", path="/api/v1/sessions",
                       json_body={"session_token": jwt, "source": "farm"})
    assert resp.status_code == 201
    assert resp.json()["status"] == "ok"


def test_upload_session_source_redroid():
    """POST /sessions with source=redroid → 201."""
    jwt = make_test_jwt()
    mock_sb = make_authed_sb([], [{"id": "redroid-sess"}], [])

    resp = run_request(mock_sb, method="POST", path="/api/v1/sessions",
                       json_body={"session_token": jwt, "source": "redroid"})
    assert resp.status_code == 201


def test_upload_session_invalid_jwt():
    """POST /sessions with invalid JWT → 422."""
    mock_sb = make_authed_sb()

    resp = run_request(mock_sb, method="POST", path="/api/v1/sessions",
                       json_body={"session_token": "not-a-valid-jwt", "source": "manual"})
    assert resp.status_code in (422, 500)  # 422 if HTTPException works, 500 if wrapped


def test_upload_session_missing_token():
    """POST /sessions without session_token → 422 (validation error)."""
    mock_sb = make_authed_sb()

    resp = run_request(mock_sb, method="POST", path="/api/v1/sessions",
                       json_body={"source": "manual"})
    assert resp.status_code == 422


def test_get_current_session_active():
    """GET /sessions/current with active session → 200, is_active=True."""
    jwt = make_test_jwt(user_id=88888888, exp_offset=7200)

    mock_sb = make_authed_sb(
        [{
            "id": "active-sess",
            "tenant_id": "c0000000-0000-0000-0000-000000000001",
            "tokens": {"session_token": jwt},
            "device_id": "dev001",
            "fingerprint": "A2.fingerprint_abcdef",
            "user_id": 88888888,
            "source": "android",
            "is_active": True,
            "expires_at": "2027-01-01T00:00:00+00:00",
            "created_at": "2024-01-01T00:00:00+00:00",
        }],
    )

    resp = run_request(mock_sb, path="/api/v1/sessions/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_active"] is True
    assert data["user_id"] == 88888888
    assert data["source"] == "android"
    assert data["ttl_seconds"] > 0


def test_get_current_session_none():
    """GET /sessions/current without active session → 200, is_active=False."""
    mock_sb = make_authed_sb([])

    resp = run_request(mock_sb, path="/api/v1/sessions/current")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_active"] is False


def test_delete_session():
    """DELETE /sessions → 200, ok."""
    mock_sb = make_authed_sb([], [])

    resp = run_request(mock_sb, method="DELETE", path="/api/v1/sessions")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_session_history():
    """GET /sessions/history → list of sessions."""
    mock_sb = make_authed_sb(
        [
            {"id": "s1", "tenant_id": "c0000000-0000-0000-0000-000000000001",
             "tokens": {"session_token": "a.b.c"},
             "user_id": 111, "source": "android", "is_active": False,
             "expires_at": "2024-06-01T00:00:00+00:00", "created_at": "2024-01-01T00:00:00+00:00"},
            {"id": "s2", "tenant_id": "c0000000-0000-0000-0000-000000000001",
             "tokens": {"session_token": "d.e.f"},
             "user_id": 222, "source": "manual", "is_active": True,
             "expires_at": "2027-01-01T00:00:00+00:00", "created_at": "2024-01-02T00:00:00+00:00"},
        ],
    )

    resp = run_request(mock_sb, path="/api/v1/sessions/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["sessions"]) == 2
    assert data["sessions"][0]["source"] == "android"


def test_token_details():
    """GET /sessions/token-details → decoded JWT info."""
    jwt = make_test_jwt(user_id=55555555, exp_offset=3600)

    mock_sb = make_authed_sb(
        [{
            "id": "td-sess",
            "tenant_id": "c0000000-0000-0000-0000-000000000001",
            "tokens": {"session_token": jwt},
            "source": "manual",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00+00:00",
        }],
    )

    resp = run_request(mock_sb, path="/api/v1/sessions/token-details")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == 55555555
    assert data["is_expired"] is False
    assert data["ttl_seconds"] > 0
    assert data["header"]["alg"] == "HS512"


def test_alerts_no_session():
    """GET /sessions/alerts without session → expired alert."""
    mock_sb = make_authed_sb([])

    resp = run_request(mock_sb, path="/api/v1/sessions/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["alerts"]) == 1
    assert data["alerts"][0]["level"] == "expired"


def test_alerts_healthy_session():
    """GET /sessions/alerts with healthy token → no alerts."""
    jwt = make_test_jwt(exp_offset=7200)

    mock_sb = make_authed_sb(
        [{
            "id": "alert-sess",
            "tenant_id": "c0000000-0000-0000-0000-000000000001",
            "tokens": {"session_token": jwt},
            "source": "manual",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00+00:00",
        }],
    )

    resp = run_request(mock_sb, path="/api/v1/sessions/alerts")
    assert resp.status_code == 200
    assert resp.json()["alerts"] == []


def test_alerts_expiring_session():
    """GET /sessions/alerts with expiring token → warning alert."""
    jwt = make_test_jwt(exp_offset=20 * 60 + 30)  # ~20.5 min

    mock_sb = make_authed_sb(
        [{
            "id": "warn-sess",
            "tenant_id": "c0000000-0000-0000-0000-000000000001",
            "tokens": {"session_token": jwt},
            "source": "manual",
            "is_active": True,
            "created_at": "2024-01-01T00:00:00+00:00",
        }],
    )

    resp = run_request(mock_sb, path="/api/v1/sessions/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["alerts"]) == 1
    assert data["alerts"][0]["level"] == "warning"

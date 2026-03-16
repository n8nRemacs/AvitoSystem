"""Tests for session_reader: SessionData.from_row(), load functions."""
from unittest.mock import patch, MagicMock
from src.workers.session_reader import SessionData, load_active_session, load_session_history
from src.storage.supabase import QueryResult
from tests.conftest import make_test_jwt, TEST_TENANT_ID


def test_from_row_full():
    """Full Supabase row → SessionData with all fields."""
    jwt = make_test_jwt(user_id=12345678)
    row = {
        "id": "sess-001",
        "tenant_id": TEST_TENANT_ID,
        "tokens": {
            "session_token": jwt,
            "refresh_token": "refresh_abc",
            "device_id": "dev123",
            "fingerprint": "A2.abcdef",
            "remote_device_id": "remote.abc",
            "user_hash": "hash123",
            "cookies": {"u": "test"},
        },
        "device_id": "dev123",
        "fingerprint": "A2.abcdef",
        "user_id": 12345678,
        "source": "android",
        "is_active": True,
        "expires_at": "2027-01-01T00:00:00+00:00",
        "created_at": "2024-01-01T00:00:00+00:00",
    }
    sd = SessionData.from_row(row)
    assert sd.id == "sess-001"
    assert sd.tenant_id == TEST_TENANT_ID
    assert sd.session_token == jwt
    assert sd.refresh_token == "refresh_abc"
    assert sd.device_id == "dev123"
    assert sd.fingerprint == "A2.abcdef"
    assert sd.remote_device_id == "remote.abc"
    assert sd.user_hash == "hash123"
    assert sd.user_id == 12345678
    assert sd.cookies == {"u": "test"}
    assert sd.source == "android"
    assert sd.is_active is True


def test_from_row_minimal():
    """Minimal row (no tokens subfields) → SessionData with defaults."""
    row = {
        "id": "sess-002",
        "tenant_id": TEST_TENANT_ID,
        "tokens": {"session_token": "x.y.z"},
        "source": "manual",
        "created_at": "2024-01-01T00:00:00+00:00",
    }
    sd = SessionData.from_row(row)
    assert sd.id == "sess-002"
    assert sd.session_token == "x.y.z"
    assert sd.refresh_token is None
    assert sd.device_id is None
    assert sd.cookies is None
    assert sd.source == "manual"


def test_from_row_fallback_device_id():
    """device_id falls back to tokens.device_id if not in row."""
    row = {
        "id": "sess-003",
        "tenant_id": TEST_TENANT_ID,
        "tokens": {"session_token": "a.b.c", "device_id": "from_tokens"},
        "source": "farm",
        "created_at": "2024-01-01T00:00:00+00:00",
    }
    sd = SessionData.from_row(row)
    assert sd.device_id == "from_tokens"


def test_from_row_empty_tokens():
    """Row with empty tokens dict → empty session_token."""
    row = {
        "id": "sess-004",
        "tenant_id": TEST_TENANT_ID,
        "tokens": {},
        "source": "manual",
        "created_at": "2024-01-01T00:00:00+00:00",
    }
    sd = SessionData.from_row(row)
    assert sd.session_token == ""
    assert sd.refresh_token is None


def test_load_active_session():
    """load_active_session returns SessionData when session exists."""
    jwt = make_test_jwt()
    mock_sb = MagicMock()
    chain = MagicMock()
    for m in ("select", "eq", "order", "limit"):
        setattr(chain, m, MagicMock(return_value=chain))
    chain.execute.return_value = QueryResult(data=[{
        "id": "sess-active",
        "tenant_id": TEST_TENANT_ID,
        "tokens": {"session_token": jwt},
        "source": "android",
        "is_active": True,
        "created_at": "2024-01-01T00:00:00+00:00",
    }])
    mock_sb.table.return_value = chain

    with patch("src.workers.session_reader.get_supabase", return_value=mock_sb):
        result = load_active_session(TEST_TENANT_ID)
    assert result is not None
    assert result.id == "sess-active"
    assert result.session_token == jwt


def test_load_active_session_none():
    """load_active_session returns None when no active session."""
    mock_sb = MagicMock()
    chain = MagicMock()
    for m in ("select", "eq", "order", "limit"):
        setattr(chain, m, MagicMock(return_value=chain))
    chain.execute.return_value = QueryResult(data=[])
    mock_sb.table.return_value = chain

    with patch("src.workers.session_reader.get_supabase", return_value=mock_sb):
        result = load_active_session(TEST_TENANT_ID)
    assert result is None


def test_load_session_history():
    """load_session_history returns list of SessionData."""
    mock_sb = MagicMock()
    chain = MagicMock()
    for m in ("select", "eq", "order", "limit"):
        setattr(chain, m, MagicMock(return_value=chain))
    chain.execute.return_value = QueryResult(data=[
        {"id": "s1", "tenant_id": TEST_TENANT_ID, "tokens": {"session_token": "a.b.c"},
         "source": "android", "is_active": False, "created_at": "2024-01-01T00:00:00+00:00"},
        {"id": "s2", "tenant_id": TEST_TENANT_ID, "tokens": {"session_token": "d.e.f"},
         "source": "manual", "is_active": True, "created_at": "2024-01-02T00:00:00+00:00"},
    ])
    mock_sb.table.return_value = chain

    with patch("src.workers.session_reader.get_supabase", return_value=mock_sb):
        result = load_session_history(TEST_TENANT_ID)
    assert len(result) == 2
    assert result[0].id == "s1"
    assert result[1].source == "manual"

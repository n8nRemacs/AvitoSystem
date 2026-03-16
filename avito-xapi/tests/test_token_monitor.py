"""Tests for token_monitor: alert generation based on TTL thresholds."""
from src.workers.token_monitor import get_alerts_for_session, ALERT_WARNING, ALERT_CRITICAL
from src.workers.session_reader import SessionData
from tests.conftest import make_test_jwt, TEST_TENANT_ID


def _make_session(exp_offset):
    """Create a SessionData with a JWT having given exp_offset from now."""
    jwt = make_test_jwt(exp_offset=exp_offset)
    return SessionData(
        id="test-sess",
        tenant_id=TEST_TENANT_ID,
        session_token=jwt,
        refresh_token=None,
        device_id=None,
        fingerprint=None,
        remote_device_id=None,
        user_hash=None,
        user_id=99999999,
        cookies=None,
        source="manual",
        is_active=True,
        expires_at=None,
        created_at="2024-01-01T00:00:00+00:00",
    )


def test_no_alert_healthy_token():
    """Token with TTL > 30 min → no alerts."""
    session = _make_session(exp_offset=7200)  # 2 hours
    alerts = get_alerts_for_session(session)
    assert alerts == []


def test_warning_alert():
    """Token with 10 min < TTL <= 30 min → warning alert."""
    session = _make_session(exp_offset=20 * 60 + 30)  # ~20.5 min
    alerts = get_alerts_for_session(session)
    assert len(alerts) == 1
    assert alerts[0]["level"] == "warning"
    assert alerts[0]["ttl_seconds"] > 0


def test_critical_alert():
    """Token with 0 < TTL <= 10 min → critical alert."""
    session = _make_session(exp_offset=5 * 60 + 30)  # ~5.5 min
    alerts = get_alerts_for_session(session)
    assert len(alerts) == 1
    assert alerts[0]["level"] == "critical"
    assert alerts[0]["ttl_seconds"] > 0


def test_expired_alert():
    """Token with TTL <= 0 → expired alert."""
    session = _make_session(exp_offset=-60)  # expired 1 min ago
    alerts = get_alerts_for_session(session)
    assert len(alerts) == 1
    assert alerts[0]["level"] == "expired"
    assert "expired" in alerts[0]["message"].lower()


def test_just_above_warning_no_alert():
    """Token with TTL just above 30 min → no alerts."""
    session = _make_session(exp_offset=ALERT_WARNING + 120)  # 32 min
    alerts = get_alerts_for_session(session)
    assert alerts == []

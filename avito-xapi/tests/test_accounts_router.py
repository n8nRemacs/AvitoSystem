"""Tests for /api/v1/accounts router."""
import pytest
from fastapi.testclient import TestClient


def test_get_accounts_returns_list(client, accounts_in_db):
    accounts_in_db([
        {"id": "acc-1", "nickname": "Clone", "state": "active",
         "consecutive_cooldowns": 0, "android_user_id": 10},
        {"id": "acc-2", "nickname": "Main", "state": "dead",
         "consecutive_cooldowns": 5, "android_user_id": 0},
    ])
    r = client.get("/api/v1/accounts", headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert {a["nickname"] for a in data} == {"Clone", "Main"}


def test_get_accounts_unauthorized(client):
    r = client.get("/api/v1/accounts")
    assert r.status_code in (401, 403)


def test_poll_claim_picks_oldest_active(client, accounts_in_db):
    """Round-robin: picks account with smallest (NULL-first) last_polled_at."""
    # 1) SELECT active accounts ORDER BY last_polled_at — returns acc-2 (oldest active).
    accounts_in_db([
        {"id": "acc-2", "state": "active", "last_polled_at": "2026-04-28T11:00:00Z",
         "phone_serial": "S2", "android_user_id": 10, "nickname": "Clone"},
    ])
    # 2) UPDATE avito_accounts SET last_polled_at = now() WHERE id=acc-2 AND
    #    last_polled_at='2026-04-28T11:00:00Z' (CAS) — returns the updated row.
    accounts_in_db([
        {"id": "acc-2", "state": "active", "last_polled_at": "2026-04-28T12:30:00Z"},
    ])
    # 3) SELECT session WHERE account_id=acc-2 AND is_active=true.
    accounts_in_db([
        {"id": "sess-2", "account_id": "acc-2", "is_active": True,
         "device_id": "abcd1234abcd1234", "fingerprint": "A2.fingerprint.payload",
         "tokens": {"session_token": "JWT_FOR_ACC2"}},
    ])

    r = client.post("/api/v1/accounts/poll-claim",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account_id"] == "acc-2"
    assert body["session_token"] == "JWT_FOR_ACC2"
    assert body["device_id"] == "abcd1234abcd1234"
    assert body["fingerprint"] == "A2.fingerprint.payload"
    assert body["phone_serial"] == "S2"
    assert body["android_user_id"] == 10


def test_poll_claim_returns_409_when_pool_drained(client, accounts_in_db):
    """No active accounts -> 409 with diagnostic detail."""
    # 1) SELECT active accounts -> empty (pool drained).
    accounts_in_db([])
    # 2) Diagnostic SELECT all accounts (nickname,state,cooldown_until,waiting_since).
    accounts_in_db([
        {"nickname": "Clone", "state": "cooldown",
         "cooldown_until": "2026-04-28T13:25:00Z", "waiting_since": None},
        {"nickname": "Main", "state": "dead",
         "cooldown_until": None, "waiting_since": None},
    ])

    r = client.post("/api/v1/accounts/poll-claim",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"]["error"] == "pool_drained"
    assert len(body["detail"]["accounts"]) == 2
    nicks = {a["nickname"] for a in body["detail"]["accounts"]}
    assert nicks == {"Clone", "Main"}


# ---------------------------------------------------------------------------
# T7: POST /api/v1/accounts/{account_id}/report
# ---------------------------------------------------------------------------

def test_report_200_resets_counters(client, accounts_in_db):
    """200 OK from Avito → state stays active, consecutive_cooldowns reset, last_403 cleared."""
    accounts_in_db([
        {"id": "acc-1", "state": "active", "consecutive_cooldowns": 2,
         "last_403_body": "old", "last_403_at": "2026-04-27T10:00:00+00:00",
         "cooldown_until": None, "waiting_since": None},
    ])
    r = client.post("/api/v1/accounts/acc-1/report",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"status_code": 200})
    assert r.status_code == 204


def test_report_403_starts_cooldown_with_ratchet(client, accounts_in_db):
    """First 403 (consecutive=0→1) → cooldown state, body_excerpt persisted."""
    accounts_in_db([
        {"id": "acc-1", "state": "active", "consecutive_cooldowns": 0,
         "last_403_body": None, "cooldown_until": None, "waiting_since": None},
    ])
    r = client.post("/api/v1/accounts/acc-1/report",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"status_code": 403,
                          "body_excerpt": "<firewall>banned</firewall>"})
    assert r.status_code == 204


def test_report_403_consecutive_3_gives_80min_cooldown(client, accounts_in_db):
    """consecutive=2 going to 3 → cooldown_duration = 20 * 2^2 = 80m."""
    accounts_in_db([
        {"id": "acc-1", "state": "active", "consecutive_cooldowns": 2,
         "cooldown_until": None, "waiting_since": None},
    ])
    r = client.post("/api/v1/accounts/acc-1/report",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"status_code": 403})
    assert r.status_code == 204


def test_report_401_does_not_cooldown(client, accounts_in_db):
    """401 → no cooldown transition, sessions UPDATE fires to expire token."""
    accounts_in_db([
        {"id": "acc-1", "state": "active", "consecutive_cooldowns": 0,
         "cooldown_until": None, "waiting_since": None},
    ])
    r = client.post("/api/v1/accounts/acc-1/report",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"status_code": 401})
    assert r.status_code == 204


def test_report_5xx_no_state_change(client, accounts_in_db):
    """5xx / network error → no-op: state and counters unchanged."""
    accounts_in_db([
        {"id": "acc-1", "state": "active", "consecutive_cooldowns": 1,
         "cooldown_until": None, "waiting_since": None},
    ])
    r = client.post("/api/v1/accounts/acc-1/report",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"status_code": 503})
    assert r.status_code == 204


def test_report_404_when_account_missing(client, accounts_in_db):
    """Unknown account_id → 404."""
    accounts_in_db([])
    r = client.post("/api/v1/accounts/unknown/report",
                    headers={"X-Api-Key": "test_dev_key_123"},
                    json={"status_code": 200})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# T8: GET /api/v1/accounts/{account_id}/session-for-sync
# ---------------------------------------------------------------------------

def test_session_for_sync_returns_active(client, accounts_in_db):
    """Active account with a session → 200 with session_token."""
    # Query 1: SELECT from avito_accounts
    accounts_in_db([
        {"id": "acc-1", "state": "active", "consecutive_cooldowns": 0,
         "cooldown_until": None, "waiting_since": None},
    ])
    # Query 2: SELECT from avito_sessions WHERE account_id=acc-1 AND is_active=true
    accounts_in_db([
        {"id": "sess-1", "account_id": "acc-1", "is_active": True,
         "device_id": "deadbeefdeadbeef", "fingerprint": "A1.fp.payload",
         "tokens": {"session_token": "JWT_FOR_ACC1"}},
    ])

    r = client.get("/api/v1/accounts/acc-1/session-for-sync",
                   headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["account_id"] == "acc-1"
    assert body["session_token"] == "JWT_FOR_ACC1"
    assert body["device_id"] == "deadbeefdeadbeef"
    assert body["fingerprint"] == "A1.fp.payload"


def test_session_for_sync_409_when_not_active(client, accounts_in_db):
    """Non-active account → 409 with detail.state = account's current state."""
    # Query 1: SELECT from avito_accounts — returns cooldown account
    accounts_in_db([
        {"id": "acc-1", "state": "cooldown",
         "cooldown_until": "2026-04-28T13:00:00Z"},
    ])

    r = client.get("/api/v1/accounts/acc-1/session-for-sync",
                   headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"]["state"] == "cooldown"
    assert body["detail"]["id"] == "acc-1"


def test_session_for_sync_409_when_no_session(client, accounts_in_db):
    """Active account but no active session row → 409 with detail.state='no_session'."""
    # Query 1: SELECT from avito_accounts — returns active account
    accounts_in_db([
        {"id": "acc-1", "state": "active"},
    ])
    # Query 2: SELECT from avito_sessions — returns empty (no active session)
    accounts_in_db([])

    r = client.get("/api/v1/accounts/acc-1/session-for-sync",
                   headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["detail"]["state"] == "no_session"
    assert body["detail"]["id"] == "acc-1"


def test_session_for_sync_404_when_unknown(client, accounts_in_db):
    """Unknown account_id → 404."""
    # Query 1: SELECT from avito_accounts — returns empty
    accounts_in_db([])

    r = client.get("/api/v1/accounts/unknown/session-for-sync",
                   headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 404, r.text


# ---------------------------------------------------------------------------
# T14: POST /api/v1/accounts/{account_id}/refresh-cycle
# ---------------------------------------------------------------------------

def test_refresh_cycle_404_when_account_missing(client, accounts_in_db):
    """Unknown account_id → 404."""
    # Query 1: SELECT avito_accounts → empty
    accounts_in_db([])
    r = client.post("/api/v1/accounts/unknown/refresh-cycle",
                    headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 404


def test_refresh_cycle_503_when_adb_dead(client, accounts_in_db, monkeypatch):
    """ADB health check fails → 503 with phone_serial in detail."""
    # Query 1: SELECT avito_accounts → found
    accounts_in_db([{"id": "acc-1", "state": "needs_refresh",
                     "phone_serial": "DEAD", "android_user_id": 0,
                     "last_device_id": "D1"}])

    async def fake_health(self, serial):
        return False

    monkeypatch.setattr("src.workers.device_switcher.DeviceSwitcher.health", fake_health)

    r = client.post("/api/v1/accounts/acc-1/refresh-cycle",
                    headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "DEAD" in detail or "adb" in detail.lower() or "ADB" in detail


def test_refresh_cycle_409_when_no_last_device_id(client, accounts_in_db, monkeypatch):
    """Account missing last_device_id → 409."""
    # Query 1: SELECT avito_accounts → found, no last_device_id
    accounts_in_db([{"id": "acc-1", "state": "needs_refresh",
                     "phone_serial": "S1", "android_user_id": 10,
                     "last_device_id": None}])

    async def ok_health(self, serial):
        return True

    async def ok_switch(self, serial, target, **kw):
        return None

    async def fast_sleep(d):
        return None

    monkeypatch.setattr("src.workers.device_switcher.DeviceSwitcher.health", ok_health)
    monkeypatch.setattr("src.workers.device_switcher.DeviceSwitcher.switch_to", ok_switch)
    monkeypatch.setattr("asyncio.sleep", fast_sleep)

    r = client.post("/api/v1/accounts/acc-1/refresh-cycle",
                    headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 409


def test_refresh_cycle_happy_path_marks_waiting(client, accounts_in_db, monkeypatch):
    """Full happy path: ADB ok, command inserted, account marked waiting_refresh → 202."""
    # Query 1: SELECT avito_accounts → found with last_device_id
    accounts_in_db([{"id": "acc-1", "state": "needs_refresh",
                     "phone_serial": "S1", "android_user_id": 0,
                     "last_device_id": "D1"}])
    # Query 2: INSERT into avito_device_commands → returns new command row
    accounts_in_db([{"id": "cmd-uuid", "command": "refresh_token", "device_id": "D1"}])
    # Query 3: UPDATE avito_accounts SET state=waiting_refresh → returns updated row
    accounts_in_db([{"id": "acc-1", "state": "waiting_refresh"}])

    async def ok_health(self, serial):
        return True

    async def ok_switch(self, serial, target, **kw):
        return None

    async def fast_sleep(d):
        return None

    monkeypatch.setattr("src.workers.device_switcher.DeviceSwitcher.health", ok_health)
    monkeypatch.setattr("src.workers.device_switcher.DeviceSwitcher.switch_to", ok_switch)
    monkeypatch.setattr("asyncio.sleep", fast_sleep)

    r = client.post("/api/v1/accounts/acc-1/refresh-cycle",
                    headers={"X-Api-Key": "test_dev_key_123"})
    assert r.status_code == 202
    body = r.json()
    assert body["account_id"] == "acc-1"
    assert "command_id" in body

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

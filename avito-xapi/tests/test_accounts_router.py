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

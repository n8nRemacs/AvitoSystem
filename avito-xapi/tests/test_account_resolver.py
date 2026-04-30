"""Tests for resolve_or_create_account helper."""
from unittest.mock import MagicMock
import pytest

from src.services.account_resolver import resolve_or_create_account


@pytest.fixture
def mock_sb():
    """Local supabase mock — chained method calls return MagicMock by default."""
    return MagicMock()


def test_returns_existing_account(mock_sb):
    mock_sb.table("avito_accounts").select("*") \
        .eq("avito_user_id", 12345).eq("last_device_id", "D1").limit(1) \
        .execute.return_value.data = [
        {"id": "acc-1", "avito_user_id": 12345, "state": "active", "last_device_id": "D1"},
    ]
    acc = resolve_or_create_account(mock_sb, avito_user_id=12345, device_id="D1")
    assert acc["id"] == "acc-1"


def test_creates_new_account_when_unknown(mock_sb):
    mock_sb.table("avito_accounts").select("*") \
        .eq("avito_user_id", 99999).eq("last_device_id", "D9").limit(1) \
        .execute.return_value.data = []
    mock_sb.table("avito_accounts").insert.return_value.execute.return_value.data = [
        {"id": "new-uuid", "avito_user_id": 99999, "nickname": "auto-99999-D9", "state": "active"},
    ]
    acc = resolve_or_create_account(mock_sb, avito_user_id=99999, device_id="D9")
    assert acc["id"] == "new-uuid"
    assert acc["nickname"] == "auto-99999-D9"


def test_two_devices_same_user_create_two_rows(mock_sb):
    """resolve(u=12345, device='D1') and resolve(u=12345, device='D2') yield
    distinct accounts (different device_id key)."""
    # First call: SELECT returns empty → INSERT
    select_chain = mock_sb.table("avito_accounts").select("*") \
        .eq("avito_user_id", 12345).eq("last_device_id", "D1").limit(1)
    select_chain.execute.return_value.data = []
    mock_sb.table("avito_accounts").insert.return_value.execute.return_value.data = [
        {"id": "acc-D1", "avito_user_id": 12345, "last_device_id": "D1"},
    ]
    acc1 = resolve_or_create_account(mock_sb, avito_user_id=12345, device_id="D1")
    assert acc1["id"] == "acc-D1"

    # Second call with same u, different device — returns separate row
    select_chain2 = mock_sb.table("avito_accounts").select("*") \
        .eq("avito_user_id", 12345).eq("last_device_id", "D2").limit(1)
    select_chain2.execute.return_value.data = []
    mock_sb.table("avito_accounts").insert.return_value.execute.return_value.data = [
        {"id": "acc-D2", "avito_user_id": 12345, "last_device_id": "D2"},
    ]
    acc2 = resolve_or_create_account(mock_sb, avito_user_id=12345, device_id="D2")
    assert acc2["id"] == "acc-D2"
    assert acc1["id"] != acc2["id"]

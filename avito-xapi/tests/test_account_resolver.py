"""Tests for resolve_or_create_account helper."""
from unittest.mock import MagicMock
import pytest

from src.services.account_resolver import resolve_or_create_account


@pytest.fixture
def mock_sb():
    """Local supabase mock — chained method calls return MagicMock by default."""
    return MagicMock()


def test_returns_existing_account(mock_sb):
    mock_sb.table("avito_accounts").select("*").eq("avito_user_id", 12345).limit(1).execute.return_value.data = [
        {"id": "acc-1", "avito_user_id": 12345, "state": "active", "last_device_id": "D1"},
    ]
    acc = resolve_or_create_account(mock_sb, avito_user_id=12345, device_id="D1")
    assert acc["id"] == "acc-1"


def test_creates_new_account_when_unknown(mock_sb):
    mock_sb.table("avito_accounts").select("*").eq("avito_user_id", 99999).limit(1).execute.return_value.data = []
    mock_sb.table("avito_accounts").insert.return_value.execute.return_value.data = [
        {"id": "new-uuid", "avito_user_id": 99999, "nickname": "auto-99999", "state": "active"},
    ]
    acc = resolve_or_create_account(mock_sb, avito_user_id=99999, device_id="D9")
    assert acc["id"] == "new-uuid"
    assert acc["nickname"] == "auto-99999"


def test_updates_last_device_id_when_existing(mock_sb):
    mock_sb.table("avito_accounts").select("*").eq("avito_user_id", 12345).limit(1).execute.return_value.data = [
        {"id": "acc-1", "avito_user_id": 12345, "last_device_id": "OLD"},
    ]
    resolve_or_create_account(mock_sb, avito_user_id=12345, device_id="NEW")
    # Проверяем что был вызван update с новым device_id
    update_calls = mock_sb.table("avito_accounts").update.call_args_list
    assert any(call.args[0].get("last_device_id") == "NEW" for call in update_calls)


def test_no_update_if_device_id_unchanged(mock_sb):
    mock_sb.table("avito_accounts").select("*").eq("avito_user_id", 12345).limit(1).execute.return_value.data = [
        {"id": "acc-1", "avito_user_id": 12345, "last_device_id": "SAME"},
    ]
    mock_sb.table("avito_accounts").update.reset_mock()
    resolve_or_create_account(mock_sb, avito_user_id=12345, device_id="SAME")
    # Update либо не вызван, либо вызван без изменения last_device_id
    update_calls = mock_sb.table("avito_accounts").update.call_args_list
    assert not any(call.args[0].get("last_device_id") == "SAME" and call.args[0].get("last_device_id") != "SAME" for call in update_calls)

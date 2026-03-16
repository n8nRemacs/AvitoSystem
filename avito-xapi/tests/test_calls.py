"""Tests for calls: normalization + endpoint."""
from unittest.mock import AsyncMock, MagicMock
from src.routers.calls import _normalize_call
from tests.conftest import make_authed_sb, run_request


def test_normalize_call():
    """Raw call → CallRecord with all fields."""
    raw = {
        "id": "12345",
        "caller": "+79001234567",
        "receiver": "+79007654321",
        "duration": "2:30",
        "hasRecord": True,
        "isNew": False,
        "isSpamTagged": False,
        "isCallback": False,
        "createTime": "2024-02-01T15:30:00Z",
        "itemId": 3001234567,
        "itemTitle": "iPhone 15 Pro 256GB",
    }
    call = _normalize_call(raw)
    assert call.id == "12345"
    assert call.caller == "+79001234567"
    assert call.duration == "2:30"
    assert call.has_record is True
    assert call.item_id == "3001234567"
    assert call.item_title == "iPhone 15 Pro 256GB"


def test_normalize_call_no_item():
    """Call without item → item fields are None."""
    raw = {
        "id": "99999",
        "caller": "+79001111111",
        "duration": "0:15",
        "hasRecord": False,
        "isNew": True,
    }
    call = _normalize_call(raw)
    assert call.id == "99999"
    assert call.has_record is False
    assert call.is_new is True
    assert call.item_id is None


def test_call_history_endpoint():
    """GET /calls/history → normalized call list."""
    fixture_data = {
        "result": {
            "items": [
                {
                    "id": "c-1",
                    "caller": "+79001111111",
                    "receiver": "+79002222222",
                    "duration": "1:00",
                    "hasRecord": True,
                    "isNew": False,
                    "isSpamTagged": False,
                    "isCallback": False,
                    "createTime": "2024-02-01T10:00:00Z",
                    "itemId": 12345,
                    "itemTitle": "Test Item",
                }
            ],
            "total": 1,
        }
    }

    mock_client = MagicMock()
    mock_client.get_call_history = AsyncMock(return_value=fixture_data)

    mock_sb = make_authed_sb()
    resp = run_request(
        mock_sb, path="/api/v1/calls/history",
        extra_patches={"src.routers.calls._get_client": mock_client},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["calls"][0]["id"] == "c-1"
    assert data["calls"][0]["has_record"] is True

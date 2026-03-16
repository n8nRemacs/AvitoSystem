"""Tests for messenger: normalization + endpoints."""
import json
from unittest.mock import AsyncMock, MagicMock
from src.routers.messenger import _normalize_channel, _normalize_message
from tests.conftest import make_authed_sb, make_test_jwt, run_request


# ── Normalization tests ───────────────────────────────


def test_normalize_channel():
    """Raw Avito channel → Channel model with correct fields."""
    raw = {
        "id": "u2i-ch-1",
        "created": 1707000000000000000,
        "updated": 1707050000000000000,
        "isRead": False,
        "unreadCount": 3,
        "users": [
            {"id": "99999999", "name": "Me"},
            {"id": "88888888", "name": "Ivan Petrov"},
        ],
        "info": {
            "name": "Ivan Petrov",
            "details": {
                "itemId": "3001234567",
                "title": "iPhone 15 Pro",
                "url": "https://avito.ru/items/3001234567",
                "price": 95000,
                "images": ["https://img.avito.ru/1.jpg"],
            },
        },
        "lastMessage": {
            "id": "msg-001",
            "authorId": "88888888",
            "createdAt": 1707050000000000000,
            "body": {"text": {"text": "Hello, is it available?"}},
        },
    }
    ch = _normalize_channel(raw, my_user_id=99999999)
    assert ch.id == "u2i-ch-1"
    assert ch.contact_name == "Ivan Petrov"
    assert ch.contact_id == "88888888"
    assert ch.is_read is False
    assert ch.unread_count == 3
    assert ch.last_message_text == "Hello, is it available?"
    assert ch.info is not None
    assert ch.info.item_id == "3001234567"
    assert ch.info.item_price == "95000"


def test_normalize_channel_no_users():
    """Channel with empty users list → contact from info.name."""
    raw = {
        "id": "ch-empty",
        "users": [],
        "info": {"name": "Contact Name", "details": {}},
        "lastMessage": {"body": {"text": {"text": "msg"}}},
    }
    ch = _normalize_channel(raw)
    assert ch.contact_name == "Contact Name"


def test_normalize_message_text():
    """Text message: body.text.text → text, readAt → is_read."""
    raw = {
        "id": "msg-001",
        "channelId": "ch-1",
        "authorId": "88888888",
        "createdAt": 1707050000000000000,
        "readAt": 1707051000000000000,
        "isFirstMessage": True,
        "body": {"text": {"text": "Hello there!"}},
    }
    msg = _normalize_message(raw)
    assert msg.id == "msg-001"
    assert msg.author_id == "88888888"
    assert msg.text == "Hello there!"
    assert msg.message_type == "text"
    assert msg.is_read is True
    assert msg.is_first is True


def test_normalize_message_image():
    """Image message: body.image → type=image, media_url set."""
    raw = {
        "id": "msg-002",
        "channelId": "ch-1",
        "authorId": "99999999",
        "createdAt": 1707052000000000000,
        "readAt": None,
        "body": {
            "image": {
                "imageId": "img-123",
                "url": "https://img.avito.ru/photo.jpg",
                "width": 1024,
                "height": 768,
            }
        },
    }
    msg = _normalize_message(raw)
    assert msg.message_type == "image"
    assert msg.media_url == "https://img.avito.ru/photo.jpg"
    assert msg.media_info["image_id"] == "img-123"
    assert msg.is_read is False


def test_normalize_message_voice():
    """Voice message: body.voice → type=voice."""
    raw = {
        "id": "msg-003",
        "channelId": "ch-1",
        "authorId": "88888888",
        "createdAt": 1707053000000000000,
        "readAt": None,
        "body": {"voice": {"voiceId": "v-1", "duration": 15}},
    }
    msg = _normalize_message(raw)
    assert msg.message_type == "voice"
    assert msg.media_info["voice_id"] == "v-1"
    assert msg.media_info["duration"] == 15


def test_normalize_message_location():
    """Location message: body.location → type=location."""
    raw = {
        "id": "msg-004",
        "channelId": "ch-1",
        "authorId": "99999999",
        "createdAt": 1707054000000000000,
        "readAt": None,
        "body": {"location": {"lat": 55.75, "lon": 37.62, "address": "Moscow"}},
    }
    msg = _normalize_message(raw)
    assert msg.message_type == "location"
    assert msg.media_info["lat"] == 55.75
    assert msg.media_info["address"] == "Moscow"


# ── Endpoint tests ────────────────────────────────────


def test_channels_endpoint():
    """GET /messenger/channels → normalized channel list."""
    jwt = make_test_jwt()
    fixture_data = {
        "success": {
            "channels": [
                {
                    "id": "ch-1",
                    "users": [{"id": "99999999", "name": "Me"}, {"id": "88888888", "name": "Seller"}],
                    "info": {"name": "Seller", "details": {"itemId": "123", "title": "Item"}},
                    "lastMessage": {"body": {"text": {"text": "Hi"}}},
                    "isRead": True,
                    "unreadCount": 0,
                }
            ],
            "hasMore": False,
        }
    }

    mock_client = MagicMock()
    mock_client.get_channels = AsyncMock(return_value=fixture_data)

    # Auth (4) + load_active_session for my_user_id (5th)
    mock_sb = make_authed_sb(
        [{
            "id": "s1", "tenant_id": "c0000000-0000-0000-0000-000000000001",
            "tokens": {"session_token": jwt}, "user_id": 99999999,
            "source": "android", "is_active": True,
            "created_at": "2024-01-01T00:00:00+00:00",
        }],
    )

    resp = run_request(
        mock_sb, path="/api/v1/messenger/channels",
        extra_patches={"src.routers.messenger._get_client": mock_client},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["channels"]) == 1
    assert data["channels"][0]["contact_name"] == "Seller"


def test_send_message_endpoint():
    """POST /messenger/channels/{id}/messages → 200."""
    mock_client = MagicMock()
    mock_client.send_text = AsyncMock(return_value={"success": {"messageId": "new-msg"}})

    mock_sb = make_authed_sb()
    resp = run_request(
        mock_sb, method="POST",
        path="/api/v1/messenger/channels/ch-1/messages",
        json_body={"text": "Hello!"},
        extra_patches={"src.routers.messenger._get_client": mock_client},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_unread_count_endpoint():
    """GET /messenger/unread-count → count."""
    mock_client = MagicMock()
    mock_client.get_unread_count = AsyncMock(return_value={"success": {"unreadCount": 5}})

    mock_sb = make_authed_sb()
    resp = run_request(
        mock_sb, path="/api/v1/messenger/unread-count",
        extra_patches={"src.routers.messenger._get_client": mock_client},
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 5

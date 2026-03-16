"""Tests for search: normalization + endpoints."""
from unittest.mock import AsyncMock, MagicMock
from src.routers.search import _normalize_item_card
from tests.conftest import make_authed_sb, run_request


def test_normalize_item_card():
    """Raw item → ItemCard with images and location."""
    raw = {
        "id": 3001234567,
        "title": "iPhone 15 Pro 256GB",
        "price": 95000,
        "priceFormatted": "95 000 ₽",
        "address": "Moscow, Tverskaya st.",
        "location": {"name": "Moscow"},
        "images": [
            {"url": "https://img.avito.ru/1.jpg", "width": 640, "height": 480}
        ],
        "url": "https://avito.ru/items/3001234567",
        "createdAt": "2024-02-01T10:00:00Z",
        "sellerId": 88888888,
    }
    card = _normalize_item_card(raw)
    assert card.id == 3001234567
    assert card.title == "iPhone 15 Pro 256GB"
    assert card.price == 95000
    assert card.price_text == "95 000 ₽"
    assert card.city == "Moscow"
    assert len(card.images) == 1
    assert card.images[0].url == "https://img.avito.ru/1.jpg"
    assert card.seller_id == 88888888


def test_normalize_item_string_images():
    """Images as plain strings → ItemImage(url=str)."""
    raw = {
        "id": 100,
        "title": "Test",
        "images": ["https://img.avito.ru/a.jpg", "https://img.avito.ru/b.jpg"],
    }
    card = _normalize_item_card(raw)
    assert len(card.images) == 2
    assert card.images[0].url == "https://img.avito.ru/a.jpg"


def test_normalize_item_no_location():
    """Item without location dict → city is None."""
    raw = {"id": 200, "title": "No Location"}
    card = _normalize_item_card(raw)
    assert card.city is None


def test_normalize_item_fallback_fields():
    """Item with alternative field names: price_text, userId, time."""
    raw = {
        "id": 300,
        "title": "Alt Fields",
        "price_text": "50 000 ₽",
        "userId": 77777,
        "time": "2024-03-01",
        "city": "SPb",
    }
    card = _normalize_item_card(raw)
    assert card.price_text == "50 000 ₽"
    assert card.seller_id == 77777
    assert card.created_at == "2024-03-01"
    assert card.city == "SPb"


def test_search_endpoint():
    """GET /search/items?query=iPhone → normalized items."""
    fixture_data = {
        "items": [
            {
                "id": 3001234567,
                "title": "iPhone 15 Pro",
                "price": 95000,
                "priceFormatted": "95 000 ₽",
                "location": {"name": "Moscow"},
                "images": [{"url": "https://img.avito.ru/1.jpg"}],
                "sellerId": 88888888,
            }
        ],
        "total": 150,
    }

    mock_client = MagicMock()
    mock_client.search_items = AsyncMock(return_value=fixture_data)

    mock_sb = make_authed_sb()
    resp = run_request(
        mock_sb, path="/api/v1/search/items?query=iPhone",
        extra_patches={"src.routers.search._get_client": mock_client},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 150
    assert len(data["items"]) == 1
    assert data["items"][0]["title"] == "iPhone 15 Pro"


def test_item_detail_endpoint():
    """GET /search/items/{id} → full item detail."""
    fixture_data = {
        "id": 3001234567,
        "title": "iPhone 15 Pro 256GB",
        "description": "Excellent condition",
        "price": 95000,
        "priceFormatted": "95 000 ₽",
        "address": "Moscow",
        "location": {"name": "Moscow"},
        "images": [{"url": "https://img.avito.ru/1.jpg"}],
        "category": {"name": "Phones"},
        "seller": {"name": "Ivan"},
        "sellerId": 88888888,
        "params": {"brand": "Apple"},
    }

    mock_client = MagicMock()
    mock_client.get_item_details = AsyncMock(return_value=fixture_data)

    mock_sb = make_authed_sb()
    resp = run_request(
        mock_sb, path="/api/v1/search/items/3001234567",
        extra_patches={"src.routers.search._get_client": mock_client},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "iPhone 15 Pro 256GB"
    assert data["description"] == "Excellent condition"
    assert data["category"] == "Phones"
    assert data["seller_name"] == "Ivan"

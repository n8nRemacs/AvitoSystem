"""Tests for search: normalization + endpoints.

The Avito mobile API returns search results as a feed of mixed widgets and
listings. Real listings are wrapped as ``{type: "item", value: {...}}``.
``_normalize_item_card`` accepts both that shape and bare-item legacy shape
for back-compat with old fixtures.
"""
from unittest.mock import AsyncMock, MagicMock

from src.routers.search import _normalize_item_card, _normalize_item_detail
from tests.conftest import make_authed_sb, run_request


# ── Live shape (verified against /api/11/items on 2026-04-27) ────────────

def test_normalize_item_card_live_shape():
    """Real Avito feed item: {type:item, value:{galleryItems, price, sellerInfo, ...}}."""
    raw = {
        "type": "item",
        "value": {
            "id": 8047874649,
            "title": "iPhone 12 Pro, 128 ГБ",
            "subTitle": "",
            "imageAlt": "iPhone 12 Pro, 128 ГБ, Астрахань",
            "price": {
                "current": "4 970 ₽",
                "priceWithoutDiscount": "5 000 ₽",
                "value_signed": "4 970 ₽",
            },
            "galleryItems": [
                {
                    "type": "image",
                    "value": {
                        "640x480": "https://60.img.avito.st/image/big.jpg",
                        "140x140": "https://60.img.avito.st/image/small.jpg",
                    },
                }
            ],
            "uri": "ru.avito://1/item/show?context=abc&itemId=8047874649",
            "sellerInfo": {"name": "Рамиль", "userKey": "1cf1ab25..."},
            "categoryId": 84,
            "isDeliveryAvailable": True,
        },
    }
    card = _normalize_item_card(raw)
    assert card.id == 8047874649
    assert card.title == "iPhone 12 Pro, 128 ГБ"
    assert card.price == 4970, "price should be parsed from 'current' string"
    assert card.price_text == "4 970 ₽"
    assert card.city == "Астрахань", "city extracted from imageAlt last segment"
    assert len(card.images) == 1
    assert card.images[0].url == "https://60.img.avito.st/image/big.jpg"
    assert card.images[0].width == 640
    assert card.images[0].height == 480
    # No integer userId in mobile API → seller_id stays None
    assert card.seller_id is None
    # url falls back to deep-link uri (web url is only on detail endpoint)
    assert "itemId=8047874649" in (card.url or "")


def test_normalize_item_card_extracts_id_from_uri_when_missing():
    """If 'value.id' is missing, parse itemId from the deep-link uri."""
    raw = {
        "type": "item",
        "value": {
            "title": "Phone",
            "uri": "ru.avito://1/item/show?itemId=12345&x=abc",
            "price": {"value_signed": "1 000 ₽"},
        },
    }
    card = _normalize_item_card(raw)
    assert card.id == 12345


def test_normalize_item_card_skips_widget_via_filter():
    """Widget items have type != 'item' — caller filters them out, not the
    normaliser, but we still verify the normaliser tolerates a missing value."""
    raw = {"type": "feedShortcutsWidget", "value": {"title": "Категории"}}
    # Widget passed through; falls through to bare-dict path with empty fields.
    card = _normalize_item_card(raw)
    assert card.id == 0
    assert card.title == ""


# ── Back-compat: legacy bare-item shape (still accepted) ─────────────────

def test_normalize_item_card_legacy_bare_shape():
    """Old fixtures: bare item with priceFormatted + sellerId."""
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
    """Legacy: images as plain strings → ItemImage(url=str)."""
    raw = {
        "id": 100,
        "title": "Test",
        "images": ["https://img.avito.ru/a.jpg", "https://img.avito.ru/b.jpg"],
    }
    card = _normalize_item_card(raw)
    assert len(card.images) == 2
    assert card.images[0].url == "https://img.avito.ru/a.jpg"


def test_normalize_item_no_location():
    raw = {"id": 200, "title": "No Location"}
    card = _normalize_item_card(raw)
    assert card.city is None


def test_normalize_item_fallback_fields():
    """Legacy alternative names: price_text, userId, time."""
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


# ── Detail normaliser ────────────────────────────────────────────────────

def test_normalize_item_detail_live_shape():
    """Real Avito /api/19/items/{id} response."""
    raw = {
        "id": 8047874649,
        "title": "iPhone 12 Pro, 128 ГБ, SIM + eSIM",
        "description": "Телефон работает, но сам по себе разряжается.",
        "address": "Астрахань, мкр-н Жилгородок",
        "coords": {"lat": 46.33, "lng": 48.02},
        "categoryId": 84,
        "time": 1776925736,
        "userType": "company",
        "price": {"value": "4 970", "value_signed": "4 970 ₽", "metric": "₽"},
        "images": [
            {"1280x960": "https://60.img.avito.st/image/big.jpg",
             "720x540": "https://60.img.avito.st/image/med.jpg"},
        ],
        "seller": {"name": "Рамиль", "profileType": "company",
                   "userHash": "1cf1ab25cac183f71a94cbf95f0501b4"},
        "sellerAddressInfo": {"fullAddress": {"locality": "Астрахань"}},
        "sharing": {"url": "https://www.avito.ru/astrahan/telefony/iphone_8047874649"},
        "parameters": {
            "flat": [
                {"attributeId": 121588, "title": "Состояние", "description": "Удовлетворительное"},
                {"attributeId": 110618, "title": "Производитель", "description": "Apple"},
            ],
        },
    }
    detail = _normalize_item_detail(raw)
    assert detail.id == 8047874649
    assert detail.title == "iPhone 12 Pro, 128 ГБ, SIM + eSIM"
    assert detail.description.startswith("Телефон работает")
    assert detail.price == 4970
    assert detail.price_text == "4 970 ₽"
    assert detail.address == "Астрахань, мкр-н Жилгородок"
    assert detail.city == "Астрахань"
    assert detail.url == "https://www.avito.ru/astrahan/telefony/iphone_8047874649"
    assert detail.category == "84"  # categoryId surfaced as string fallback
    assert detail.seller_name == "Рамиль"
    assert len(detail.images) == 1
    assert detail.images[0].url == "https://60.img.avito.st/image/big.jpg"
    assert detail.params == {"Состояние": "Удовлетворительное", "Производитель": "Apple"}
    assert detail.created_at == "1776925736"


# ── Endpoint integration tests ───────────────────────────────────────────

def test_search_endpoint_legacy_shape():
    """Endpoint with legacy bare-item fixture still works (back-compat)."""
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


def test_search_endpoint_live_shape_filters_widgets():
    """Endpoint with realistic mobile API shape: result.items mixes widgets + listings."""
    fixture_data = {
        "status": "ok",
        "result": {
            "totalCount": 12345,
            "mainCount": 12000,
            "items": [
                # Widget — must be filtered out
                {"type": "feedShortcutsWidget", "value": {"title": "Категории"}},
                # Real listing
                {
                    "type": "item",
                    "value": {
                        "id": 8047874649,
                        "title": "iPhone 12 Pro, 128 ГБ",
                        "imageAlt": "iPhone 12 Pro, 128 ГБ, Астрахань",
                        "price": {"current": "4 970 ₽", "value_signed": "4 970 ₽"},
                        "galleryItems": [
                            {"type": "image",
                             "value": {"640x480": "https://img/big.jpg"}}
                        ],
                        "uri": "ru.avito://1/item/show?itemId=8047874649",
                        "sellerInfo": {"name": "Рамиль"},
                    },
                },
                {
                    "type": "item",
                    "value": {
                        "id": 8047874700,
                        "title": "iPhone 13",
                        "imageAlt": "iPhone 13, Москва",
                        "price": {"value_signed": "13 000 ₽"},
                        "galleryItems": [],
                        "uri": "ru.avito://1/item/show?itemId=8047874700",
                    },
                },
            ],
        },
    }

    mock_client = MagicMock()
    mock_client.search_items = AsyncMock(return_value=fixture_data)

    mock_sb = make_authed_sb()
    resp = run_request(
        mock_sb, path="/api/v1/search/items?query=iphone",
        extra_patches={"src.routers.search._get_client": mock_client},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Total picked up from result.totalCount
    assert data["total"] == 12345
    # Widget filtered, only 2 listings remain
    assert len(data["items"]) == 2
    first = data["items"][0]
    assert first["id"] == 8047874649
    assert first["title"] == "iPhone 12 Pro, 128 ГБ"
    assert first["price"] == 4970
    assert first["price_text"] == "4 970 ₽"
    assert first["city"] == "Астрахань"
    assert first["images"][0]["url"] == "https://img/big.jpg"


def test_item_detail_endpoint_legacy():
    """Detail endpoint with legacy fixture: category as dict, seller as dict."""
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


def test_item_detail_endpoint_live_shape():
    """Detail endpoint with realistic /api/19/items/{id} shape."""
    fixture_data = {
        "id": 8047874649,
        "title": "iPhone 12 Pro, 128 ГБ, SIM + eSIM",
        "description": "Рабочий телефон",
        "address": "Астрахань, мкр-н Жилгородок",
        "categoryId": 84,
        "time": 1776925736,
        "price": {"value": "4 970", "value_signed": "4 970 ₽"},
        "images": [{"1280x960": "https://img/big.jpg"}],
        "seller": {"name": "Рамиль"},
        "sellerAddressInfo": {"fullAddress": {"locality": "Астрахань"}},
        "sharing": {"url": "https://www.avito.ru/astrahan/.../iphone_8047874649"},
        "parameters": {
            "flat": [{"title": "Состояние", "description": "Удовлетворительное"}],
        },
    }

    mock_client = MagicMock()
    mock_client.get_item_details = AsyncMock(return_value=fixture_data)

    mock_sb = make_authed_sb()
    resp = run_request(
        mock_sb, path="/api/v1/search/items/8047874649",
        extra_patches={"src.routers.search._get_client": mock_client},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 8047874649
    assert data["title"] == "iPhone 12 Pro, 128 ГБ, SIM + eSIM"
    assert data["price"] == 4970
    assert data["price_text"] == "4 970 ₽"
    assert data["city"] == "Астрахань"
    assert data["url"] == "https://www.avito.ru/astrahan/.../iphone_8047874649"
    assert data["seller_name"] == "Рамиль"
    assert data["params"] == {"Состояние": "Удовлетворительное"}
    assert data["created_at"] == "1776925736"

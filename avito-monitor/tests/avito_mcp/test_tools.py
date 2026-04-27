"""Unit tests for the four avito_mcp tools.

All tests mock the upstream xapi via ``respx`` (httpx mock transport) so they
run offline in CI.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from avito_mcp.config import McpSettings
from avito_mcp.integrations.xapi_client import XapiClient
from avito_mcp.tools.listings import (
    avito_get_listing_images_impl,
    avito_get_listing_impl,
    extract_item_id,
)
from avito_mcp.tools.search import avito_fetch_search_page_impl
from avito_mcp.tools.service import avito_health_check_impl

XAPI_BASE = "http://xapi.test"


def make_client() -> XapiClient:
    settings = McpSettings(
        avito_xapi_url=XAPI_BASE,
        avito_xapi_api_key="test-key",
    )
    return XapiClient(settings)


# ------------------------------------------------------------------------
# avito_fetch_search_page
# ------------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_fetch_search_page_parses_url_and_normalises_items() -> None:
    fake_response = {
        "items": [
            {
                "id": 1234567890,
                "title": "iPhone 12 Pro Max 256Gb",
                "price": 12500,
                "price_text": "12 500 ₽",
                "city": "Москва",
                "address": "м. Новокузнецкая",
                "images": [
                    {"url": "https://avito.example/img1.jpg", "width": 640, "height": 480},
                    "https://avito.example/img2.jpg",
                ],
                "url": "https://www.avito.ru/iphone_12_pro_max_1234567890",
                "created_at": "2026-04-26T10:00:00Z",
                "seller_id": 999,
            },
            {
                "id": 1234567891,
                "title": "iPhone 12 Pro Max 128Gb (как новый)",
                "price": 13000,
                "city": "Москва",
                "images": [],
                "url": "https://www.avito.ru/iphone_12_pro_max_1234567891",
                "seller_id": 1000,
            },
        ],
        "total": 47,
        "page": 1,
        "has_more": True,
    }

    route = respx.get(f"{XAPI_BASE}/api/v1/search/items").mock(
        return_value=httpx.Response(200, json=fake_response)
    )

    page = await avito_fetch_search_page_impl(
        url=(
            "https://www.avito.ru/moskva/telefony/mobilnye_telefony/"
            "apple-ASgBAgICAUSwwQ2OWg?pmin=11000&pmax=13500"
        ),
        page=1,
        client=make_client(),
    )

    assert route.called
    sent = route.calls.last.request
    # X-Api-Key header
    assert sent.headers["x-api-key"] == "test-key"
    # Query string was assembled from the parsed Avito URL
    assert sent.url.params["query"] == "Apple"
    assert sent.url.params["price_min"] == "11000"
    assert sent.url.params["price_max"] == "13500"
    assert sent.url.params["location_id"] == "637640"  # Moscow
    assert sent.url.params["page"] == "1"

    # Normalised result
    assert len(page.items) == 2
    first = page.items[0]
    assert first.id == 1234567890
    assert first.price == 12500
    assert first.region == "Москва"
    assert first.seller_id == 999
    assert len(first.images) == 2
    assert first.images[0].url == "https://avito.example/img1.jpg"
    assert first.images[0].index == 0
    assert page.total == 47
    assert page.has_more is True
    assert page.applied_query == "Apple"


# ------------------------------------------------------------------------
# avito_get_listing
# ------------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_get_listing_extracts_id_from_url_and_returns_detail() -> None:
    fake_detail = {
        "id": 1234567890,
        "title": "iPhone 12 Pro Max 256Gb",
        "description": "Состояние идеальное, аккумулятор 92%, без сколов.",
        "price": 12500,
        "price_text": "12 500 ₽",
        "city": "Москва",
        "address": "м. Новокузнецкая",
        "images": [
            {"url": "https://avito.example/img1.jpg", "width": 1280, "height": 960},
            {"url": "https://avito.example/img2.jpg"},
        ],
        "url": "https://www.avito.ru/iphone_12_pro_max_1234567890",
        "category": "Мобильные телефоны",
        "seller_id": 999,
        "seller_name": "Иван",
        "params": {"battery": "92%", "memory": "256Gb"},
        "created_at": "2026-04-26T10:00:00Z",
    }
    route = respx.get(f"{XAPI_BASE}/api/v1/search/items/1234567890").mock(
        return_value=httpx.Response(200, json=fake_detail)
    )

    detail = await avito_get_listing_impl(
        item_id_or_url="https://www.avito.ru/moskva/telefony/iphone_12_pro_max_1234567890",
        client=make_client(),
    )

    assert route.called
    assert detail.id == 1234567890
    assert detail.description.startswith("Состояние идеальное")
    assert detail.parameters == {"battery": "92%", "memory": "256Gb"}
    assert detail.seller_name == "Иван"
    assert len(detail.images) == 2
    assert detail.images[0].width == 1280


def test_extract_item_id_variants() -> None:
    assert extract_item_id(1234567890) == 1234567890
    assert extract_item_id("1234567890") == 1234567890
    assert extract_item_id(
        "https://www.avito.ru/moskva/telefony/iphone_12_pro_max_1234567890"
    ) == 1234567890
    assert extract_item_id(
        "https://www.avito.ru/moskva/telefony/iphone_12_pro_max_1234567890/"
    ) == 1234567890
    with pytest.raises(ValueError):
        extract_item_id("not-a-url-and-no-digits")
    with pytest.raises(ValueError):
        extract_item_id(0)


# ------------------------------------------------------------------------
# avito_get_listing_images
# ------------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_get_listing_images_returns_only_image_list() -> None:
    fake_detail = {
        "id": 42,
        "title": "Test",
        "images": [
            {"url": "https://avito.example/a.jpg", "width": 100, "height": 75},
            {"url": "https://avito.example/b.jpg", "width": 200, "height": 150},
            "https://avito.example/c.jpg",
        ],
    }
    respx.get(f"{XAPI_BASE}/api/v1/search/items/42").mock(
        return_value=httpx.Response(200, json=fake_detail)
    )

    images = await avito_get_listing_images_impl(42, client=make_client())
    assert [img.url for img in images] == [
        "https://avito.example/a.jpg",
        "https://avito.example/b.jpg",
        "https://avito.example/c.jpg",
    ]
    assert images[0].width == 100
    assert images[2].index == 2


# ------------------------------------------------------------------------
# avito_health_check
# ------------------------------------------------------------------------

@respx.mock
@pytest.mark.asyncio
async def test_health_check_active_session() -> None:
    respx.get(f"{XAPI_BASE}/health").mock(
        return_value=httpx.Response(200, json={"status": "ok", "version": "0.1.0"})
    )
    respx.get(f"{XAPI_BASE}/api/v1/sessions/current").mock(
        return_value=httpx.Response(200, json={
            "is_active": True,
            "ttl_seconds": 7200,
            "ttl_human": "2h 0m",
            "expires_at": "2026-04-26T15:00:00Z",
            "created_at": "2026-04-25T15:00:00Z",
            "device_id": "abc",
            "fingerprint_preview": "A2.aaaa...",
        })
    )

    health = await avito_health_check_impl(client=make_client())
    assert health.xapi_reachable is True
    assert health.session_active is True
    assert health.avito_reachable is True
    assert health.session_ttl_hours == 2.0
    assert health.session_ttl_human == "2h 0m"
    assert health.last_error is None


@respx.mock
@pytest.mark.asyncio
async def test_health_check_xapi_unreachable() -> None:
    respx.get(f"{XAPI_BASE}/health").mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    health = await avito_health_check_impl(client=make_client())
    assert health.xapi_reachable is False
    assert health.session_active is False
    assert "transport error" in (health.last_error or "")


@respx.mock
@pytest.mark.asyncio
async def test_health_check_no_session() -> None:
    respx.get(f"{XAPI_BASE}/health").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )
    respx.get(f"{XAPI_BASE}/api/v1/sessions/current").mock(
        return_value=httpx.Response(200, json={"is_active": False})
    )

    health = await avito_health_check_impl(client=make_client())
    assert health.xapi_reachable is True
    assert health.session_active is False
    assert health.avito_reachable is False
    assert "no active Avito session" in (health.last_error or "")

"""avito_fetch_search_page tool implementation.

Takes an Avito search URL + page number, extracts query / price / location
from the URL, calls xapi, and normalises the response into ``SearchPage``.
"""
from __future__ import annotations

from typing import Any

from app.services.url_parser import ParsedAvitoUrl, parse_avito_url
from avito_mcp.integrations.xapi_client import XapiClient
from shared.models.avito import ListingImage, ListingShort, SearchPage


def _build_query_string(p: ParsedAvitoUrl) -> str:
    """Pick the most useful query keyword from a parsed URL.

    Priority:
        1. explicit ``?q=`` parameter
        2. brand + model joined
        3. brand alone
        4. last category segment
        5. fallback to "*" (Avito accepts empty-ish queries on category-only)
    """
    if p.query:
        return p.query
    if p.brand and p.model:
        return f"{p.brand} {p.model}"
    if p.brand:
        return p.brand
    if p.category_human:
        return p.category_human.split(" / ")[-1]
    return "*"


def _normalise_listing(raw: dict[str, Any]) -> ListingShort:
    """xapi returns ``ItemCard`` (already normalised); map into ``ListingShort``."""
    images_raw = raw.get("images") or []
    images: list[ListingImage] = []
    for idx, img in enumerate(images_raw):
        if isinstance(img, str):
            images.append(ListingImage(url=img, index=idx))
        elif isinstance(img, dict) and img.get("url"):
            images.append(ListingImage(
                url=img["url"],
                width=img.get("width"),
                height=img.get("height"),
                index=idx,
            ))

    return ListingShort(
        id=int(raw.get("id") or 0),
        title=raw.get("title") or "",
        price=raw.get("price"),
        price_text=raw.get("price_text"),
        region=raw.get("city") or raw.get("address"),
        address=raw.get("address"),
        url=raw.get("url"),
        images=images,
        seller_id=raw.get("seller_id"),
        seller_type=None,  # xapi ItemCard does not expose seller_type yet
        first_seen=raw.get("created_at"),
    )


async def avito_fetch_search_page_impl(
    url: str,
    page: int = 1,
    *,
    client: XapiClient | None = None,
) -> SearchPage:
    """Fetch a single page of an Avito search query described by ``url``.

    The URL is parsed locally (``app.services.url_parser``) to extract query
    keyword, region, price range, sort, then handed to xapi.
    """
    if not url or not url.strip():
        raise ValueError("url must be a non-empty Avito search URL")
    if page < 1:
        raise ValueError("page must be >= 1")

    parsed = parse_avito_url(url)
    query = _build_query_string(parsed)

    xapi = client or XapiClient()
    data = await xapi.search_items(
        query=query,
        price_min=parsed.pmin,
        price_max=parsed.pmax,
        location_id=parsed.region_location_id,
        sort=_map_sort(parsed.sort),
        with_delivery=parsed.only_with_delivery,
        page=page,
    )

    raw_items = data.get("items") or []
    items = [_normalise_listing(it) for it in raw_items if isinstance(it, dict)]

    return SearchPage(
        items=items,
        total=data.get("total"),
        page=int(data.get("page") or page),
        has_more=bool(data.get("has_more", False)),
        source_url=url,
        applied_query=query,
    )


# Avito's numeric `s=` param maps to xapi's string sort code.
# 104 = newest first; 1 = price ascending; 2 = price descending.
_SORT_MAP = {
    104: "date",
    1: "price",
    2: "price_desc",
}


def _map_sort(s: int | None) -> str | None:
    if s is None:
        return None
    return _SORT_MAP.get(s)

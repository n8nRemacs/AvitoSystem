"""avito_fetch_search_page tool implementation.

Takes an Avito search URL + page number, extracts query / price / location
from the URL, calls xapi, and normalises the response into ``SearchPage``.
"""
from __future__ import annotations

from typing import Any

from app.services.url_parser import ParsedAvitoUrl, parse_avito_url
from avito_mcp.integrations.xapi_client import XapiClient
from shared.models.avito import ListingImage, ListingShort, SearchPage


# Avito-side category numeric IDs we care about. Used to narrow the search to
# the right vertical when the user's URL only carries a slug. Without this,
# the iPhone profile's ``query=Apple`` returns Apple Watches, iPads and AirPods
# alongside phones because the mobile API otherwise searches across all
# categories. Add new entries when a profile starts catching foreign garbage.
_CATEGORY_SLUG_TO_ID: dict[str, int] = {
    "mobilnye_telefony": 87,
    "noutbuki": 86,
    "planshety": 96,
    "naushniki": 100,
    "smart_chasy_i_braslety": 98,
    "audio_i_video": 33,
}


# Brand+category fallback model words. When the URL uses a binary filter token
# (e.g. ``apple-ASgBAg...``) the brand parser returns just "Apple" with no
# model, and Avito's free-text search on ``Apple`` matches every Apple
# product line. Pick a model term that points the search at the right
# subcategory so iPhone-only profiles don't pull in iPads.
_BRAND_CATEGORY_MODEL_HINT: dict[tuple[str, str], str] = {
    ("apple", "mobilnye_telefony"): "iPhone",
    ("apple", "noutbuki"): "MacBook",
    ("apple", "planshety"): "iPad",
    ("apple", "naushniki"): "AirPods",
    ("apple", "smart_chasy_i_braslety"): "Apple Watch",
}


def _category_id_for(p: ParsedAvitoUrl) -> int | None:
    """Return Avito's numeric category id for the URL's deepest known slug."""
    if not p.category_path:
        return None
    # The deepest category in the path is the most specific one.
    for slug in reversed(p.category_path.split("/")):
        cid = _CATEGORY_SLUG_TO_ID.get(slug)
        if cid:
            return cid
    return None


def _build_query_string(p: ParsedAvitoUrl) -> str:
    """Pick the most useful query keyword from a parsed URL.

    Priority:
        1. explicit ``?q=`` parameter
        2. brand + model joined
        3. brand + brand-category model hint (e.g. ``Apple`` + phones → ``iPhone``)
        4. brand alone
        5. last category segment
        6. fallback to "*" (Avito accepts empty-ish queries on category-only)
    """
    if p.query:
        return p.query
    if p.brand and p.model:
        return f"{p.brand} {p.model}"
    # Brand without model + known category: substitute a model term so the
    # search hits the right product line instead of Apple's whole catalogue.
    if p.brand and p.category_path:
        deepest = p.category_path.rsplit("/", 1)[-1]
        hint = _BRAND_CATEGORY_MODEL_HINT.get((p.brand.lower(), deepest))
        if hint:
            return hint
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


async def avito_fetch_subscription_items_impl(
    filter_id: int,
    page: int = 1,
    *,
    client: XapiClient | None = None,
    account_id: str | None = None,
) -> SearchPage:
    """Fetch one page of items for an Avito autosearch (saved search).

    The xapi side pulls ``/2/subscriptions/{id}.deepLink``, parses its
    structured params, and forwards them to ``/11/items`` — exactly the
    feed the Avito mobile app shows when the user opens that subscription.
    Returns the same ``SearchPage`` shape as ``avito_fetch_search_page_impl``
    so polling can swap between URL-based and autosearch-based without
    knowing the difference.

    ``account_id``: when provided, forwarded as a query param so xapi loads
    the session for that specific pool account (T17a pool-aware routing).
    """
    xapi = client or XapiClient()
    params: dict[str, Any] = {"page": page}
    if account_id:
        params["account_id"] = account_id
    data = await xapi._get(f"/api/v1/subscriptions/{int(filter_id)}/items", params)
    raw_items = data.get("items") or []
    items = [_normalise_listing(it) for it in raw_items if isinstance(it, dict)]
    return SearchPage(
        items=items,
        total=data.get("total"),
        page=int(data.get("page") or page),
        has_more=bool(data.get("has_more", False)),
        source_url=f"avito://subscription/{filter_id}",
        applied_query=f"subscription:{filter_id}",
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
    category_id = _category_id_for(parsed)

    xapi = client or XapiClient()
    data = await xapi.search_items(
        query=query,
        price_min=parsed.pmin,
        price_max=parsed.pmax,
        location_id=parsed.region_location_id,
        category_id=category_id,
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

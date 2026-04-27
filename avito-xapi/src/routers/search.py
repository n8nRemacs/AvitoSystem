"""Avito search endpoints + raw response normalisation.

Avito mobile API returns search results as a *feed* of mixed widgets and items.
Real listings have ``type == "item"`` and the actual data is under ``value``.

Response shape (verified live 2026-04-27):

  /api/11/items
  └── status, result
       ├── items: [
       │     {type: "feedShortcutsWidget", ...},   # skip
       │     {type: "item", value: {id, title, price, galleryItems, ...}},
       │     ...
       │   ]
       ├── totalCount, mainCount, count
       └── nextPageId, lastStamp, ...

  /api/19/items/{id}
  └── id, title, description, address, coords, time, categoryId,
      images: [{<sizeKey>: <url>, ...}, ...],
      price: {value, value_signed, value_old, ...},
      seller: {name, profileType, userHash, ...},
      sellerAddressInfo: {fullAddress: {locality}, geoReferences, ...},
      sharing: {url},
      parameters: {flat: [{title, description, ...}], groups: [...]}
"""
from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.dependencies import get_current_tenant
from src.middleware.auth import require_feature
from src.models.tenant import TenantContext
from src.models.search import ItemCard, ItemImage, ItemDetail, SearchResponse
from src.workers.session_reader import load_active_session
from src.workers.http_client import AvitoHttpClient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/search", tags=["Search"])

# Image size keys (largest → smallest); we pick the first present.
_IMAGE_SIZE_PRIORITY = (
    "1280x960", "1170x878", "1080x810", "828x621", "720x540",
    "678x678", "640x480", "558x558", "507x507", "372x372",
    "339x339", "278x278", "256x256", "192x192", "140x140",
    "128x128", "96x96", "72x72", "64x64", "48x48", "36x36", "24x24",
)
# Fingerprint of "image dict": at least one key matches WxH pattern.
_SIZE_KEY_RE = re.compile(r"^\d{2,4}x\d{2,4}$")


def _get_client(ctx: TenantContext) -> AvitoHttpClient:
    session = load_active_session(ctx.tenant.id)
    if not session:
        raise HTTPException(status_code=404, detail="No active Avito session")
    return AvitoHttpClient(session)


# ── Helpers ───────────────────────────────────────────────────────────────

def _pick_image_url(img: Any) -> str | None:
    """Pick the largest available URL from an Avito image dict.

    Accepts either a flat dict ``{"640x480": "...", ...}`` or a wrapped
    ``{"value": {...}, "type": "image"}`` (search galleryItems shape).
    """
    if not isinstance(img, dict):
        return None
    # Wrapped form: galleryItems[i] = {value: {...sizes...}, type: "image"}
    inner = img.get("value")
    if isinstance(inner, dict) and any(_SIZE_KEY_RE.match(k) for k in inner):
        img = inner
    # Detail form: img dict directly contains size keys
    for size in _IMAGE_SIZE_PRIORITY:
        url = img.get(size)
        if url:
            return url
    # Last resort — pick first string value
    for v in img.values():
        if isinstance(v, str) and v.startswith("http"):
            return v
    return None


def _extract_image_size(img: Any) -> tuple[int | None, int | None]:
    """Pull width/height from picked size key like ``640x480`` if available."""
    if not isinstance(img, dict):
        return None, None
    src = img.get("value") if isinstance(img.get("value"), dict) else img
    if not isinstance(src, dict):
        return None, None
    for size in _IMAGE_SIZE_PRIORITY:
        if size in src:
            try:
                w, h = size.split("x")
                return int(w), int(h)
            except ValueError:  # pragma: no cover - defensive
                return None, None
    return None, None


def _parse_int_price(price: dict | None) -> int | None:
    """Pull integer rouble value from search/detail price object.

    Search items: ``{"current": "4 970 ₽", "priceWithoutDiscount": "5 000 ₽", ...}``
    Detail items: ``{"value": "4 970", "value_signed": "4 970 ₽", ...}``
    """
    if not isinstance(price, dict):
        return None
    candidates = (
        price.get("value"),                 # detail: bare digits
        price.get("current"),               # search: "4 970 ₽"
        price.get("priceWithoutDiscount"),  # search fallback
        price.get("value_signed"),          # detail fallback
    )
    for raw in candidates:
        if not isinstance(raw, str):
            continue
        digits = re.sub(r"[^\d]", "", raw)
        if digits:
            try:
                return int(digits)
            except ValueError:
                continue
    return None


def _format_price_text(price: dict | None) -> str | None:
    """Pretty price string for UI ("4 970 ₽")."""
    if not isinstance(price, dict):
        return None
    for key in ("value_signed", "current", "priceWithoutDiscount"):
        v = price.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return None


def _extract_item_id_from_uri(uri: str | None) -> int | None:
    """Search items expose ``ru.avito://1/item/show?...&itemId=N`` — pull N."""
    if not isinstance(uri, str) or "itemId=" not in uri:
        return None
    try:
        # ru.avito:// scheme isn't fully parseable via urlparse, fall back to regex
        m = re.search(r"itemId=(\d+)", uri)
        return int(m.group(1)) if m else None
    except (TypeError, ValueError):
        return None


def _city_from_image_alt(image_alt: str | None) -> str | None:
    """Search ``imageAlt`` is "Title, City" — pull last segment as city.

    Best-effort; returns None if format unexpected.
    """
    if not isinstance(image_alt, str):
        return None
    parts = [p.strip() for p in image_alt.split(",") if p.strip()]
    return parts[-1] if len(parts) >= 2 else None


def _city_from_seller_address(addr_info: dict | None) -> str | None:
    if not isinstance(addr_info, dict):
        return None
    full = addr_info.get("fullAddress")
    if isinstance(full, dict):
        loc = full.get("locality")
        if isinstance(loc, str) and loc:
            return loc
    return None


def _detail_params_to_dict(params: dict | None) -> dict[str, Any]:
    """Flatten ``parameters.flat`` list into a {title: description} mapping.

    Detail returns parameters under ``flat`` and ``groups``. ``flat`` is the
    user-visible list, each entry shaped like
    ``{"attributeId": 121588, "title": "Состояние", "description": "Удовлетворительное"}``.
    """
    if not isinstance(params, dict):
        return {}
    flat = params.get("flat")
    out: dict[str, Any] = {}
    if isinstance(flat, list):
        for entry in flat:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title")
            desc = entry.get("description")
            if isinstance(title, str) and isinstance(desc, str):
                out[title] = desc
    return out


# ── Normalisers ───────────────────────────────────────────────────────────

def _normalize_item_card(raw: dict) -> ItemCard:
    """Normalise one feed entry from /api/11/items into an ItemCard.

    Accepts either the new wrapped shape ``{type: "item", value: {...}}`` or
    a bare item dict (back-compat with old fixtures / tests).
    """
    # New mobile API: real listings are wrapped as {type: "item", value: {...}}
    if isinstance(raw, dict) and raw.get("type") == "item" and isinstance(raw.get("value"), dict):
        val = raw["value"]
    else:
        val = raw if isinstance(raw, dict) else {}

    # ── Images ────────────────────────────────────────────────────────────
    images: list[ItemImage] = []
    gallery = val.get("galleryItems")
    if isinstance(gallery, list):
        for img in gallery:
            url = _pick_image_url(img)
            if url:
                w, h = _extract_image_size(img)
                images.append(ItemImage(url=url, width=w, height=h))
    # Back-compat: legacy ``images`` list (strings or {url,...})
    if not images:
        for img in val.get("images", []) or []:
            if isinstance(img, str):
                images.append(ItemImage(url=img))
            elif isinstance(img, dict):
                url = img.get("url") or _pick_image_url(img)
                if url:
                    w, h = _extract_image_size(img)
                    images.append(ItemImage(
                        url=url,
                        width=img.get("width") or w,
                        height=img.get("height") or h,
                    ))

    # ── ID ────────────────────────────────────────────────────────────────
    item_id = val.get("id")
    if not isinstance(item_id, int):
        item_id = _extract_item_id_from_uri(val.get("uri")) or 0

    # ── Price ─────────────────────────────────────────────────────────────
    price_raw = val.get("price")
    if isinstance(price_raw, dict):
        price_int = _parse_int_price(price_raw)
        price_text = _format_price_text(price_raw)
    else:
        # Legacy shape (old fixtures): price is plain int, priceFormatted is string
        price_int = price_raw if isinstance(price_raw, int) else None
        price_text = val.get("priceFormatted") or val.get("price_text")

    # ── Title / address / city ────────────────────────────────────────────
    title = val.get("title") or ""
    image_alt = val.get("imageAlt")
    address = val.get("address")  # legacy fixtures
    city = (
        _city_from_image_alt(image_alt)
        or (val.get("location", {}).get("name") if isinstance(val.get("location"), dict) else None)
        or val.get("city")
    )

    # ── URL (deep-link or web) ────────────────────────────────────────────
    url = val.get("url")
    if not url:
        # Mobile API uses ``ru.avito://`` deep-link as ``uri`` — surface it as-is
        # so MCP/UI can reconstruct https://www.avito.ru/.../{id} from sharing
        # endpoint or item-detail later.
        url = val.get("uri")

    # ── Created-at ────────────────────────────────────────────────────────
    created_at = val.get("createdAt") or val.get("time")
    if isinstance(created_at, int):
        created_at = str(created_at)  # epoch seconds → keep as string per model

    # ── Seller ────────────────────────────────────────────────────────────
    seller_info = val.get("sellerInfo")
    seller_id = None
    if isinstance(seller_info, dict):
        sid = seller_info.get("userId") or seller_info.get("sellerId")
        if isinstance(sid, int):
            seller_id = sid
    # Legacy fixture fields:
    if seller_id is None:
        sid = val.get("sellerId") or val.get("userId")
        if isinstance(sid, int):
            seller_id = sid

    return ItemCard(
        id=item_id,
        title=title,
        price=price_int,
        price_text=price_text,
        address=address,
        city=city,
        images=images,
        url=url,
        created_at=created_at,
        seller_id=seller_id,
    )


def _normalize_item_detail(raw: dict, fallback_id: int = 0) -> ItemDetail:
    """Normalise /api/19/items/{id} response into an ItemDetail."""
    # ── Images ────────────────────────────────────────────────────────────
    images: list[ItemImage] = []
    for img in raw.get("images", []) or []:
        if isinstance(img, str):
            images.append(ItemImage(url=img))
        elif isinstance(img, dict):
            url = img.get("url") or _pick_image_url(img)
            if url:
                w, h = _extract_image_size(img)
                images.append(ItemImage(
                    url=url,
                    width=img.get("width") or w,
                    height=img.get("height") or h,
                ))

    # ── Price ─────────────────────────────────────────────────────────────
    price_raw = raw.get("price")
    if isinstance(price_raw, dict):
        price_int = _parse_int_price(price_raw)
        price_text = _format_price_text(price_raw)
    else:
        price_int = price_raw if isinstance(price_raw, int) else None
        price_text = raw.get("priceFormatted") or raw.get("price_text")

    # ── Address / city ────────────────────────────────────────────────────
    address = raw.get("address")
    city = _city_from_seller_address(raw.get("sellerAddressInfo"))
    if not city:
        loc = raw.get("location")
        if isinstance(loc, dict):
            city = loc.get("name")
        elif isinstance(raw.get("city"), str):
            city = raw["city"]
    # Last-resort: pull city from "Город, район" address string
    if not city and isinstance(address, str):
        first = address.split(",", 1)[0].strip()
        if first:
            city = first

    # ── URL (web) ─────────────────────────────────────────────────────────
    url = raw.get("url")
    if not url:
        sharing = raw.get("sharing")
        if isinstance(sharing, dict):
            url = sharing.get("url") or sharing.get("native")

    # ── Category ──────────────────────────────────────────────────────────
    category: str | None = None
    cat_raw = raw.get("category")
    if isinstance(cat_raw, dict):
        category = cat_raw.get("name")
    elif isinstance(cat_raw, str):
        category = cat_raw
    # Detail responses no longer carry "category" — we get categoryId only.
    # Surface it as numeric string fallback so callers know category is set.
    if not category:
        cat_id = raw.get("categoryId")
        if isinstance(cat_id, int):
            category = str(cat_id)

    # ── Seller ────────────────────────────────────────────────────────────
    seller = raw.get("seller")
    seller_name = None
    seller_id = None
    if isinstance(seller, dict):
        seller_name = seller.get("name")
        sid = seller.get("userId") or seller.get("id")
        if isinstance(sid, int):
            seller_id = sid
    if seller_id is None:
        sid = raw.get("sellerId") or raw.get("userId")
        if isinstance(sid, int):
            seller_id = sid

    # ── Params (flatten parameters.flat) ──────────────────────────────────
    params = _detail_params_to_dict(raw.get("parameters")) if raw.get("parameters") else {}
    if not params:
        # Legacy fixture: top-level "params" dict
        legacy = raw.get("params")
        if isinstance(legacy, dict):
            params = legacy

    # ── Created-at ────────────────────────────────────────────────────────
    created_at = raw.get("createdAt") or raw.get("time")
    if isinstance(created_at, int):
        created_at = str(created_at)

    return ItemDetail(
        id=raw.get("id") or fallback_id,
        title=raw.get("title") or "",
        description=raw.get("description"),
        price=price_int,
        price_text=price_text,
        address=address,
        city=city,
        images=images,
        url=url,
        category=category,
        seller_id=seller_id,
        seller_name=seller_name,
        params=params,
        created_at=created_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.get("/items", response_model=SearchResponse)
async def search_items(
    request: Request,
    query: str = Query(..., min_length=1),
    price_min: int | None = Query(None, ge=0),
    price_max: int | None = Query(None, ge=0),
    location_id: int | None = Query(None),
    category_id: int | None = Query(None),
    sort: str | None = Query(None, description="date, price, price_desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    with_delivery: bool | None = Query(None, description="Только с Авито Доставкой"),
    owner: str | None = Query(None, description="Тип продавца: private, company"),
    search_area: str | None = Query(None, description="Область поиска"),
    radius: int | None = Query(None, description="Радиус поиска в км"),
    force_location: bool | None = Query(None, description="Строго по региону"),
    ctx: TenantContext = Depends(get_current_tenant),
):
    require_feature(request, "avito.search")
    client = _get_client(ctx)
    data = await client.search_items(
        query=query, price_min=price_min, price_max=price_max,
        location_id=location_id, category_id=category_id,
        sort=sort, page=page, per_page=per_page,
        with_delivery=with_delivery, owner=owner,
        search_area=search_area, radius=radius,
        force_location=force_location,
    )

    result = data.get("result") if isinstance(data.get("result"), dict) else None
    raw_items = data.get("items") or (result.get("items") if result else []) or []

    # Filter feed: keep only real listings (skip widgets like feedShortcutsWidget,
    # ads, geo-suggest blocks, etc.). Back-compat: bare item dicts (no "type")
    # are also accepted (legacy fixtures).
    listings = [
        it for it in raw_items
        if isinstance(it, dict) and (
            it.get("type") == "item" or "id" in it
        )
    ]

    items = [_normalize_item_card(item) for item in listings]
    total = (
        data.get("total")
        or (result.get("totalCount") if result else None)
        or (result.get("mainCount") if result else None)
        or (result.get("count") if result else None)
    )

    return SearchResponse(
        items=items,
        total=total,
        page=page,
        has_more=len(listings) >= per_page,
    )


@router.get("/items/{item_id}", response_model=ItemDetail)
async def get_item(item_id: int, request: Request,
                   ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.search")
    client = _get_client(ctx)
    data = await client.get_item_details(item_id)

    raw = data if isinstance(data, dict) and "id" in data else (
        data.get("result", data) if isinstance(data, dict) else {}
    )
    if not isinstance(raw, dict):
        raw = {}

    return _normalize_item_detail(raw, fallback_id=item_id)

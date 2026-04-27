"""avito_get_listing and avito_get_listing_images tool implementations."""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from avito_mcp.integrations.xapi_client import XapiClient
from shared.models.avito import ListingDetail, ListingImage

# Avito item URLs end with ``..._<digits>`` (e.g. /iphone_12_pro_max_1234567890)
_ID_TAIL_RE = re.compile(r"_(\d{6,})$")
_BARE_DIGITS_RE = re.compile(r"^\d{6,}$")


def extract_item_id(item_id_or_url: int | str) -> int:
    """Accept either a numeric id or a full avito.ru/.../iphone_..._<id> URL."""
    if isinstance(item_id_or_url, int):
        if item_id_or_url <= 0:
            raise ValueError("item_id must be a positive integer")
        return item_id_or_url

    if not isinstance(item_id_or_url, str) or not item_id_or_url.strip():
        raise ValueError("item_id_or_url must be int or non-empty string")

    s = item_id_or_url.strip()
    if _BARE_DIGITS_RE.match(s):
        return int(s)

    parsed = urlparse(s)
    # Path looks like /moskva/telefony/.../iphone_12_pro_max_1234567890
    path = parsed.path.rstrip("/")
    last = path.rsplit("/", 1)[-1] if path else ""
    m = _ID_TAIL_RE.search(last)
    if m:
        return int(m.group(1))

    raise ValueError(f"could not extract numeric item id from: {item_id_or_url!r}")


def _normalise_detail(raw: dict[str, Any]) -> ListingDetail:
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

    params = raw.get("params") or {}
    if not isinstance(params, dict):
        params = {}

    return ListingDetail(
        id=int(raw.get("id") or 0),
        title=raw.get("title") or "",
        price=raw.get("price"),
        price_text=raw.get("price_text"),
        region=raw.get("city") or raw.get("address"),
        address=raw.get("address"),
        url=raw.get("url"),
        images=images,
        seller_id=raw.get("seller_id"),
        seller_name=raw.get("seller_name"),
        first_seen=raw.get("created_at"),
        description=raw.get("description"),
        category=raw.get("category"),
        parameters=params,
        raw_data=raw,
    )


async def avito_get_listing_impl(
    item_id_or_url: int | str,
    *,
    client: XapiClient | None = None,
) -> ListingDetail:
    item_id = extract_item_id(item_id_or_url)
    xapi = client or XapiClient()
    raw = await xapi.get_item(item_id)
    return _normalise_detail(raw)


async def avito_get_listing_images_impl(
    item_id: int | str,
    *,
    client: XapiClient | None = None,
) -> list[ListingImage]:
    detail = await avito_get_listing_impl(item_id, client=client)
    return detail.images

"""Avito autosearches (saved searches / subscriptions).

Avito mobile API calls them ``subscriptions``. The web UI calls them
``autosearch`` (https://www.avito.ru/autosearch). One subscription = one
saved filter the user maintains on the Avito side. We mirror them locally
into ``SearchProfile`` rows. See ADR-011.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

from curl_cffi.requests.exceptions import HTTPError as CurlHTTPError
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from src.routers._avito_errors import reraise_avito_error

from src.dependencies import get_current_tenant
from src.middleware.auth import require_feature
from src.models.search import SearchResponse
from src.models.tenant import TenantContext
from src.routers.search import _normalize_item_card
from src.storage.supabase import get_supabase
from src.workers.http_client import AvitoHttpClient
from src.workers.session_reader import load_active_session, load_session_for_account

router = APIRouter(prefix="/api/v1/subscriptions", tags=["Subscriptions"])


def _get_client(ctx: TenantContext) -> AvitoHttpClient:
    session = load_active_session(ctx.tenant.id)
    if not session:
        raise HTTPException(status_code=404, detail="No active Avito session")
    return AvitoHttpClient(session)


async def _resolve_client(
    ctx: TenantContext,
    account_id: str | None,
) -> AvitoHttpClient:
    """Resolve an AvitoHttpClient using pool-aware or legacy session loading.

    When ``account_id`` is provided, loads the session for that specific account
    (pool-aware path). Otherwise falls back to the legacy ``load_active_session``
    behaviour (any active session for the tenant).
    """
    if account_id:
        sb = get_supabase()
        session = await load_session_for_account(sb, account_id)
        if session is None:
            raise HTTPException(
                status_code=409,
                detail=f"account {account_id} has no active session",
            )
    else:
        session = load_active_session(ctx.tenant.id)
        if session is None:
            raise HTTPException(status_code=404, detail="No active Avito session")
    return AvitoHttpClient(session)


# ru.avito://1/items/search?categoryId=…&params[110617][0]=… — strip scheme/host
# and parse the query-string keeping bracketed keys (params[110617][0]).
def _parse_deeplink_to_search_params(deeplink: str) -> dict[str, Any]:
    if not deeplink:
        return {}
    parts = urlsplit(deeplink)
    qs = parts.query
    if not qs and "?" in deeplink:
        # urlsplit can choke on the custom scheme with no host — fall back.
        qs = deeplink.split("?", 1)[1]
    raw = parse_qs(qs, keep_blank_values=True)
    # parse_qs returns list values; flatten singletons except for ``params[…]``
    # repeated entries which should stay as lists.
    out: dict[str, Any] = {}
    for k, vs in raw.items():
        if k.startswith("params[") and len(vs) == 1:
            out[k] = vs[0]
        elif len(vs) == 1:
            out[k] = vs[0]
        else:
            out[k] = vs
    return out


@router.get("")
async def list_subscriptions(
    request: Request,
    account_id: str | None = Query(None, description="Pool account id; omit for legacy any-active fallback"),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Return the user's saved searches.

    Response shape (passthrough of mobile API):
    ``{"items": [{id, ssid, title, description, hasNewItems,
    pushFrequency, editAction, openAction, deepLink}, ...]}``.
    """
    require_feature(request, "avito.search")
    client = await _resolve_client(ctx, account_id)
    items = await client.list_subscriptions()
    return {"items": items, "count": len(items)}


@router.get("/{filter_id}/search-params")
async def get_subscription_search_params(
    request: Request,
    filter_id: int = Path(..., description="Avito subscription/filter id (numeric)"),
    account_id: str | None = Query(None, description="Pool account id; omit for legacy any-active fallback"),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Return the parsed structured search params for a single autosearch.

    Pulls ``/2/subscriptions/{filter_id}`` from Avito, parses the query-string
    of ``result.deepLink``, and hands back a dict ready to feed into
    ``search_items()`` via ``params_extra``. This is the canonical filter —
    the same one the Avito mobile app uses for the precise (chairs-free)
    feed of that subscription.

    Example return value:
        {
          "categoryId": "84",
          "locationId": "621540",
          "params[110617][0]": "491590",
          "params[110618][0]": "469735",
          "priceMin": "11000",
          "priceMax": "13500",
          "sort": "date",
          "withDeliveryOnly": "1",
          ...
        }
    """
    require_feature(request, "avito.search")
    client = await _resolve_client(ctx, account_id)
    deeplink = await client.get_subscription_deeplink(filter_id)
    if not deeplink:
        raise HTTPException(status_code=404, detail="Subscription not found")
    params = _parse_deeplink_to_search_params(deeplink)
    return {"deeplink": deeplink, "search_params": params}


_INT_PARAMS = {"categoryId": "category_id", "locationId": "location_id"}
_PRICE_PARAMS = {"priceMin": "price_min", "priceMax": "price_max"}


@router.get("/{filter_id}/items")
async def get_subscription_items(
    request: Request,
    filter_id: int = Path(..., description="Avito subscription/filter id"),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    account_id: str | None = Query(None, description="Pool account id; omit for legacy any-active fallback"),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Items for one autosearch — the chairs-free feed.

    Pulls the subscription's search-deeplink, extracts the structured filter
    (categoryId, locationId, params[…]=…, priceMin/Max, sort, withDeliveryOnly,
    geoCoords, etc.) and forwards it as ``params_extra`` to the standard
    ``/11/items`` mobile endpoint. Result schema matches /api/v1/search/items.
    """
    require_feature(request, "avito.search")
    client = await _resolve_client(ctx, account_id)
    try:
        deeplink = await client.get_subscription_deeplink(filter_id)
    except CurlHTTPError as exc:
        reraise_avito_error(exc)
    if not deeplink:
        raise HTTPException(status_code=404, detail="Subscription not found")
    raw = _parse_deeplink_to_search_params(deeplink)

    typed: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    for k, v in raw.items():
        if k in _INT_PARAMS:
            try:
                typed[_INT_PARAMS[k]] = int(v)
            except (TypeError, ValueError):
                pass
        elif k in _PRICE_PARAMS:
            try:
                typed[_PRICE_PARAMS[k]] = int(v)
            except (TypeError, ValueError):
                pass
        elif k == "withDeliveryOnly":
            typed["with_delivery"] = v in ("1", 1, True, "true")
        elif k == "sort":
            typed["sort"] = str(v)
        else:
            extra[k] = v
    typed.setdefault("query", " ")  # mobile API requires non-empty query

    try:
        data = await client.search_items(
            page=page,
            per_page=per_page,
            params_extra=extra,
            **{k: v for k, v in typed.items()},
        )
    except CurlHTTPError as exc:
        reraise_avito_error(exc)

    # Same nest-and-flatten as /api/v1/search/items.
    result = data.get("result") if isinstance(data.get("result"), dict) else None
    raw_items = data.get("items") or (result.get("items") if result else []) or []
    listings = [
        it for it in raw_items
        if isinstance(it, dict) and (it.get("type") == "item" or "id" in it)
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
    ).model_dump()

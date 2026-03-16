from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.dependencies import get_current_tenant
from src.middleware.auth import require_feature
from src.models.tenant import TenantContext
from src.models.search import ItemCard, ItemImage, ItemDetail, SearchResponse
from src.workers.session_reader import load_active_session
from src.workers.http_client import AvitoHttpClient

router = APIRouter(prefix="/api/v1/search", tags=["Search"])


def _get_client(ctx: TenantContext) -> AvitoHttpClient:
    session = load_active_session(ctx.tenant.id)
    if not session:
        raise HTTPException(status_code=404, detail="No active Avito session")
    return AvitoHttpClient(session)


def _normalize_item_card(raw: dict) -> ItemCard:
    images_raw = raw.get("images", [])
    images = []
    for img in images_raw:
        if isinstance(img, str):
            images.append(ItemImage(url=img))
        elif isinstance(img, dict):
            images.append(ItemImage(
                url=img.get("url", img.get("640x480", "")),
                width=img.get("width"),
                height=img.get("height"),
            ))

    return ItemCard(
        id=raw.get("id", 0),
        title=raw.get("title", ""),
        price=raw.get("price"),
        price_text=raw.get("priceFormatted") or raw.get("price_text"),
        address=raw.get("address"),
        city=raw.get("location", {}).get("name") if isinstance(raw.get("location"), dict) else raw.get("city"),
        images=images,
        url=raw.get("url"),
        created_at=raw.get("createdAt") or raw.get("time"),
        seller_id=raw.get("sellerId") or raw.get("userId"),
    )


@router.get("/items", response_model=SearchResponse)
async def search_items(
    request: Request,
    query: str = Query(..., min_length=1),
    price_min: int | None = Query(None, ge=0),
    price_max: int | None = Query(None, ge=0),
    location_id: int | None = Query(None),
    category_id: int | None = Query(None),
    sort: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(30, ge=1, le=100),
    ctx: TenantContext = Depends(get_current_tenant),
):
    require_feature(request, "avito.search")
    client = _get_client(ctx)
    data = await client.search_items(
        query=query, price_min=price_min, price_max=price_max,
        location_id=location_id, category_id=category_id,
        sort=sort, page=page, per_page=per_page,
    )

    raw_items = data.get("items", data.get("result", {}).get("items", []))
    items = [_normalize_item_card(item) for item in raw_items]
    total = data.get("total") or data.get("result", {}).get("total")

    return SearchResponse(
        items=items,
        total=total,
        page=page,
        has_more=len(raw_items) >= per_page,
    )


@router.get("/items/{item_id}", response_model=ItemDetail)
async def get_item(item_id: int, request: Request,
                   ctx: TenantContext = Depends(get_current_tenant)):
    require_feature(request, "avito.search")
    client = _get_client(ctx)
    data = await client.get_item_details(item_id)

    raw = data if "id" in data else data.get("result", data)

    images_raw = raw.get("images", [])
    images = []
    for img in images_raw:
        if isinstance(img, str):
            images.append(ItemImage(url=img))
        elif isinstance(img, dict):
            images.append(ItemImage(
                url=img.get("url", img.get("640x480", "")),
                width=img.get("width"),
                height=img.get("height"),
            ))

    return ItemDetail(
        id=raw.get("id", item_id),
        title=raw.get("title", ""),
        description=raw.get("description"),
        price=raw.get("price"),
        price_text=raw.get("priceFormatted") or raw.get("price_text"),
        address=raw.get("address"),
        city=raw.get("location", {}).get("name") if isinstance(raw.get("location"), dict) else raw.get("city"),
        images=images,
        url=raw.get("url"),
        category=raw.get("category", {}).get("name") if isinstance(raw.get("category"), dict) else raw.get("category"),
        seller_id=raw.get("sellerId") or raw.get("userId"),
        seller_name=raw.get("seller", {}).get("name") if isinstance(raw.get("seller"), dict) else None,
        params=raw.get("params", {}),
        created_at=raw.get("createdAt") or raw.get("time"),
    )

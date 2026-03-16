from pydantic import BaseModel
from typing import Any


class SearchParams(BaseModel):
    query: str
    price_min: int | None = None
    price_max: int | None = None
    location_id: int | None = None
    category_id: int | None = None
    sort: str | None = None  # "date", "price", "price_desc"
    page: int = 1
    per_page: int = 30


class ItemImage(BaseModel):
    url: str
    width: int | None = None
    height: int | None = None


class ItemCard(BaseModel):
    id: int
    title: str
    price: int | None = None
    price_text: str | None = None
    address: str | None = None
    city: str | None = None
    images: list[ItemImage] = []
    url: str | None = None
    created_at: str | None = None
    seller_id: int | None = None


class ItemDetail(BaseModel):
    id: int
    title: str
    description: str | None = None
    price: int | None = None
    price_text: str | None = None
    address: str | None = None
    city: str | None = None
    images: list[ItemImage] = []
    url: str | None = None
    category: str | None = None
    seller_id: int | None = None
    seller_name: str | None = None
    params: dict[str, Any] = {}
    created_at: str | None = None


class SearchResponse(BaseModel):
    items: list[ItemCard]
    total: int | None = None
    page: int = 1
    has_more: bool = False

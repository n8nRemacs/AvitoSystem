"""Tool implementations registered into the FastMCP server.

The functions here intentionally take a ``XapiClient`` as the first argument
(or accept None and lazy-construct the default one) so they can be unit tested
with mocked HTTP without going through the FastMCP layer.
"""
from .listings import (
    avito_get_listing_images_impl,
    avito_get_listing_impl,
    extract_item_id,
)
from .search import avito_fetch_search_page_impl
from .service import avito_health_check_impl

__all__ = [
    "avito_fetch_search_page_impl",
    "avito_get_listing_images_impl",
    "avito_get_listing_impl",
    "avito_health_check_impl",
    "extract_item_id",
]

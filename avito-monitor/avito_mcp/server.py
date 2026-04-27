"""FastMCP server instance + tool registration."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from avito_mcp.config import get_mcp_settings
from avito_mcp.integrations.xapi_client import XapiClient
from avito_mcp.tools.listings import (
    avito_get_listing_images_impl,
    avito_get_listing_impl,
)
from avito_mcp.tools.search import avito_fetch_search_page_impl
from avito_mcp.tools.service import avito_health_check_impl
from shared.models.avito import (
    HealthStatus,
    ListingDetail,
    ListingImage,
    SearchPage,
)


def _make_client() -> XapiClient:
    """Build a fresh XapiClient per request — short-lived httpx connections."""
    return XapiClient(get_mcp_settings())


def build_server() -> FastMCP:
    """Create and configure the FastMCP server with all tools registered.

    Kept as a function (not module-level) so tests can spin up isolated instances.
    """
    settings = get_mcp_settings()
    mcp = FastMCP(
        name="avito-mcp",
        instructions=(
            "Read-only access to Avito.ru listings via the avito-xapi gateway. "
            "Use avito_fetch_search_page to enumerate a search URL, "
            "avito_get_listing for a single item, and avito_health_check "
            "to verify the upstream session is alive."
        ),
        host=settings.avito_mcp_http_host,
        port=settings.avito_mcp_http_port,
    )

    @mcp.tool(
        name="avito_fetch_search_page",
        description=(
            "Fetch one page of an Avito.ru search query. Pass an Avito search "
            "URL (the kind a user would copy from the website) and an optional "
            "page number. Returns up to ~30 listings with id, title, price, "
            "region, image previews, seller id."
        ),
    )
    async def avito_fetch_search_page(url: str, page: int = 1) -> SearchPage:
        return await avito_fetch_search_page_impl(url, page, client=_make_client())

    @mcp.tool(
        name="avito_get_listing",
        description=(
            "Fetch full details for one Avito listing. Accepts either a numeric "
            "item id or a full avito.ru/.../iphone_..._<id> URL. Returns title, "
            "description, price, all images, seller id/name, parameters."
        ),
    )
    async def avito_get_listing(item_id_or_url: str) -> ListingDetail:
        return await avito_get_listing_impl(item_id_or_url, client=_make_client())

    @mcp.tool(
        name="avito_get_listing_images",
        description=(
            "Fetch only the images for a given listing id. Wrapper that calls "
            "avito_get_listing under the hood and returns the image list."
        ),
    )
    async def avito_get_listing_images(item_id: str) -> list[ListingImage]:
        return await avito_get_listing_images_impl(item_id, client=_make_client())

    @mcp.tool(
        name="avito_health_check",
        description=(
            "Report whether the upstream avito-xapi gateway is reachable and "
            "whether a live Avito session is loaded. Returns session TTL in "
            "hours so callers can decide if they need a session refresh."
        ),
    )
    async def avito_health_check() -> HealthStatus:
        return await avito_health_check_impl(client=_make_client())

    return mcp


# Module-level instance used by ``python -m avito_mcp`` and stdio transport.
mcp = build_server()

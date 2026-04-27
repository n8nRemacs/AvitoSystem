"""Integration test against a live avito-xapi (and therefore live Avito session).

This test is skipped by default. To run it locally:

    AVITO_MCP_INTEGRATION=1 \\
    AVITO_XAPI_URL=http://host.docker.internal:8080 \\
    AVITO_XAPI_API_KEY=test_dev_key_123 \\
    pytest tests/avito_mcp/test_integration.py -v

We use a "skip-if-unreachable" pattern instead of pytest-vcr cassettes because
the xapi response embeds presigned image URLs and timestamps that are awkward
to scrub deterministically. The unit tests above cover the offline path.
"""
from __future__ import annotations

import os

import pytest

from avito_mcp.config import McpSettings
from avito_mcp.integrations.xapi_client import XapiClient
from avito_mcp.tools.search import avito_fetch_search_page_impl
from avito_mcp.tools.service import avito_health_check_impl

INTEGRATION_ENABLED = os.environ.get("AVITO_MCP_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="set AVITO_MCP_INTEGRATION=1 to run live xapi tests",
)


def _client() -> XapiClient:
    return XapiClient(
        McpSettings(
            avito_xapi_url=os.environ["AVITO_XAPI_URL"],
            avito_xapi_api_key=os.environ["AVITO_XAPI_API_KEY"],
        )
    )


@pytest.mark.asyncio
async def test_live_health_check_reports_active_session() -> None:
    health = await avito_health_check_impl(client=_client())
    assert health.xapi_reachable is True
    assert health.session_active is True, (
        f"no active Avito session; last_error={health.last_error}"
    )
    assert health.session_ttl_hours and health.session_ttl_hours > 0


@pytest.mark.asyncio
async def test_live_fetch_search_page_iphone_12_pro_max() -> None:
    page = await avito_fetch_search_page_impl(
        url=(
            "https://www.avito.ru/moskva/telefony/mobilnye_telefony/"
            "apple-ASgBAgICAUSwwQ2OWg?pmin=11000&pmax=13500"
        ),
        page=1,
        client=_client(),
    )
    assert page.applied_query == "Apple"
    assert page.items, "expected at least one listing in 11-13.5K range"
    # All prices should land roughly in the requested range.
    in_range = [it for it in page.items if it.price and 11000 <= it.price <= 13500]
    assert len(in_range) >= 1, (
        f"expected listings in 11-13.5K; got prices: "
        f"{[it.price for it in page.items]}"
    )

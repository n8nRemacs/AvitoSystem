"""avito-mcp — thin MCP wrapper over avito-xapi.

Block 1 of V1 plan. Exposes 4 tools (`avito_fetch_search_page`,
`avito_get_listing`, `avito_get_listing_images`, `avito_health_check`) over
either stdio (local Claude Code) or HTTP+SSE (backend worker).
"""
__version__ = "0.1.0"

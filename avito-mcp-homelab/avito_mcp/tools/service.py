"""avito_health_check tool — surfaces xapi/session status to the MCP client."""
from __future__ import annotations

from avito_mcp.integrations.xapi_client import XapiClient, XapiError
from shared.models.avito import HealthStatus


async def avito_health_check_impl(
    *,
    client: XapiClient | None = None,
) -> HealthStatus:
    """Return reachability + session TTL.

    The check happens in two steps:
        1. GET /health (no auth) — confirms xapi is up.
        2. GET /api/v1/sessions/current — confirms an active Avito session exists
           and reports TTL.
    """
    xapi = client or XapiClient()

    last_error: str | None = None
    xapi_reachable = False
    try:
        await xapi.health_root()
        xapi_reachable = True
    except XapiError as exc:
        last_error = f"xapi /health failed: {exc}"

    if not xapi_reachable:
        return HealthStatus(
            xapi_reachable=False,
            avito_reachable=False,
            session_active=False,
            last_error=last_error,
        )

    try:
        session = await xapi.health()
    except XapiError as exc:
        return HealthStatus(
            xapi_reachable=True,
            avito_reachable=False,
            session_active=False,
            last_error=f"xapi /sessions/current failed: {exc}",
        )

    is_active = bool(session.get("is_active"))
    ttl_seconds = session.get("ttl_seconds")
    ttl_hours = round(ttl_seconds / 3600, 2) if isinstance(ttl_seconds, (int, float)) else None

    return HealthStatus(
        xapi_reachable=True,
        avito_reachable=is_active,
        session_active=is_active,
        session_ttl_hours=ttl_hours,
        session_ttl_human=session.get("ttl_human"),
        last_error=None if is_active else "no active Avito session in xapi",
    )

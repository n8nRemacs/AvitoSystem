"""Scenario C — Messenger alive.

PASS: ``GET /messenger/channels?limit=1`` returns HTTP 200.
FAIL: any non-200 / network error / timeout (>= 10s, controlled by client).
"""
from __future__ import annotations

from app.services.health_checker.scenarios.base import ScenarioResult
from app.services.health_checker.xapi_client import XapiClient

SCENARIO = "C"


async def scenario_c(client: XapiClient) -> ScenarioResult:
    call = await client.get("/api/v1/messenger/channels", params={"limit": 1})
    details: dict = {
        "endpoint": "/api/v1/messenger/channels?limit=1",
        "status_code": call.status_code,
    }
    if call.ok and call.status_code == 200:
        # Surface a tiny breadcrumb if body parsed.
        if isinstance(call.body, dict):
            channels = call.body.get("channels") or []
            details["returned_channels"] = len(channels) if isinstance(channels, list) else None
        return ScenarioResult(SCENARIO, "pass", call.latency_ms, details)

    details["error"] = call.error or f"HTTP {call.status_code}"
    return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

"""Scenario D — Messenger round-trip latency.

PASS: ``GET /messenger/unread-count`` returns 200 AND latency < 2000 ms.
FAIL: any other outcome. Latency is reported regardless.
"""
from __future__ import annotations

from app.services.health_checker.scenarios.base import ScenarioResult
from app.services.health_checker.xapi_client import XapiClient

SCENARIO = "D"
# 2000ms gives headroom for run-all parallel-load — sequential calls usually 700-1500ms.
MAX_LATENCY_MS = 2000


async def scenario_d(client: XapiClient) -> ScenarioResult:
    call = await client.get("/api/v1/messenger/unread-count")
    details: dict = {
        "endpoint": "/api/v1/messenger/unread-count",
        "status_code": call.status_code,
        "max_latency_ms": MAX_LATENCY_MS,
    }
    if isinstance(call.body, dict) and "count" in call.body:
        details["unread_count"] = call.body["count"]

    if not call.ok or call.status_code != 200:
        details["error"] = call.error or f"HTTP {call.status_code}"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

    if call.latency_ms >= MAX_LATENCY_MS:
        details["reason"] = f"latency {call.latency_ms}ms >= {MAX_LATENCY_MS}ms"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

    return ScenarioResult(SCENARIO, "pass", call.latency_ms, details)

"""Scenario A — Token freshness.

PASS: ``GET /sessions/current`` returns 200 AND session is valid AND
       remaining TTL > 4 hours.
FAIL: anything else.

We accept two response shapes (TZ §3 normaliser is in flux):

* spec shape: ``{is_valid, hours_left, ...}``
* live xapi:  ``{is_active, ttl_seconds, ttl_human, ...}``
"""
from __future__ import annotations

from app.services.health_checker.scenarios.base import ScenarioResult
from app.services.health_checker.xapi_client import XapiClient

SCENARIO = "A"
MIN_HOURS_LEFT = 4.0


def _extract_validity(body: dict | None) -> tuple[bool, float | None]:
    """Return ``(is_valid, hours_left)`` from either spec or live shape."""
    if not isinstance(body, dict):
        return False, None
    # Spec shape (preferred).
    is_valid = body.get("is_valid")
    hours_left = body.get("hours_left")
    if is_valid is not None and hours_left is not None:
        try:
            return bool(is_valid), float(hours_left)
        except (TypeError, ValueError):
            return False, None
    # Live xapi shape.
    is_active = body.get("is_active")
    ttl_seconds = body.get("ttl_seconds")
    if is_active is None and ttl_seconds is None:
        return False, None
    h = float(ttl_seconds) / 3600.0 if ttl_seconds is not None else None
    return bool(is_active), h


async def scenario_a(client: XapiClient) -> ScenarioResult:
    call = await client.get("/api/v1/sessions/current")
    details: dict = {
        "endpoint": "/api/v1/sessions/current",
        "status_code": call.status_code,
    }
    if not call.ok:
        details["error"] = call.error or f"HTTP {call.status_code}"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

    is_valid, hours_left = _extract_validity(call.body if isinstance(call.body, dict) else None)
    details["is_valid"] = is_valid
    details["hours_left"] = hours_left

    if not is_valid:
        details["reason"] = "session not valid"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)
    if hours_left is None:
        details["reason"] = "could not extract hours_left from response"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)
    if hours_left <= MIN_HOURS_LEFT:
        details["reason"] = f"hours_left={hours_left:.2f} <= {MIN_HOURS_LEFT}"
        return ScenarioResult(SCENARIO, "fail", call.latency_ms, details)

    return ScenarioResult(SCENARIO, "pass", call.latency_ms, details)
